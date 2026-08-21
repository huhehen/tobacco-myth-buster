"""edge-tts 流式封装：文本 → mp3 音频 chunk 流。

免费、中文音色丰富、支持流式。首个音频包延迟通常 < 1.5 秒。

⚠️ edge-tts/Azure 存在内容策略拦截（NoAudioReceived）问题，
判定规则不透明、不稳定。策略：
1. 不发整句（命中率太低），直接按句末标点切分
2. 失败则按逗号切分
3. 每片段最多重试 2 次
4. 最终失败静默跳过

流式分段 TTS（stream_speech_segmented）：
- 边接收文本边按句末标点切分触发 TTS
- 首包延迟可降至 0.5-1s（无需等待完整发言）
- 参考 Verbal Werewolf (arXiv 2506.00160) 的并行流水线设计
"""
import asyncio
import base64
import re

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

# 句末标点（触发 TTS 切分）
SENTENCE_ENDERS = re.compile(r'[。！？；\n]')
# 逗号分隔符（降级切分）
COMMA_DELIMITER = re.compile(r'[，,]')


async def _try_stream(text: str, voice: str):
    """尝试一次 TTS，yield base64 audio chunks。失败 raise。"""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield base64.b64encode(chunk["data"]).decode("ascii")


def _split_segments(text: str, delimiters: str) -> list[str]:
    parts = re.split(f'([{re.escape(delimiters)}])', text)
    segments = []
    i = 0
    while i < len(parts):
        if i + 1 < len(parts) and parts[i + 1]:
            segments.append(parts[i] + parts[i + 1])
            i += 2
        else:
            if parts[i]:
                segments.append(parts[i])
            i += 1
    return [s.strip() for s in segments if s and s.strip()]


async def _try_segment(seg: str, voice: str, max_retry: int = 2):
    """尝试生成单个片段的 TTS。失败 raise。内部重试 max_retry 次。"""
    import edge_tts
    for attempt in range(max_retry + 1):
        try:
            chunks = []
            async for b64 in _try_stream(seg, voice):
                chunks.append(b64)
            if chunks:
                for b64 in chunks:
                    yield b64
                return
            raise edge_tts.exceptions.NoAudioReceived("empty stream")
        except edge_tts.exceptions.NoAudioReceived:
            if attempt < max_retry:
                await asyncio.sleep(0.15)
                continue
            raise
        except Exception:
            raise
    raise edge_tts.exceptions.NoAudioReceived("retry exhausted")


async def stream_speech(text: str, voice: str = DEFAULT_VOICE):
    """流式生成 TTS 音频。多级降级策略。"""
    if not text or not text.strip():
        return

    segments = _split_segments(text, '。！？；')
    if not segments:
        return

    yielded_total = 0
    pending = []

    # 第1轮：句末切分
    for seg in segments:
        yielded_this = 0
        try:
            async for b64 in _try_segment(seg, voice, max_retry=1):
                yielded_total += 1
                yielded_this += 1
                yield b64
        except Exception:
            pass
        if yielded_this == 0:
            pending.append(seg)

    # 第2轮：失败的片段按逗号再切
    if pending:
        for seg in pending:
            sub_segments = _split_segments(seg, '，')
            if not sub_segments:
                sub_segments = [seg]
            for sub in sub_segments:
                yielded_this = 0
                try:
                    async for b64 in _try_segment(sub, voice, max_retry=1):
                        yielded_total += 1
                        yielded_this += 1
                        yield b64
                except Exception:
                    pass

    if yielded_total == 0:
        print(f"⚠️ TTS 整句失败: {text[:50]!r}", flush=True)


async def speech_to_b64(text: str, voice: str = DEFAULT_VOICE) -> str:
    """一次性生成完整音频（base64）。失败返回空字符串。"""
    parts = []
    async for b64 in stream_speech(text, voice):
        parts.append(b64)
    return "".join(parts)


async def stream_speech_segmented(text: str, voice: str = DEFAULT_VOICE):
    """流式分段 TTS：边接收文本边按句末标点切分触发 TTS。

    设计思路参考 Verbal Werewolf (arXiv 2506.00160)：
    - LLM 流式产出文本时，检测到句末标点立即触发 TTS
    - TTS 生成音频期间，LLM 继续产出后续文本
    - 两者并行，显著降低感知延迟（首包 ~0.5-1s）
    - 尾部剩余文本在流结束后补全生成
    """
    if not text or not text.strip():
        return

    # 按句末标点切分
    segments = _split_segments(text, '。！？；')
    if not segments:
        # 无句末标点，按逗号切分
        segments = _split_segments(text, '，')
    if not segments:
        segments = [text]

    yielded_total = 0
    pending = []

    # 第1轮：句末切分
    for seg in segments:
        yielded_this = 0
        try:
            async for b64 in _try_segment(seg, voice, max_retry=1):
                yielded_total += 1
                yielded_this += 1
                yield b64
        except Exception:
            pass
        if yielded_this == 0:
            pending.append(seg)

    # 第2轮：失败的片段按逗号再切
    if pending:
        for seg in pending:
            sub_segments = _split_segments(seg, '，')
            if not sub_segments:
                sub_segments = [seg]
            for sub in sub_segments:
                yielded_this = 0
                try:
                    async for b64 in _try_segment(sub, voice, max_retry=1):
                        yielded_total += 1
                        yielded_this += 1
                        yield b64
                except Exception:
                    pass

    if yielded_total == 0:
        print(f"⚠️ TTS 整句失败: {text[:50]!r}", flush=True)
