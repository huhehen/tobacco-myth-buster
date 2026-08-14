"""AI 发言驱动器：流式生成发言 → 广播文本增量 → 识别结束标记 → 推进。

通过 LLMPool 串行队列保证同一时刻只有一个 LLM 调用。
"""
import asyncio
import random
import re

from ..game.state_machine import Game, GamePlayer
from .llm_pool import LLMPool, PlayerSession
from .prompts import (
    SPEECH_END_MARK,
    build_speech_system_prompt,
    build_target_prompt,
    build_vote_prompt,
)


def clean_thinking(result: str) -> str:
    """清理思考文本：去掉「思考：」「投票：」等结构化标记，只保留推理内容。"""
    text = result.replace(SPEECH_END_MARK, "").strip()
    # 只保留「思考：」到「投票：」之间的推理部分
    if "思考" in text and "投票" in text:
        start = text.find("思考")
        start = text.find("：", start) + 1 if text.find("：", start) != -1 else start
        end = text.find("投票", start)
        text = text[start:end].strip() if end != -1 else text[start:].strip()
    elif text.startswith("思考："):
        text = text[len("思考："):].strip()
    return text


def parse_number(result: str, alive_ids: list[int]) -> int | None:
    """从 LLM 输出中解析玩家编号（整词匹配，避免「12」被误判为「1」）。"""
    if not result:
        return None
    # 纯数字行（LLM 按 prompt 要求只输出一个数字时）
    for line in result.splitlines():
        m = re.fullmatch(r"\s*(\d+)\s*", line.strip())
        if m and int(m.group(1)) in alive_ids:
            return int(m.group(1))
    # 「N号」格式（降序排列，避免「11号」被误判为「1号」）
    for pid in sorted(alive_ids, reverse=True):
        if f"{pid}号" in result:
            return pid
    return None


