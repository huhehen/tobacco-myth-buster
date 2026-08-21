"""游戏状态机：夜晚/白天/投票/结算 阶段流转与裁判逻辑。

纯确定性逻辑（不用 LLM），负责：
- 阶段推进（夜晚 → 天亮 → 白天发言 → 投票 → 结算）
- 角色行动裁决（狼人杀人、预言家查验、女巫救毒、猎人开枪）
- 胜负判定

AI 的行动决策（杀谁/验谁/投谁）由外部（speaker 层）注入。
"""
import random
from dataclasses import dataclass, field

from .roles import get_camp, get_role_config, is_wolf


@dataclass
class GamePlayer:
    """游戏内玩家状态（与 Room.Player 分离，只含游戏数据）。"""
    player_id: int
    nickname: str
    is_ai: bool
    role: str = ""
    alive: bool = True
    # 预言家查验结果: {target_id: "狼人"/"好人"}
    divine_results: dict = field(default_factory=dict)
    witch_antidote: bool = True      # 女巫解药
    witch_poison: bool = True        # 女巫毒药
    shot_used: bool = False          # 猎人开枪
    voted: bool = False              # 本轮是否已投票
    died_by: str = ""                # 死因：狼人/毒药/放逐/枪击（毒死的猎人不可开枪）


@dataclass
class NightResult:
    """夜晚结果。"""
    killed_ids: list = field(default_factory=list)   # 最终死亡名单
    divine_result: dict = field(default_factory=dict)  # {diviner_id: {target_id: camp}}
    witch_saved: bool = False
    witch_poisoned_id: int = 0


