"""白天阶段：发言（AI/人类合并路径、逐字流式、截断）、投票、票数统计复用 judge.tally_votes、放逐广播。"""
import asyncio

from ..judge import tally_votes, valid_target
from ..state_machine import Game, GamePlayer

# 需要校验目标合法性的行动
TARGET_ACTIONS = ("预言家查验", "女巫毒人", "守卫守护", "猎人开枪", "投票")


class DayDirector:
    """白天阶段导演：编排发言 + 投票流程。"""

    def __init__(self, director):
        """director: GameDirector 实例（用于委派广播、记录决策日志等）"""
        self.director = director
        self.game: Game = director.game
        self.broadcast = director.broadcast
        self.room = director.room

    # ---------- 公开入口 ----------
    async def run_day_phase(self):
        """执行完整白天流程：发言 → 投票。"""
        game = self.game
        await self._run_day_speeches()
        if game.phase == "结束":
            return
        await self._run_voting()

    # ---------- 发言 ----------
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
                    text = await self.director.ai_speaker.speak(
                        game, speaker, {}, on_streaming_delta=on_streaming_delta, prior_speeches=prior, speech_order=speech_order)
                except RuntimeError:
                    # LLM 超时或异常时，使用默认发言避免游戏卡死
                    await self.director._narrate(f"{speaker.nickname} 发言超时，跳过", public=True)
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
                if self.director.on_tts and text.strip():
                    asyncio.create_task(self.director.on_tts(speaker_id, text))
            else:
                # 人类玩家发言：等待前端输入
                text = await self.director._human_act(speaker, "发言")
                await self.broadcast(self.room.code, {
                    "type": "speech_delta",
                    "player_id": speaker_id,
                    "text": text,
                    "final": True,
                })
                # 人类发言也走完整 TTS
                if self.director.on_tts and text.strip():
                    asyncio.create_task(self.director.on_tts(speaker_id, text))
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
        await self.director._narrate("发言结束，请投票", public=True)
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
                target = await self.director._ai_decide(player, "投票")
            else:
                target = await self.director._human_act(player, "投票")
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
            await self.director._record_decision(self.director._make_decision_log(
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

        await self.director._narrate(text, public=True)
        await self.broadcast(self.room.code, {
            "type": "vote_result",
            "eliminated_id": eliminated,
            "eliminated_name": f"{eliminated}号玩家" if eliminated else None,
            "narrator_text": text,
            "vote_breakdown": vote_breakdown,
        })
        # 白天放逐致死的玩家需要补发上帝视角历史
        if eliminated is not None:
            await self.director._notify_newly_dead([eliminated])
        # 猎人被放逐可开枪
        if eliminated is not None and game.players[eliminated].role == "猎人":
            from ..judge import hunter_can_shoot
            if hunter_can_shoot(game, eliminated):
                from .night import NightDirector
                night_director = NightDirector(self.director)
                await night_director._check_hunter_shoot([eliminated])
        if game.check_winner():
            return
        game._enter_night()
        await self.director._narrate(f"天黑请闭眼，第 {game.day} 天夜晚开始", public=True)
        await self.broadcast(self.room.code, {
            "type": "phase_changed",
            "phase": "夜晚",
            "day": game.day,
        })