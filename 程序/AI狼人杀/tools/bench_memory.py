"""房间 / LLM 会话长期内存基准。

模拟“房间创建 → 游戏结束 → 遗留对象”的生命周期，统计：
- RoomManager.rooms 残留数量
- LLMPool.sessions / voice_cache 残留数量
- tracemalloc 当前占用

在清理逻辑存在时会自动执行清理并输出 after 指标，否则只输出 before。
"""
import gc
import os
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("MOCK_KEY_A", "mock-key")

from backend.ai.llm_pool import LLMPool
from backend.config import ModelConfig
from backend.room.manager import RoomManager

ROOMS = 300
PLAYERS = 12
SESSION_ROOMS = 100


def kb(n: int) -> str:
    return f"{n / 1024:.1f}KiB"


def main():
    tracemalloc.start()
    rm = RoomManager()
    for i in range(ROOMS):
        room = rm.create_room(f"房主{i}", PLAYERS)
        for j in range(PLAYERS - 1):
            rm.add_player(room, f"玩家{i}-{j}")
        room.game_started = True
        room.game_started = False
        room.director = object()
    gc.collect()
    rooms_before = len(rm.rooms)
    mem_before = tracemalloc.get_traced_memory()[0]

    rooms_after = rooms_before
    if hasattr(rm, "prune_stale_rooms"):
        rm.prune_stale_rooms(now=time.time() + 3600)
        gc.collect()
        rooms_after = len(rm.rooms)
    mem_after_rooms = tracemalloc.get_traced_memory()[0]

    pool = LLMPool([
        ModelConfig("mock-A", "http://127.0.0.1:9000/v1", "MOCK_KEY_A", "mock-model"),
    ])
    for room_i in range(SESSION_ROOMS):
        code = f"BENCH{room_i}"
        for pid in range(1, PLAYERS + 1):
            pool.assign_model(code, pid)
            pool.assign_voice(code, pid)
    gc.collect()
    sessions_before = len(pool.sessions)
    voices_before = len(pool._voice_cache)
    mem_before_sessions = tracemalloc.get_traced_memory()[0]

    sessions_after = sessions_before
    voices_after = voices_before
    if hasattr(pool, "cleanup_room"):
        for room_i in range(SESSION_ROOMS):
            pool.cleanup_room(f"BENCH{room_i}")
        gc.collect()
        sessions_after = len(pool.sessions)
        voices_after = len(pool._voice_cache)
    mem_after_sessions = tracemalloc.get_traced_memory()[0]

    print(f"rooms before={rooms_before} after={rooms_after} mem={kb(mem_before)} -> {kb(mem_after_rooms)}")
    print(f"sessions before={sessions_before} after={sessions_after} "
          f"voices before={voices_before} after={voices_after} "
          f"mem={kb(mem_before_sessions)} -> {kb(mem_after_sessions)}")


if __name__ == "__main__":
    main()