class Game:
    """一局游戏。"""

    def __init__(self, players: list[GamePlayer], room_code: str = ""):
        self.room_code = room_code
        self.players: dict[int, GamePlayer] = {p.player_id: p for p in players}
        # 发言顺序：按编号从小到大（编号已在建房时随机分配，故顺序随机但固定 1→N）
        self.seat_order: list[int] = sorted(p.player_id for p in players)
        self.day: int = 0                 # 第几天（夜晚前 day=0）
        self.phase: str = "等待开始"       # 等待开始/夜晚/天亮/白天发言/投票/结束
        self.dead_tonight: list[int] = []
        self.divine_result: dict = {}     # {预言家id: {目标id: "狼人"/"好人"}}（累计，不清空）
        self.guard_target: int = 0        # 今晚守卫守护的玩家（0=无）
        self.night_wolf_target: int = 0   # 今晚狼人袭击的目标（0=未袭击；狼人私密，仅供狼人视角回忆）
        self.last_witch_poison: int = 0   # 女巫最近一次毒杀目标（0=未毒；女巫私密回忆）
        self.last_witch_save: bool = False  # 女巫最近一次是否使用解药（女巫私密回忆）
        self.witch_used_antidote: bool = False
        self.witch_used_poison: bool = False
        self.witch_poisoned_id: int = 0    # 今晚毒药目标（0=未用毒）
        self.public_log: list[str] = []   # 公开事件记录
        self.winner: str = ""             # 好人阵营/狼人阵营
        self.speaking_index: int = 0      # 当前发言的座位下标
        self.vote_results: dict = {}      # {投票者id: 目标id}
        self.speeches_of_day: list[dict] = []  # 本轮全部发言 [{player_id, nickname, text}]
        self.vote_thinking: dict[int, str] = {}  # {玩家id: 投票思考过程（历史记录展示）}
        self.decision_thinking: dict[int, str] = {}  # {玩家id: 本晚夜间决策思考（狼刀/查验/毒/守，复盘展示）}
        self.full_record: list[dict] = []  # 整局完整记录：发言/决策/投票（游戏结束展示）
        self.pending_human: int = 0       # 正在等待行动的人类玩家（0=无）
        self.snapshot_rev: int = 0        # 状态快照版本，每次广播后 +1

    # ---------- 初始化 ----------

    def start(self):
        """随机分配角色并进入第一夜。发言顺序按编号 1→N。"""
        role_config = get_role_config(len(self.players))
        roles = []
        for role, count in role_config.items():
            roles.extend([role] * count)
        random.shuffle(roles)
        for player, role in zip(self.seat_order, roles):
            self.players[player].role = role
        self.day = 0
        self._enter_night()

    # ---------- 阶段推进 ----------

    def _enter_night(self):
        self.day += 1
        self.phase = "夜晚"
        self.dead_tonight = []
        self.guard_target = 0
        self.night_wolf_target = 0
        self.speeches_of_day = []

    def enter_day(self):
        """天亮：公布死者，进入白天发言。"""
        self.phase = "白天发言"
        self.speaking_index = 0
        self.vote_results = {}
        self.vote_thinking = {}
        # 把本晚夜间决策思考并入 full_record（供游戏结束后复盘展示）。
        # 注意：本晚白天发言的 speech_round 在 enter_voting 时记录（day 尚未 +1）
        if self.decision_thinking:
            self.full_record.append({
                "type": "night_thinking",
                "day": self.day,
                "thinking": dict(self.decision_thinking),
            })
            self.decision_thinking = {}

    def next_speaker(self) -> int | None:
        """返回下一位应发言的存活玩家 id，全部说完返回 None。"""
        while self.speaking_index < len(self.seat_order):
            pid = self.seat_order[self.speaking_index]
            self.speaking_index += 1
            if self.players[pid].alive:
                return pid
        return None

    def enter_voting(self):
        self.phase = "投票"
        # 记录当天完整发言（此时 day 仍为该白天的天数，speeches_of_day 已填满）
        if self.speeches_of_day:
            self.full_record.append({
                "type": "speech_round",
                "day": self.day,
                "speeches": list(self.speeches_of_day),
            })

    def record_vote(self, voter_id: int, target_id: int):
        self.vote_results[voter_id] = target_id

    def all_voted(self) -> bool:
        alive_ids = [pid for pid in self.seat_order if self.players[pid].alive]
        return all(pid in self.vote_results for pid in alive_ids)

    # ---------- 夜晚行动 ----------

    def apply_night_kill(self, target_id: int):
        """狼人选定击杀目标。"""
        self.dead_tonight = [target_id]

    def apply_divine(self, diviner_id: int, target_id: int):
        """预言家查验：结果存入（玩家自身可见，跨天累计保留）。"""
        target = self.players[target_id]
        self.divine_result.setdefault(diviner_id, {})[target_id] = (
            "狼人" if is_wolf(target.role) else "好人"
        )
        self.players[diviner_id].divine_results[target_id] = (
            "狼人" if is_wolf(target.role) else "好人"
        )

    def apply_guard(self, guard_id: int, target_id: int):
        """守卫守护：记录今晚守护目标。"""
        self.guard_target = target_id

    def apply_witch_save(self):
        """女巫使用解药（救活今晚被狼杀的玩家）。"""
        if self.dead_tonight and self.players[self.dead_tonight[0]].role != "女巫":
            self.dead_tonight = []
        self.witch_used_antidote = True
        self.last_witch_save = True

    def apply_witch_poison(self, target_id: int):
        """女巫使用毒药。"""
        if target_id not in self.dead_tonight:
            self.dead_tonight.append(target_id)
        self.witch_used_poison = True
        self.witch_poisoned_id = target_id
        self.last_witch_poison = target_id

    # ---------- 结算 ----------

    def resolve_night(self):
        """夜晚结算：处理死亡、猎人开枪。返回死亡名单。

        狼刀目标受守卫守护则改为平安夜；apply_witch_poison 已保证
        狼刀与毒药重叠时只记录一次（死因按毒药计）。
        """
        # 守卫守护抵消狼刀（只移除被守护的目标，其他死亡照常结算）
        if self.guard_target and self.guard_target in self.dead_tonight:
            self.dead_tonight.remove(self.guard_target)
        poisoned = self.witch_poisoned_id if self.witch_poisoned_id in self.dead_tonight else 0
        died = list(self.dead_tonight)
        self.dead_tonight = []
        self.witch_poisoned_id = 0
        for pid in died:
            self.kill(pid, died_by="毒药" if pid == poisoned else "狼人")
        return died

    def kill(self, player_id: int, died_by: str = ""):
        p = self.players[player_id]
        if p.alive:
            p.alive = False
            p.died_by = died_by
            self.public_log.append(f"{player_id}号玩家 死亡")

    def execute(self, target_id: int):
        """白天放逐。"""
        p = self.players[target_id]
        p.alive = False
        p.died_by = "放逐"
        self.public_log.append(f"{target_id}号玩家 被放逐")

    def check_winner(self) -> str | None:
        """胜负判定：狼人全灭 → 好人胜；狼人数 ≥ 好人数 → 狼人胜。"""
        wolves = [p for p in self.players.values() if is_wolf(p.role) and p.alive]
        good = [p for p in self.players.values() if not is_wolf(p.role) and p.alive]
        if not wolves:
            self.winner = "好人阵营"
            self.phase = "结束"
            return self.winner
        if len(wolves) >= len(good):
            self.winner = "狼人阵营"
            self.phase = "结束"
            return self.winner
        return None

    # ---------- 查询 ----------

    def visible_speeches(self) -> list[dict]:
        """全部公开信息（发言记录 + 公开日志），供重连快照使用。"""
        return {
            "speeches": list(self.speeches_of_day),
            "public_log": list(self.public_log),
            "dead_ids": [pid for pid, p in self.players.items() if not p.alive],
        }

    def alive_players(self) -> list[GamePlayer]:
        return [p for p in self.players.values() if p.alive]

    def alive_ids(self) -> list[int]:
        return [p.player_id for p in self.alive_players()]

    def get_alive_except(self, exclude_ids: set[int]) -> list[int]:
        return [pid for pid in self.alive_ids() if pid not in exclude_ids]

    def wolves(self) -> list[GamePlayer]:
        return [p for p in self.players.values() if is_wolf(p.role) and p.alive]
