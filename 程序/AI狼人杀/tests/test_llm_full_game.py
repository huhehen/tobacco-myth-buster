"""M3 集成测试：LLM 驱动的完整 9 人局（mock 模型服务器）。

验证：AI 玩家用 LLM 发言/决策，完整跑完一局。
"""
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("MOCK_KEY_A", "mock-key")
os.environ.setdefault("MOCK_KEY_B", "mock-key")

from backend.ai.llm_pool import LLMPool
from backend.ai.speaker import LlmSpeaker
from backend.config import ModelConfig
from backend.game.director import GameDirector
from backend.game.state_machine import Game, GamePlayer
from backend.room.manager import Player, Room
from tests.mock_llm import start_mock_server


def make_room(player_count: int = 9) -> Room:
    room = Room(code="LLMG", name="LLM局", max_players=player_count, host_nickname="小明")
    room.host_player_id = 1
    for i in range(player_count):
        pid = i + 1
        # 全部 AI（验证 LLM 流程，不涉及人类输入）
        room.players[pid] = Player(player_id=pid, nickname=f"玩家{pid}",
                                   is_human=False, is_ai=True)
    return room


async def test_llm_full_game():
    room = make_room(9)
    events = []
    speech_count = {"n": 0}

    async def on_broadcast(code, msg, only=None):
        events.append(msg)
        if msg["type"] == "game_over":
            print(f"\n🏁 游戏结束: {msg['winner']}")
        if msg["type"] == "speech_delta" and msg.get("final"):
            speech_count["n"] += 1

    pool = LLMPool([
        ModelConfig("mock-A", "http://127.0.0.1:9000/v1", "MOCK_KEY_A", "mock-model"),
        ModelConfig("mock-B", "http://127.0.0.1:9000/v1", "MOCK_KEY_B", "mock-model"),
    ])
    await pool.start()

    director = GameDirector(room, on_broadcast)
    speaker = LlmSpeaker(pool)
    speaker.room_code = room.code
    director.ai_speaker = speaker

    print("🎮 开始 LLM 完整局（8 AI + 1 占位人类）...")
    await director.run()

    # 验证
    types = {e["type"] for e in events}
    assert "game_started" in types and "game_over" in types
    assert speech_count["n"] > 0, "没有 AI 发言"
    print(f"✅ AI 发言次数: {speech_count['n']}")

    # 验证 LLM 会话：参与过发言/决策的 AI 玩家都有独立会话
    # （开局即死且从未发言/投票的玩家没有会话是正常行为）
    ai_ids = [pid for pid in room.players if room.players[pid].is_ai]
    sessions = {pid: pool.get_session(room.code, pid) for pid in ai_ids}
    active = [pid for pid, s in sessions.items() if s is not None]
    assert len(active) >= 5, f"仅 {len(active)} 个玩家有会话（应至少 5 个）"
    print(f"✅ {len(active)} 个 AI 玩家有独立会话（未参与行动: {[pid for pid in ai_ids if pid not in active]}）")

    await pool.stop()
    print("\n🎉 M3 LLM 完整局测试通过")


if __name__ == "__main__":
    start_mock_server()
    time.sleep(1.5)
    asyncio.run(test_llm_full_game())
