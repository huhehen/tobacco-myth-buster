"""裁判逻辑：确定性规则，不依赖 LLM。

负责处理角色行动的合法性校验与结果裁决。
"""
import random

from .roles import get_camp, is_wolf
from .state_machine import Game, GamePlayer


def can_act_night(player: GamePlayer) -> bool:
    """该玩家在夜晚是否有行动。"""
    return player.role in ("狼人", "预言家", "女巫")


def pick_wolf_target(game: Game, proposals: list[int]) -> int | None:
    """狼人协商结果：从每只狼人提议的目标中投票选出（多数优先，平票随机）。"""
    if not proposals:
        return None
    alive_except_wolves = [pid for pid in game.alive_ids() if not is_wolf(game.players[pid].role)]
    if not alive_except_wolves:
        return None
    votes = {}
    for target in proposals:
        if target in alive_except_wolves:
            votes[target] = votes.get(target, 0) + 1
    if not votes:
        return random.choice(alive_except_wolves)
    max_votes = max(votes.values())
    top = [t for t, v in votes.items() if v == max_votes]
    return random.choice(top)


def valid_target(game: Game, target_id: int | None, exclude_self: int | None = None) -> bool:
    """目标合法性：存在、存活、非自己。"""
    if target_id is None:
        return False
    p = game.players.get(target_id)
    if p is None or not p.alive:
        return False
    if exclude_self is not None and target_id == exclude_self:
        return False
    return True


def divine_valid(game: Game, diviner_id: int, target_id: int) -> bool:
    """预言家查验合法性：目标存活且不是自己。"""
    return valid_target(game, target_id, exclude_self=diviner_id)


def witch_can_save(game: Game, witch_id: int) -> bool:
    """女巫能否使用解药：未用过 + 今晚有人被杀 + 死者不是女巫自己。"""
    if game.witch_used_antidote:
        return False
    if not game.dead_tonight:
        return False
    if game.players[game.dead_tonight[0]].role == "女巫":
        return False
    return True


def witch_can_poison(game: Game, witch_id: int, target_id: int) -> bool:
    """女巫能否使用毒药：未用过 + 目标存活且不是自己。"""
    return valid_target(game, target_id, exclude_self=witch_id) and not game.witch_used_poison


def guard_valid(game: Game, guard_id: int, target_id: int) -> bool:
    """守卫守护合法性：目标存活且不是自己。"""
    return valid_target(game, target_id, exclude_self=guard_id)


def hunter_can_shoot(game: Game, hunter_id: int) -> bool:
    """猎人能否开枪（未用过、已死、且死于狼人/放逐而非毒药）。"""
    p = game.players.get(hunter_id)
    return (
        p is not None and not p.shot_used and not p.alive
        and p.died_by in ("狼人", "放逐")
    )


def tally_votes(votes: dict[int, int]) -> int | None:
    """投票结算：得票最多者被放逐；平票或全弃权则无人出局。"""
    if not votes:
        return None
    counter = {}
    for target in votes.values():
        if target == 0:   # 弃权票不计入
            continue
        counter[target] = counter.get(target, 0) + 1
    if not counter:
        return None
    sorted_targets = sorted(counter.items(), key=lambda x: -x[1])
    top = sorted_targets[0]
    if len(sorted_targets) == 1 or top[1] > sorted_targets[1][1]:
        return top[0]
    return None


def end_game_reason(game: Game) -> str:
    """生成游戏结束的胜负描述。"""
    wolves = [p for p in game.players.values() if is_wolf(p.role)]
    if game.winner == "狼人阵营":
        wolf_names = "、".join(p.nickname for p in wolves if not p.alive)
        return f"狼人阵营胜利！狼人数量已不少于好人。狼人：{wolf_names}"
    good_names = "、".join(p.nickname for p in game.players.values() if get_camp(p.role) == "好人阵营")
    return f"好人阵营胜利！所有狼人已被消灭。好人：{good_names}"
