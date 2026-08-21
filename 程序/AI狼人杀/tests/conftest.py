"""全局 pytest 配置：让 async def 测试无需装饰器即可被 pytest-asyncio 自动识别。

阶段1 验收要求 `pytest tests/test_game.py tests/test_game_good_win.py -v` 0 fail，
这两个文件里的测试是裸 async def（项目原本用 asyncio.run 直接执行）。
asyncio_mode=auto 让 pytest-asyncio 自动把它们当 async 测试运行。
"""
import pytest

pytest_plugins = ["pytest_asyncio"]


def pytest_configure(config):
    """强制 asyncio_mode=auto，不依赖 pytest.ini。"""
    config.option.asyncio_mode = "auto"
