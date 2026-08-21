"""M5 集成测试：游戏中 TTS 音频消息通过 WebSocket 广播（mock LLM 环境）。

注意：本测试通过内存注入 mock 模型配置，不覆盖磁盘上的 config/models.json。
"""
import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path

import uvicorn
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("MOCK_KEY_A", "mock-key")

PORT = 8138

from tests.mock_llm import start_mock_server

import backend.config as config_module


def start_server():
    # 用 mock 模型配置（注入内存，不覆盖磁盘上的 models.json）
    config_module.load_env_file()
    mock_configs = [
        config_module.ModelConfig(
            name="mock-A",
            base_url="http://127.0.0.1:9000/v1",
            api_key_env="MOCK_KEY_A",
            model="mock-model",
            tts_voice="zh-CN-XiaoxiaoNeural",
        )
    ]
    config_module.MODELS.clear()
    config_module.MODELS.extend(mock_configs)

    from backend.main import app, LLM_POOL
    # 用新配置重建 LLM 池
    LLM_POOL._model_configs = config_module.MODELS
    from backend.ai.llm_client import LLMClient
    LLM_POOL.clients = [
        LLMClient(m.name, m.base_url, m.api_key, m.model)
        for m in config_module.MODELS if m.enabled
    ]
    LLM_POOL.sessions = {}
    print(f"[测试] LLM_POOL clients: {len(LLM_POOL.clients)}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


async def test_tts_ws():
    audio_count = {"n": 0}
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws:
        await ws.send(json.dumps({"type": "create_room", "nickname": "小明", "player_count": 9}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
        room_code = resp["room"]["code"]

        await ws.send(json.dumps({"type": "start_game"}))
        print("✅ 游戏开始，等待 TTS 音频...")

        deadline = asyncio.get_running_loop().time() + 90
        ai_spoken = {"done": False}
        while asyncio.get_running_loop().time() < deadline:
            msg = json.loads(await asyncio.wait_for(ws.recv(), 10))
            if msg["type"] == "human_action_req":
                # 自动回复人类行动，避免卡住
                action = msg["action"]
                if action == "女巫救人":
                    await ws.send(json.dumps({"type": "human_action", "action": action, "data": {"save": True}}))
                elif action == "发言":
                    await ws.send(json.dumps({"type": "human_action", "action": action, "data": {"text": "我是好人！"}}))
                elif action == "投票":
                    await ws.send(json.dumps({"type": "human_action", "action": action, "data": {"target_id": 2}}))
                else:
                    await ws.send(json.dumps({"type": "human_action", "action": action, "data": {"target_id": 2}}))
            elif msg["type"] == "speech_delta" and msg.get("final") and msg["player_id"] != 1:
                # AI 完整发言（player_id != 1 是 AI，1 是人类房主）
                ai_spoken["done"] = True
                print(f"✅ 收到 AI 完整发言: {msg['text'][:30]}...")
            elif msg["type"] == "speech_audio":
                audio_count["n"] += 1
                if audio_count["n"] == 1:
                    print(f"✅ 收到首个 TTS 音频 chunk（{len(msg['audio'])} base64 字符）")
            elif msg["type"] == "game_over":
                break
            # AI 发言完成后，再等 TTS 音频出现
            if ai_spoken["done"] and audio_count["n"] > 0:
                break

    print(f"✅ 共收到 {audio_count['n']} 个音频 chunk")
    assert audio_count["n"] > 0, "未收到任何 TTS 音频"
    print("🎉 M5 TTS WebSocket 集成测试通过")


def test_tts():
    start_mock_server()
    time.sleep(1)
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    time.sleep(2)
    asyncio.run(test_tts_ws())


if __name__ == "__main__":
    test_tts()
