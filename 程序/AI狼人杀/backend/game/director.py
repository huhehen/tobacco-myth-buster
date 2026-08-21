"""游戏驱动层：编排夜晚/白天/投票流程，广播事件。

M2 阶段：AI 玩家使用 FakeSpeaker（固定话术）验证游戏规则正确性。
M3 阶段：接入真实 LLM（替换 FakeSpeaker 为 LlmSpeaker）。

上帝视角（死亡玩家全视角）：
- 每个 AI 决策环节（投票/狼杀/女巫/预言家/守卫/猎人）都生成一条结构化日志，
  包含思考过程、候选、最终决策。
- 日志只广播给当前**已死亡**玩家（活人永不接收，避免泄露 AI CoT）。
- 玩家死亡瞬间补发截至当前的完整历史，之后每个新日志实时推送给死亡玩家。
"""
import asyncio
import random
import time

from ..room.manager import Room
from .judge import (
    divine_valid,
    guard_valid,
    hunter_can_shoot,
    pick_wolf_target,
    tally_votes,
    valid_target,
    witch_can_poison,
    witch_can_save,
)
from .roles import is_wolf
from .state_machine import Game, GamePlayer

# 旁白音色：沉稳男声，与 AI 玩家音色区分
NARRATOR_VOICE = "zh-CN-YunjianNeural"

# 需要校验目标合法性的行动
TARGET_ACTIONS = ("预言家查验", "女巫毒人", "守卫守护", "猎人开枪", "投票")

# 上帝视角日志的阶段 / 种类标识
DECISION_KIND_LABELS = {
    "wolf_proposal": "狼人提议",
    "wolf_consensus": "狼群决议",
    "divine": "预言家查验",
    "witch_save": "女巫救人",
    "witch_poison": "女巫毒人",
    "guard": "守卫守护",
    "hunter_shoot": "猎人开枪",
    "vote": "投票",
}


class FakeSpeaker:
    """假 AI 发言器：固定话术，用于无模型配置时验证游戏流程。"""

    def __init__(self, seed_texts: list[str]):
        self._texts = seed_texts
        self._i = 0

    async def speak(self, game: Game, player: GamePlayer, visible_info: dict,
                    on_streaming_delta=None, prior_speeches: list[dict] | None = None, speech_order: list[int] | None = None) -> str:
        text = self._texts[self._i % len(self._texts)]
        self._i += 1
        # 模拟逐字流：每 30ms 输出一个字，让前端能看到打字效果
        if on_streaming_delta:
            for ch in text:
                await on_streaming_delta(player.player_id, ch, False)
                await asyncio.sleep(0.03)
            await on_streaming_delta(player.player_id, "", True)
        else:
            await asyncio.sleep(0.05)
        return text


