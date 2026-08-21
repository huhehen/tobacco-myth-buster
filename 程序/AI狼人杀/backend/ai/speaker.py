"""AI 发言驱动器：流式生成发言 → 广播文本增量 → 识别结束标记 → 推进。

流式 TTS 设计（参考 Verbal Werewolf arXiv 2506.00160）：
- LLM 逐字输出时，检测到句末标点立即触发 TTS
- TTS 生成音频期间，LLM 继续产出后续文本
- 两者并行，首包延迟降至 0.5-1s
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
    """清理思考文本：优先 JSON 解析，兜底标记提取。"""
    import json
    import re
    text = result.replace(SPEECH_END_MARK, "").strip()
    # 优先尝试 JSON 解析（投票 prompt 要求 JSON 输出）
    brace_start = text.find("{")
    brace_end = text.rfind("}") + 1
    if brace_start != -1 and brace_end > brace_start:
        try:
            obj = json.loads(text[brace_start:brace_end])
            if isinstance(obj, dict) and "思考" in obj:
                return str(obj["思考"]).strip()
        except (json.JSONDecodeError, ValueError):
            pass
    # 兜底：从「思考」标记提取到「投票」标记（结构化匹配，避免截断思考正文中的"投票"二字）
    if "思考" in text:
        start = text.find("思考")
        colon = text.find("：", start)
        if colon != -1:
            start = colon + 1
        else:
            colon = text.find(":", start)
            if colon != -1:
                start = colon + 1
        # 找 "投票" 作为结构化标记（JSON key 或行首），而非思考正文中的"投票"二字
        end_match = re.search(r'["\u201d]?投票["\u201d]?\s*[:：]|^投票\s*[:：]', text[start:], re.MULTILINE)
        if end_match:
            end = start + end_match.start()
            text = text[start:end].strip()
        else:
            text = text[start:].strip()
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

    async def _submit_with_retry(self, task, *args, **kwargs):
        """封装 pool.submit：失败后等 2s 重试一次，仍失败则返回该 Exception。"""
        result = await self.pool.submit(task, *args, **kwargs)
        if isinstance(result, Exception):
            await asyncio.sleep(2)
            result = await self.pool.submit(task, *args, **kwargs)
        return result

    # ---------- 白天发言 ----------

    async def speak(self, game: Game, player: GamePlayer, visible_info: dict,
                    on_streaming_delta=None, prior_speeches: list[dict] | None = None,
                    speech_order: list[int] | None = None) -> str:
        """让 AI 玩家发言（流式）。返回完整发言文本。

        on_streaming_delta: async (player_id, text_chunk, is_final) -> None
            每收到 LLM 一段增量立即回调；用于 director 实时广播 speech_delta。
        prior_speeches: 本回合之前的发言记录，AI 据此回应/反驳。
        """
        session = self._get_session(game, player)
        prompt = build_speech_system_prompt(game, player, prior_speeches=prior_speeches, speech_order=speech_order)
        session.set_system_prompt(prompt)
        # 部分提供商（如 Agnes）要求 messages 中必须存在 user 消息
        if not any(m["role"] == "user" for m in session.messages):
            session.messages.append({"role": "user", "content": "请开始你的发言。"})

        async def stream_call():
            """普通 async 函数（非生成器）：在 worker 中迭代生成器并回调。

            流式 TTS 集成：LLM 输出时边检测句末标点边触发 TTS，实现并行流水线。
            """
            collected = ""
            pending_tts = ""  # TTS 缓冲文本

            async for delta in session.client.chat_stream(session.messages):
                collected += delta
                # 实时广播文本增量
                if on_streaming_delta:
                    await on_streaming_delta(player.player_id, delta, False)
                if self.on_delta:
                    await self.on_delta(player.player_id, delta)

                # 流式 TTS：累积文本，检测到句末标点立即触发
                pending_tts += delta
                if self.on_tts and any(m in pending_tts for m in ("。", "！", "？", "\n")):
                    # 提取完整句段触发 TTS
                    sentences = re.split(r'([。！？；\n])', pending_tts)
                    complete_idx = 0
                    for i, part in enumerate(sentences):
                        if i + 1 < len(sentences) and sentences[i + 1]:
                            complete_idx = i + 2
                        else:
                            break
                    if complete_idx > 0:
                        segment = "".join(sentences[:complete_idx]).strip()
                        if segment:
                            await self.on_tts(player.player_id, segment)
                            pending_tts = "".join(sentences[complete_idx:])

            # 流结束后触发剩余文本的 TTS
            if self.on_tts and pending_tts.strip():
                await self.on_tts(player.player_id, pending_tts.strip())

            # 流结束再回调一次 final，让前端停止打字光标
            if on_streaming_delta:
                await on_streaming_delta(player.player_id, "", True)
            return collected

        full_text = await self._submit_with_retry(stream_call)
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
        """决策：狼人提议/预言家查验/女巫救人/毒人/守卫守护/猎人开枪/投票。

        思考文本会写入 game.decision_thinking（夜间行动）或 game.vote_thinking（投票），
        供 director 在死亡玩家的"上帝视角"日志里展示。
        """
        if action in ("狼人提议", "预言家查验", "女巫毒人", "守卫守护", "猎人开枪", "投票"):
            return await self._decide_target(game, player, action)
        if action == "女巫救人":
            save, thinking = await self._decide_save(game, player)
            if thinking:
                game.decision_thinking[player.player_id] = thinking
            return save
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
            # 兜底：如果 player_id 不在存活列表中（已被投票出局），使用第一个位置
            if player.player_id in alive_ids:
                vote_position = f"{alive_ids.index(player.player_id) + 1}/{len(alive_ids)}"
            else:
                vote_position = f"1/{len(alive_ids)}"
            prompt = build_vote_prompt(game, player, speeches, vote_position)
            messages = [{"role": "system", "content": prompt}, {"role": "user", "content": "请投票。"}]
            try:
                result = await self._submit_with_retry(self._get_session(game, player).client.chat, messages, 0.5)
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
            result = await self._submit_with_retry(self._get_session(game, player).client.chat, messages, 0.5)
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

    async def _decide_save(self, game: Game, player: GamePlayer) -> tuple[bool, str]:
        """女巫救人决策。返回 (是否救人, 思考文本)。

        思考文本写入 game.decision_thinking，供上帝视角日志展示。
        """
        prompt = (
            f"你是狼人杀里 {player.player_id} 号玩家，女巫。"
            f"今晚 {game.dead_tonight[0]}号被狼人杀死。"
            "你有一瓶解药（仅一次），是否使用？\n"
            "请先简要说明思考（为什么救/不救，1-2 句话），"
            "然后在最后一行单独回答「救」或「不救」。"
        )
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": "请回答。"}]
        try:
            result = await self._submit_with_retry(self._get_session(game, player).client.chat, messages, 0.5)
            decision = "救" in result and "不救" not in result
            thinking = clean_thinking(result)
            return decision, thinking
        except Exception:
            return True, ""

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

    async def review(self, game: Game, player: GamePlayer) -> str:
        """游戏结束后让 AI 玩家生成复盘。"""
        from .prompts import build_review_prompt
        prompt = build_review_prompt(game, player)
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": "请开始你的复盘。"}]
        try:
            result = await self._submit_with_retry(self._get_session(game, player).client.chat, messages, 0.7)
            return result.strip() if isinstance(result, str) else str(result).strip()
        except Exception as e:
            return f"（复盘生成失败：{e}）"