class LlmSpeaker:
    """基于 LLM 的 AI 玩家发言/决策器。"""

    def __init__(self, pool: LLMPool, on_delta=None, on_speech_end=None, on_tts=None):
        """
        on_delta: async (player_id, delta_text) -> None   流式文本增量
        on_speech_end: async (player_id, full_text) -> None  发言结束
        on_tts: async (player_id, b64_chunk) -> None      TTS 音频 chunk
        """
        self.pool = pool
        self.on_delta = on_delta
        self.on_speech_end = on_speech_end
        self.on_tts = on_tts
        self.room_code = ""  # 由 director 在开局时设置（会话按房间隔离）

    # ---------- 白天发言 ----------

    async def speak(self, game: Game, player: GamePlayer, visible_info: dict,
                    on_streaming_delta=None, prior_speeches: list[dict] | None = None) -> str:
        """让 AI 玩家发言（流式）。返回完整发言文本。

        on_streaming_delta: async (player_id, text_chunk, is_final) -> None
            每收到 LLM 一段增量立即回调；用于 director 实时广播 speech_delta。
        prior_speeches: 本回合之前的发言记录，AI 据此回应/反驳。
        """
        session = self._get_session(game, player)
        prompt = build_speech_system_prompt(game, player, prior_speeches=prior_speeches)
        session.set_system_prompt(prompt)
        # 部分提供商（如 Agnes）要求 messages 中必须存在 user 消息
        if not any(m["role"] == "user" for m in session.messages):
            session.messages.append({"role": "user", "content": "请开始你的发言。"})

        async def stream_call():
            """普通 async 函数（非生成器）：在 worker 中迭代生成器并回调。"""
            collected = ""
            async for delta in session.client.chat_stream(session.messages):
                collected += delta
                if on_streaming_delta:
                    await on_streaming_delta(player.player_id, delta, False)
                if self.on_delta:
                    await self.on_delta(player.player_id, delta)
            # 流结束再回调一次 final，让前端停止打字光标
            if on_streaming_delta:
                await on_streaming_delta(player.player_id, "", True)
            return collected

        full_text = await self.pool.submit(stream_call)
        # pool 将异常作为结果返回（不抛出），需显式检查
        if isinstance(full_text, Exception):
            print(f"⚠️ 玩家{player.player_id} 发言失败: {full_text}")
            full_text = ""
            # 失败时不写入空消息污染会话
            return ""

        # 清理结束标记（防止把标记当作发言内容广播）
        clean_text = full_text.replace(SPEECH_END_MARK, "").strip()
        if self.on_speech_end:
            await self.on_speech_end(player.player_id, clean_text)

        session.add_message("assistant", clean_text)
        return clean_text

    # ---------- 夜晚行动/投票决策 ----------

    async def decide(self, game: Game, player: GamePlayer, action: str):
        """决策：狼人提议/预言家查验/女巫救人/毒人/守卫守护/猎人开枪/投票。"""
        if action in ("狼人提议", "预言家查验", "女巫毒人", "守卫守护", "猎人开枪", "投票"):
            return await self._decide_target(game, player, action)
        if action == "女巫救人":
            return await self._decide_save(game, player)
        return False

    async def _decide_target(self, game: Game, player: GamePlayer, action: str) -> int:
        """从存活玩家中选择一个目标。"""
        alive = game.get_alive_except({player.player_id})
        if not alive:
            return 0
        if action == "投票":
            # 投票用综合推理 prompt（保留发言顺序，便于 AI 建立推理链）
            speeches = list(game.speeches_of_day)
            # 计算投票位置（在存活玩家中的顺序）
            alive_ids = sorted(alive)
            vote_position = f"{alive_ids.index(player.player_id) + 1}/{len(alive_ids)}"
            prompt = build_vote_prompt(game, player, speeches, vote_position)
            messages = [{"role": "system", "content": prompt}, {"role": "user", "content": "请投票。"}]
            try:
                result = await self.pool.submit(self._get_session(game, player).client.chat, messages, 0.5)
                # 记录投票思考（含推理过程），供历史记录展示
                thinking = clean_thinking(result)
                # 投票目标优先解析「投票：N」行，避免思考里的「N号」被误当投票
                target = self._parse_vote(result, alive)
                if not target:
                    target = parse_number(result, alive)
                if thinking:
                    game.vote_thinking[player.player_id] = thinking
                if target:
                    return target
            except Exception:
                pass
            return random.choice(alive)
        # 其他行动：简单 prompt
        prompt = build_target_prompt(game, player, action)
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": "请回答。"}]
        try:
            result = await self.pool.submit(self._get_session(game, player).client.chat, messages, 0.5)
            target = parse_number(result, alive)
            # 记录夜间决策思考（狼刀/查验/毒/守），供复盘展示
            thinking = clean_thinking(result)
            if thinking and action in ("狼人提议", "预言家查验", "女巫毒人", "守卫守护", "猎人开枪"):
                game.decision_thinking[player.player_id] = thinking
            if target:
                return target
        except Exception:
            pass
        return random.choice(alive)

    async def _decide_save(self, game: Game, player: GamePlayer) -> bool:
        """女巫救人决策。"""
        prompt = (
            f"你是狼人杀里 {player.player_id} 号玩家，女巫。"
            f"今晚 {game.dead_tonight[0]}号被狼人杀死。"
            "你有一瓶解药（仅一次），是否使用？回答「救」或「不救」。"
        )
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": "请回答。"}]
        try:
            result = await self.pool.submit(self._get_session(game, player).client.chat, messages, 0.3)
            return "救" in result and "不救" not in result
        except Exception:
            return True

    @staticmethod
    def _parse_vote(result: str, alive_ids: list[int]) -> int | None:
        """解析投票输出：优先取「投票：N」行中的 N（整词匹配，避免子串误判）。

        兜底 N号 匹配仅在无「投票」标记时使用，避免思考里的编号被误当投票目标。
        """
        # 优先：含「投票」标记的行
        for line in result.splitlines():
            if "投票" in line:
                nums = [int(m) for m in re.findall(r"\d+", line)]
                for pid in reversed(nums):
                    if pid in alive_ids:
                        return pid
        # 无「投票」标记时才兜底 N号（降序，避免「11号」被误判为「1号」）
        if "投票" not in result:
            for pid in sorted(alive_ids, reverse=True):
                if f"{pid}号" in result:
                    return pid
        return None

    # ---------- 会话管理 ----------

    def _get_session(self, game: Game, player: GamePlayer) -> PlayerSession:
        room_code = self.room_code or game.room_code
        session = self.pool.get_session(room_code, player.player_id)
        if not session:
            self.pool.assign_model(room_code, player.player_id)
            session = self.pool.get_session(room_code, player.player_id)
        return session