class GameDirector:
    """游戏总导演：推进流程、收集行动、广播事件。"""

    def __init__(self, room: Room, on_broadcast, on_narrator=None, on_tts=None):
        """on_broadcast: async (room_code, msg_dict, only: list[int] | None) -> None
        on_narrator: async (room_code, text, voice, only) -> None  旁白语音（失败静默）
        on_tts: async (player_id, text) -> None  AI/人类发言完整文本TTS（失败静默）
        """
        self.room = room
        self.broadcast = on_broadcast
        self.on_narrator = on_narrator
        self.on_tts = on_tts
        self.game: Game | None = None
        # AI 决策接口：ai_act(game, player, action) -> 决策结果
        self.ai_act = None
        self.ai_speaker = None
        # 人类行动等待：{player_id: (action, asyncio.Future)}
        self.human_actions: dict[int, tuple] = {}
        self.disconnected: set[int] = set()   # 行动中断线等待重连的玩家
        # 上帝视角日志：每个 AI 决策环节（含思考/CoT/候选/最终决定）。
        # 死亡玩家可随时调取，活人永不接收。游戏结束不持久化。
        self.decision_logs: list[dict] = []
        # 已通知过死亡日志的玩家集合，避免重复补发
        self._notified_dead: set[int] = set()

    # ---------- 对外接口 ----------

    def submit_human_action(self, player_id: int, action: str, data: dict):
        """前端提交人类行动结果（由 ws_handler 调用）。行动类型不一致则丢弃。"""
        entry = self.human_actions.get(player_id)
        if entry is None:
            return
        expected, fut = entry
        if action != expected or fut.done():
            return
        fut.set_result({"action": action, "data": data})

    def snapshot(self, player_id: int) -> dict | None:
        """重连状态快照：角色 + 阶段 + 死者 + 公开事件 + 待行动状态。

        已死亡玩家额外获得截至当前的完整决策日志（上帝视角）。
        """
        game = self.game
        if game is None:
            return None
        p = game.players.get(player_id)
        if p is None:
            return None
        snap = {
            "day": game.day,
            "phase": game.phase,
            "role": p.role,
            "alive": p.alive,
            "dead_ids": [pid for pid, g in game.players.items() if not g.alive],
            "public_log": list(game.public_log),
            "speeches": list(game.speeches_of_day),
            "winner": game.winner,
            "pending_action": None,
        }
        if is_wolf(p.role):
            snap["wolf_partners"] = [
                w.player_id for w in game.players.values()
                if w.player_id != player_id and is_wolf(w.role)
            ]
        if p.role == "预言家":
            snap["divine_results"] = dict(p.divine_results)
        if p.role == "女巫":
            snap["witch_antidote"] = game.witch_used_antidote
            snap["witch_poison"] = game.witch_used_poison
        # 已死亡玩家附带决策日志（上帝视角历史快照）
        if not p.alive:
            snap["decision_logs"] = list(self.decision_logs)
        entry = self.human_actions.get(player_id)
        if entry is not None:
            snap["pending_action"] = entry[0]
        return snap

    # ---------- 启动 ----------

    def build_game(self) -> Game:
        players = [
            GamePlayer(
                player_id=p.player_id,
                nickname=p.nickname,
                is_ai=p.is_ai,
            )
            for p in self.room.players.values()
        ]
        self.game = Game(players, room_code=self.room.code)
        return self.game

    async def run(self):
        """开始并运行整局游戏（异步直到结束）。"""
        game = self.build_game()
        game.start()
        await self.broadcast(self.room.code, {
            "type": "game_started",
            "players": [
                {"player_id": p.player_id, "nickname": p.nickname, "is_ai": p.is_ai}
                for p in game.players.values()
            ],
        })
        # 角色私密推送：每个玩家只收到自己的角色
        for p in game.players.values():
            await self._send(p.player_id, {
                "type": "your_role",
                "player_id": p.player_id,
                "role": p.role,
                "camp": "狼人阵营" if is_wolf(p.role) else "好人阵营",
            })
            # 狼人互知同伙（私密推送）
            if p.role == "狼人":
                partners = [w.player_id for w in game.players.values()
                            if is_wolf(w.role) and w.player_id != p.player_id]
                await self._send(p.player_id, {
                    "type": "wolf_partners",
                    "player_id": p.player_id,
                    "partner_ids": partners,
                })
        await self.broadcast(self.room.code, {
            "type": "phase_changed",
            "phase": "夜晚",
            "day": game.day,
        })
        await self._narrate("天黑请闭眼，第 1 天夜晚开始", public=True)
        try:
            while game.phase != "结束":
                if game.phase == "夜晚":
                    await self._run_night()
                elif game.phase == "白天发言":
                    await self._run_day_speeches()
                elif game.phase == "投票":
                    await self._run_voting()
        finally:
            for _, fut in self.human_actions.values():
                if not fut.done():
                    fut.cancel()
            self.human_actions.clear()
            self.disconnected.clear()
            game.pending_human = 0
            # 最后一夜若在夜晚结算时结束（未走到 enter_day），兜底并入夜间思考
            if game.decision_thinking:
                game.full_record.append({
                    "type": "night_thinking",
                    "day": game.day,
                    "thinking": dict(game.decision_thinking),
                })
                game.decision_thinking = {}
        # 结束：公开全部身份 + 完整记录（供游戏结束后查看）
        await self._narrate(f"游戏结束，{game.winner}获得胜利", public=True)
        await self.broadcast(self.room.code, {
            "type": "game_over",
            "winner": game.winner,
            "roles": {pid: p.role for pid, p in game.players.items()},
            "full_record": game.full_record,
        })
        # ---- 游戏结束后：AI 玩家复盘 ----
        reviews = {}
        if self.ai_speaker and hasattr(self.ai_speaker, "review"):
            for p in game.players.values():
                if p.is_ai:
                    try:
                        review_text = await self.ai_speaker.review(game, p)
                        reviews[p.player_id] = review_text
                        await self.broadcast(self.room.code, {
                            "type": "post_game_review",
                            "player_id": p.player_id,
                            "nickname": p.nickname,
                            "role": p.role,
                            "text": review_text,
                        })
                    except Exception as e:
                        print(f"⚠️ 玩家{p.player_id} 复盘失败: {e}")
        if reviews:
            game.full_record.append({
                "type": "post_game_review",
                "day": game.day,
                "reviews": {
                    str(pid): text for pid, text in reviews.items()
                },
            })

    # ---------- 夜晚 ----------

    async def _run_night(self):
        game = self.game
        # 1. 狼人协商杀人：先收集每只狼的提议，再选一个目标
        wolves = game.wolves()
        await self._narrate("狼人请睁眼，请选择今晚要袭击的玩家",
                            only=[w.player_id for w in wolves])
        proposals = []
        for wolf in wolves:
            if wolf.is_ai:
                target = await self._ai_decide(wolf, "狼人提议")
            else:
                target = await self._human_act(wolf, "狼人提议")
            proposals.append(target or 0)
            # 上帝视角日志：每只狼的提议 + CoT 思考
            thinking = game.decision_thinking.get(wolf.player_id, "")
            await self._record_decision(self._make_decision_log(
                day=game.day, phase="夜晚",
                kind="wolf_proposal",
                actor=wolf,
                thinking=thinking,
                target_id=target or 0,
                target_name=f"{target}号玩家" if target else "",
            ))
        target = pick_wolf_target(game, proposals)
        if target is None:
            good = [pid for pid in game.alive_ids() if not is_wolf(game.players[pid].role)]
            if good:
                target = random.choice(good)
        # 狼群决议日志：汇总每只狼的提议 + 最终击杀目标
        proposal_summary = [
            {"wolf_id": w.player_id, "wolf_nickname": w.nickname, "target_id": t}
            for w, t in zip(wolves, proposals)
        ]
        await self._record_decision(self._make_decision_log(
            day=game.day, phase="夜晚",
            kind="wolf_consensus",
            actor=None,
            thinking="狼群投票汇总",
            target_id=target or 0,
            target_name=f"{target}号玩家" if target else "",
            extra={
                "actor_role": "狼群",
                "proposals": proposal_summary,
            },
        ))
        if target is not None:
            game.apply_night_kill(target)
        # 狼刀目标属狼人私密信息：只记入 game 状态，不进 full_record（防泄漏）
        game.night_wolf_target = target

        # 2. 预言家查验
        for player in game.players.values():
            if player.role == "预言家" and player.alive:
                await self._narrate("预言家请睁眼，请选择要查验的玩家",
                                    only=[player.player_id])
                if player.is_ai:
                    div_target = await self._ai_decide(player, "预言家查验")
                else:
                    div_target = await self._human_act(player, "预言家查验")
                # 上帝视角日志：查验决策
                thinking = game.decision_thinking.get(player.player_id, "")
                if div_target:
                    await self._record_decision(self._make_decision_log(
                        day=game.day, phase="夜晚",
                        kind="divine",
                        actor=player,
                        thinking=thinking,
                        target_id=div_target,
                        target_name=f"{div_target}号玩家",
                        extra={
                            "result": "狼人" if is_wolf(game.players[div_target].role) else "好人",
                        },
                    ))
                if div_target and divine_valid(game, player.player_id, div_target):
                    game.apply_divine(player.player_id, div_target)
                    game.full_record.append({
                        "type": "divine",
                        "day": game.day,
                        "seer": player.player_id,
                        "target": div_target,
                        "result": "狼人" if is_wolf(game.players[div_target].role) else "好人",
                    })
                    await self._send(player.player_id, {
                        "type": "divine_result",
                        "player_id": player.player_id,
                        "target_id": div_target,
                        "camp": game.divine_result[player.player_id][div_target],
                    })

        # 3. 女巫行动
        for player in game.players.values():
            if player.role == "女巫" and player.alive:
                await self._narrate("女巫请睁眼，请选择是否使用药剂",
                                    only=[player.player_id])
                await self._run_witch(player)

        # 4. 守卫行动（12 人局）
        for player in game.players.values():
            if player.role == "守卫" and player.alive:
                await self._narrate("守卫请睁眼，请选择今晚要守护的玩家",
                                    only=[player.player_id])
                if player.is_ai:
                    guard_target = await self._ai_decide(player, "守卫守护")
                else:
                    guard_target = await self._human_act(player, "守卫守护")
                # 上帝视角日志：守卫守护决策
                thinking = game.decision_thinking.get(player.player_id, "")
                if guard_target:
                    await self._record_decision(self._make_decision_log(
                        day=game.day, phase="夜晚",
                        kind="guard",
                        actor=player,
                        thinking=thinking,
                        target_id=guard_target,
                        target_name=f"{guard_target}号玩家",
                    ))
                if guard_target and guard_valid(game, player.player_id, guard_target):
                    game.apply_guard(player.player_id, guard_target)
                    await self._send(player.player_id, {
                        "type": "guard_result",
                        "player_id": player.player_id,
                        "target_id": guard_target,
                    })

        # 5. 天亮结算
        died = game.resolve_night()

        # 记录公开死讯（所有玩家可见）——死亡名单是公开信息
        if died:
            game.full_record.append({
                "type": "death",
                "day": game.day,
                "died": died,
            })

        if died:
            text = f"天亮了，昨晚 {self._join_ids(died)} 死亡"
        else:
            text = "天亮了，昨晚是平安夜"
        await self._narrate(text, public=True)
        await self.broadcast(self.room.code, {
            "type": "night_result",
            "day": game.day,
            "died_ids": died,
            "died_names": [f"{d}号玩家" for d in died],
            "narrator_text": text,
        })

        # 死亡瞬间补发上帝视角历史（只对新死者；_notified_dead 去重）
        if died:
            await self._notify_newly_dead(died)

        # 6. 猎人被狼杀可开枪
        await self._check_hunter_shoot(died)

        # 7. 检查胜负
        if game.check_winner():
            return
        game.enter_day()
        await self.broadcast(self.room.code, {
            "type": "phase_changed",
            "phase": "白天发言",
            "day": game.day,
        })

    async def _run_witch(self, witch: GamePlayer):
        game = self.game
        # 救人（仅当晚有可救对象时）
        if game.dead_tonight and witch_can_save(game, witch.player_id):
            if witch.is_ai:
                save = await self._ai_decide(witch, "女巫救人")
            else:
                save = await self._human_act(witch, "女巫救人")
            # 上帝视角日志：女巫救人决策
            thinking = game.decision_thinking.get(witch.player_id, "")
            await self._record_decision(self._make_decision_log(
                day=game.day, phase="夜晚",
                kind="witch_save",
                actor=witch,
                thinking=thinking,
                target_id=game.dead_tonight[0] if game.dead_tonight else 0,
                target_name=f"{game.dead_tonight[0]}号玩家" if game.dead_tonight else "",
                extra={"decision_text": "使用解药救人" if save else "不使用解药"},
            ))
            if save:
                game.apply_witch_save()
                await self._send(witch.player_id, {
                    "type": "witch_action",
                    "player_id": witch.player_id,
                    "action": "救人",
                })
        # 毒人（只要毒药未用，就询问是否使用及目标）
        if not game.witch_used_poison:
            if witch.is_ai:
                poison_target = await self._ai_decide(witch, "女巫毒人")
            else:
                poison_target = await self._human_act(witch, "女巫毒人")
            # 上帝视角日志：女巫毒人决策
            thinking = game.decision_thinking.get(witch.player_id, "")
            if poison_target:
                await self._record_decision(self._make_decision_log(
                    day=game.day, phase="夜晚",
                    kind="witch_poison",
                    actor=witch,
                    thinking=thinking,
                    target_id=poison_target,
                    target_name=f"{poison_target}号玩家",
                    extra={"decision_text": "使用毒药"},
                ))
            if poison_target and witch_can_poison(game, witch.player_id, poison_target):
                game.apply_witch_poison(poison_target)
                await self._send(witch.player_id, {
                    "type": "witch_action",
                    "player_id": witch.player_id,
                    "action": "毒人",
                    "target_id": poison_target,
                })

    async def _check_hunter_shoot(self, died_ids: list[int]):
        game = self.game
        for pid in died_ids:
            player = game.players[pid]
            if player.role == "猎人" and hunter_can_shoot(game, pid):
                await self._narrate(f"{pid}号玩家被杀害，猎人发动技能，请选择开枪带走谁",
                                    only=[pid])
                if player.is_ai:
                    shoot_target = await self._ai_decide(player, "猎人开枪")
                else:
                    shoot_target = await self._human_act(player, "猎人开枪")
                # 上帝视角日志：猎人开枪决策
                thinking = game.decision_thinking.get(player.player_id, "")
                if shoot_target:
                    await self._record_decision(self._make_decision_log(
                        day=game.day, phase="夜晚",
                        kind="hunter_shoot",
                        actor=player,
                        thinking=thinking,
                        target_id=shoot_target,
                        target_name=f"{shoot_target}号玩家",
                        extra={"trigger": f"{pid}号玩家死亡触发"},
                    ))
                if shoot_target and valid_target(game, shoot_target):
                    player.shot_used = True
                    game.kill(shoot_target, died_by="枪击")
                    await self._narrate(f"猎人开枪带走了 {shoot_target}号玩家", public=True)
                    await self.broadcast(self.room.code, {
                        "type": "hunter_shot",
                        "hunter_id": pid,
                        "target_id": shoot_target,
                        "narrator_text": f"猎人开枪带走了 {shoot_target}号玩家",
                    })
                    # 猎人开枪致死的玩家也需要补发上帝视角历史
                    await self._notify_newly_dead([shoot_target])
                if game.check_winner():
                    return

    # ---------- 白天发言 ----------

    async def _run_day_speeches(self):
        game = self.game
        while True:
            speaker_id = game.next_speaker()
            if speaker_id is None:
                break
            speaker = game.players[speaker_id]
            await self.broadcast(self.room.code, {
                "type": "speech_turn",
                "player_id": speaker_id,
                "nickname": speaker.nickname,
            })
            if speaker.is_ai:
                # 本回合之前的全部发言（公开上下文，AI 据此反驳/回应）
                prior = list(game.speeches_of_day)
                # 计算存活玩家的发言顺序
                speech_order = [pid for pid in game.seat_order if game.players[pid].alive]
                async def on_streaming_delta(pid, chunk, is_final):
                    # 剥掉流式 chunk 中的【发言结束】标记，避免泄漏到前端历史/发言区
                    if chunk and "【发言结束】" in chunk:
                        chunk = chunk.replace("【发言结束】", "")
                    if not chunk and not is_final:
                        return
                    await self.broadcast(self.room.code, {
                        "type": "speech_delta",
                        "player_id": pid,
                        "text": chunk,
                        "final": is_final,
                    })
                try:
                    text = await self.ai_speaker.speak(
                        game, speaker, {}, on_streaming_delta=on_streaming_delta, prior_speeches=prior, speech_order=speech_order)
                except RuntimeError:
                    # LLM 超时或异常时，使用默认发言避免游戏卡死
                    await self._narrate(f"{speaker.nickname} 发言超时，跳过", public=True)
                    text = "（发言超时）"
                # 补发清理后的完整文本（流式增量里可能含结束标记）
                await self.broadcast(self.room.code, {
                    "type": "speech_delta",
                    "player_id": speaker_id,
                    "text": text,
                    "final": True,
                    "replace": True,
                })
                # 发言完毕后整段 TTS（避免按句分段生成导致音频碎片化）
                if self.on_tts and text.strip():
                    asyncio.create_task(self.on_tts(speaker_id, text))
            else:
                # 人类玩家发言：等待前端输入
                text = await self._human_act(speaker, "发言")
                await self.broadcast(self.room.code, {
                    "type": "speech_delta",
                    "player_id": speaker_id,
                    "text": text,
                    "final": True,
                })
                # 人类发言也走完整 TTS
                if self.on_tts and text.strip():
                    asyncio.create_task(self.on_tts(speaker_id, text))
            # 防御性截断：单条发言不超过 500 字，避免恶意 / 失控文本撑爆前端
            text = str(text or "")
            if len(text) > 500:
                text = text[:500]
            game.speeches_of_day.append({
                "player_id": speaker_id,
                "nickname": speaker.nickname,
                "text": text,
            })
            await self.broadcast(self.room.code, {
                "type": "speech_end",
                "player_id": speaker_id,
            })
            if game.check_winner():
                return
        game.enter_voting()
        await self._narrate("发言结束，请投票", public=True)
        await self.broadcast(self.room.code, {
            "type": "phase_changed",
            "phase": "投票",
            "day": game.day,
        })

    # ---------- 投票 ----------

    async def _run_voting(self):
        game = self.game
        for player in game.players.values():
            if not player.alive:
                continue
            if player.is_ai:
                target = await self._ai_decide(player, "投票")
            else:
                target = await self._human_act(player, "投票")
            # 非法目标（越界/已死/自己）→ 弃权
            if not valid_target(game, target):
                target = 0
            game.record_vote(player.player_id, target)
            await self.broadcast(self.room.code, {
                "type": "vote_update",
                "voter_id": player.player_id,
                "target_id": target,
            })
            # 上帝视角日志：每位投票者的思考 + 票型
            thinking = game.vote_thinking.get(player.player_id, "")
            await self._record_decision(self._make_decision_log(
                day=game.day, phase="投票",
                kind="vote",
                actor=player,
                thinking=thinking,
                target_id=target,
                target_name=f"{target}号玩家" if target else "弃权",
            ))
        eliminated = tally_votes(game.vote_results)
        if eliminated is not None:
            game.execute(eliminated)
            game.full_record.append({
                "type": "execution",
                "day": game.day,
                "executed": eliminated,
            })
        # 投票轮完整记录（含思考，供复盘展示 + 后续轮模型回忆）
        game.full_record.append({
            "type": "vote_round",
            "day": game.day,
            "votes": [
                {"voter": vid, "target": tid}
                for vid, tid in sorted(game.vote_results.items())
            ],
            "thinking": dict(game.vote_thinking),
        })
        if eliminated is not None:
            text = f"{eliminated}号玩家被投票放逐"
        else:
            text = "平票，无人出局"
        # 构建投票明细（存活玩家的投票汇总），得票数走 judge.tally_votes 的同款去弃权算法
        breakdown_lines = []
        for pid in sorted(game.alive_ids()):
            target = game.vote_results.get(pid, 0)
            if target:
                breakdown_lines.append(f"{pid}号→{target}号")
            else:
                breakdown_lines.append(f"{pid}号弃权")
        vote_breakdown = " | ".join(breakdown_lines)

        await self._narrate(text, public=True)
        await self.broadcast(self.room.code, {
            "type": "vote_result",
            "eliminated_id": eliminated,
            "eliminated_name": f"{eliminated}号玩家" if eliminated else None,
            "narrator_text": text,
            "vote_breakdown": vote_breakdown,
        })
        # 白天放逐致死的玩家需要补发上帝视角历史
        if eliminated is not None:
            await self._notify_newly_dead([eliminated])
        # 猎人被放逐可开枪
        if eliminated is not None and game.players[eliminated].role == "猎人" and hunter_can_shoot(game, eliminated):
            await self._check_hunter_shoot([eliminated])
        if game.check_winner():
            return
        game._enter_night()
        await self._narrate(f"天黑请闭眼，第 {game.day} 天夜晚开始", public=True)
        await self.broadcast(self.room.code, {
            "type": "phase_changed",
            "phase": "夜晚",
            "day": game.day,
        })

    # ---------- AI 决策（M2 用假决策，M3 替换） ----------

    async def _ai_decide(self, player: GamePlayer, action: str) -> int | bool:
        """AI 决策入口：返回目标 id 或布尔。"""
        if self.ai_speaker is not None and hasattr(self.ai_speaker, "decide"):
            return await self.ai_speaker.decide(self.game, player, action)
        if self.ai_act:
            return await self.ai_act(self.game, player, action)
        # 默认假决策
        if action == "女巫救人":
            return True
        alive_except = self.game.get_alive_except({player.player_id})
        if alive_except:
            return random.choice(alive_except)
        return 0

    # ---------- 人类行动 ----------

    async def _human_act(self, player: GamePlayer, action: str):
        """等待人类玩家在前端做出行动（断线时等待重连后重发请求）。"""
        game = self.game
        while True:
            # 断线等待：直到玩家重连
            while not self._is_connected(player.player_id):
                self.disconnected.add(player.player_id)
                await asyncio.sleep(0.5)
            self.disconnected.discard(player.player_id)
            # 发送（或重发）行动请求
            game.pending_human = player.player_id
            await self._send(player.player_id, {
                "type": "human_action_req",
                "player_id": player.player_id,
                "action": action,
            })
            fut = asyncio.get_running_loop().create_future()
            self.human_actions[player.player_id] = (action, fut)
            try:
                result = await fut
            except asyncio.CancelledError:
                self.human_actions.pop(player.player_id, None)
                game.pending_human = 0
                raise
            finally:
                pass
            self.human_actions.pop(player.player_id, None)
            game.pending_human = 0
            parsed = self._parse_human_result(result, action)
            # 目标类行动：非法目标重新要求
            if action in TARGET_ACTIONS and not valid_target(game, parsed, exclude_self=player.player_id):
                await self._send(player.player_id, {
                    "type": "action_invalid",
                    "player_id": player.player_id,
                    "message": "目标不合法，请重新选择",
                })
                continue
            return parsed

    def _is_connected(self, player_id: int) -> bool:
        p = self.room.players.get(player_id)
        return bool(p and p.connected)

    def _parse_human_result(self, result: dict, action: str):
        """解析人类玩家的行动结果（action 已在 submit 时校验一致）。"""
        data = result.get("data", {})
        if action in TARGET_ACTIONS or action == "狼人提议":
            t = data.get("target_id", 0)
            try:
                return int(t)
            except (TypeError, ValueError):
                return 0
        if action == "女巫救人":
            return bool(data.get("save", False))
        if action == "发言":
            text = str(data.get("text", "") or "")
            if len(text) > 500:
                text = text[:500]
            return text
        return False

    # ---------- 旁白与广播 ----------

    def _join_ids(self, ids: list[int]) -> str:
        return "、".join(f"{i}号玩家" for i in ids)

    async def _narrate(self, text: str, public: bool = False, only: list[int] | None = None):
        """旁白：文本消息（公开或定向）+ 语音（失败静默）。"""
        if public:
            await self.broadcast(self.room.code, {"type": "narrator", "text": text})
        elif only:
            for pid in only:
                await self._send(pid, {"type": "narrator", "text": text, "private": True})
        if self.on_narrator:
            await self.on_narrator(self.room.code, text, NARRATOR_VOICE, None if public else only)

    async def _send(self, player_id: int, msg: dict):
        """定向发送（仅该玩家可见）。"""
        await self.broadcast(self.room.code, msg, [player_id])

    # ---------- 上帝视角（死亡玩家全视角） ----------

    def _dead_player_ids(self) -> list[int]:
        """当前已死亡玩家 id 列表（用于决策日志定向广播）。"""
        if not self.game:
            return []
        return [pid for pid, p in self.game.players.items() if not p.alive]

    def _make_decision_log(self, *, day: int, phase: str, kind: str,
                            actor: GamePlayer | None = None,
                            thinking: str = "",
                            target_id: int = 0,
                            target_name: str = "",
                            extra: dict | None = None) -> dict:
        """构造一条上帝视角日志（不含发送动作）。"""
        log = {
            "day": day,
            "phase": phase,
            "kind": kind,
            "kind_label": DECISION_KIND_LABELS.get(kind, kind),
            "thinking": thinking,
            "decision_target_id": target_id,
            "decision_target_name": target_name or (f"{target_id}号玩家" if target_id else ""),
            "ts": time.time(),
        }
        if actor is not None:
            log["actor_id"] = actor.player_id
            log["actor_role"] = actor.role
            log["actor_nickname"] = actor.nickname
        if extra:
            log.update(extra)
        return log

    async def _record_decision(self, log_entry: dict):
        """记录一条决策日志 + 实时推送给所有已死亡玩家（活人永不接收）。"""
        self.decision_logs.append(log_entry)
        dead_ids = self._dead_player_ids()
        if dead_ids:
            await self.broadcast(self.room.code, {
                "type": "decision_log",
                "log": log_entry,
            }, only=dead_ids)

    async def _send_godview_history(self, player_id: int):
        """向刚死亡的玩家一次性补发所有历史日志（含思考 / CoT）。"""
        if not self.decision_logs:
            return
        await self._send(player_id, {
            "type": "decision_log_history",
            "logs": list(self.decision_logs),
        })

    async def _notify_newly_dead(self, newly_dead: list[int]):
        """玩家死亡瞬间：补发上帝视角历史 + 推送 you_died。

        每个玩家只通知一次（用 _notified_dead 集合去重）。
        """
        for pid in newly_dead:
            if pid in self._notified_dead:
                continue
            self._notified_dead.add(pid)
            await self._send_godview_history(pid)
            await self._send(pid, {
                "type": "you_died",
                "player_id": pid,
            })
