"""LLM 客户端性能基准：串行非流式调用延迟与 Python 内存峰值。

用法（在项目根目录）：
    .venv/bin/python tools/bench_llm.py [calls]

结果用于对比“每次调用新建 httpx.AsyncClient”与“复用持久化客户端”。
"""
import asyncio
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
from tests.mock_llm import start_mock_server

MESSAGES = [
    {"role": "system", "content": "基准测试"},
    {"role": "user", "content": "请回复一句话。"},
]


async def main():
    calls = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    start_mock_server()
    await asyncio.sleep(1.0)

    pool = LLMPool([
        ModelConfig("mock-A", "http://127.0.0.1:9000/v1", "MOCK_KEY_A", "mock-model"),
    ])
    await pool.start()
    client = pool.clients[0]

    for _ in range(3):
        await pool.submit(client.chat, MESSAGES)

    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    for _ in range(calls):
        text = await pool.submit(client.chat, MESSAGES)
        if not text:
            raise RuntimeError("mock 调用返回空文本")
    t1 = time.perf_counter()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    elapsed = t1 - t0
    print(f"calls={calls} total={elapsed:.4f}s avg={elapsed / calls * 1000:.2f}ms "
          f"tracemalloc_current={current / 1024:.1f}KiB tracemalloc_peak={peak / 1024:.1f}KiB")
    await pool.stop()


if __name__ == "__main__":
    asyncio.run(main())
