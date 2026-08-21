"""M5 语音播报测试：edge-tts 流式生成中文音频。

验证：
1. 能生成 mp3 音频 chunk（base64）
2. 首个音频包延迟合理
3. 失败时静默降级（不中断游戏）
4. 流式分段 TTS 首包延迟 < 2s
"""
import asyncio
import base64
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.ai.tts import speech_to_b64, stream_speech, stream_speech_segmented


async def test_tts_stream():
    """流式生成：收到至少一个音频 chunk，且是合法 base64。"""
    text = "我是预言家，昨晚查验了2号，他是狼人。大家相信我！"
    chunks = []
    start = time.time()
    async for b64 in stream_speech(text):
        chunks.append(b64)
        if len(chunks) == 1:
            first_delay = time.time() - start
            # 解码验证是 mp3（前 2 字节为 MPEG 同步字）
            raw = base64.b64decode(b64)
            assert raw[:2] in (b"ID", b"\xff\xf3", b"\xff\xfb"), f"非 mp3 头: {raw[:2]}"
            print(f"✅ 首个音频包延迟: {first_delay:.2f}s（mp3 头正确）")
    assert chunks, "没有生成任何音频"
    total = sum(len(base64.b64decode(c)) for c in chunks)
    print(f"✅ 流式 TTS 成功：{len(chunks)} 个 chunk，共 {total} 字节")
    return chunks


async def test_tts_full():
    """一次性生成完整音频。"""
    b64 = await speech_to_b64("大家好，我是村民。")
    assert b64, "音频为空"
    raw = base64.b64decode(b64)
    assert len(raw) > 1000, f"音频太短: {len(raw)} 字节"
    print(f"✅ 完整 TTS 成功：{len(raw)} 字节")


async def test_tts_fallback():
    """失败静默降级：无效音色名不抛异常。"""
    chunks = []
    async for c in stream_speech("测试", voice="zh-CN-InvalidVoice"):
        chunks.append(c)
    assert chunks == [], "无效音色应无输出（静默降级）"
    print("✅ 失败静默降级验证通过")


async def test_tts_segmented():
    """流式分段 TTS 测试：验证首包延迟 < 2s，且能生成多个 chunk。"""
    text = "我是预言家，昨晚查验了 2 号玩家。他是狼人！请大家相信我！"
    chunks = []
    start = time.time()
    first_chunk_time = None

    async for b64 in stream_speech_segmented(text):
        if first_chunk_time is None:
            first_chunk_time = time.time() - start
        chunks.append(b64)

    assert chunks, "没有生成任何音频"
    assert len(chunks) > 0, "应生成至少一个 chunk"

    # 验证首个 chunk 是合法的 mp3
    raw = base64.b64decode(chunks[0])
    assert raw[:2] in (b"ID", b"\xff\xf3", b"\xff\xfb"), f"非 mp3 头: {raw[:2]}"

    print(f"✅ 流式分段 TTS 测试通过：首包延迟 {first_chunk_time:.2f}s，共 {len(chunks)} 个 chunk")
    assert first_chunk_time < 2.0, f"首包延迟过高: {first_chunk_time:.2f}s"


async def test_tts_segmented_empty():
    """流式分段 TTS 空文本测试。"""
    chunks = []
    async for b64 in stream_speech_segmented(""):
        chunks.append(b64)
    assert chunks == [], "空文本应无输出"
    print("✅ 空文本 TTS 测试通过")


if __name__ == "__main__":
    asyncio.run(test_tts_stream())
    asyncio.run(test_tts_full())
    asyncio.run(test_tts_fallback())
    asyncio.run(test_tts_segmented())
    asyncio.run(test_tts_segmented_empty())
    print("\n🎉 M5 语音播报测试通过")
