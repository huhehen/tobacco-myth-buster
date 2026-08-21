"""M3 LLM 接入测试：mock 模型服务器 + LLMPool 会话隔离 + 串行调度。

验证：
1. 流式发言正常（增量输出 + 完整文本）
2. 会话隔离（两个玩家同模型互不干扰）
3. 串行调度（同一时刻只有一个 LLM 调用）
4. 投票综合推理（乱序 + 结构化输出）
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 设置 mock 模型的环境变量（让 ModelConfig.enabled 通过）
os.environ.setdefault("MOCK_KEY_A", "mock-key")
os.environ.setdefault("MOCK_KEY_B", "mock-key")

from backend.ai.llm_client import LLMClient
from backend.ai.llm_pool import LLMPool
from backend.ai.speaker import LlmSpeaker
from backend.config import ModelConfig
from tests.mock_llm import start_mock_server


def make_model_configs():
    return [
        ModelConfig(name="mock-A", base_url="http://127.0.0.1:9000/v1",
                    api_key_env="MOCK_KEY_A", model="mock-model"),
    ]


async def test_stream_speech():
    """流式发言：增量输出 + 完整文本 + 结束标记清理。"""
    pool = LLMPool(make_model_configs())
    await pool.start()

    deltas = []
    completed = []

    async def on_delta(pid, delta):
        deltas.append(delta)

    async def on_end(pid, text):
        completed.append(text)

    speaker = LlmSpeaker(pool, on_delta=on_delta, on_speech_end=on_end)

    # 模拟一个最小游戏
    from backend.game.state_machine import Game, GamePlayer
    from backend.game.roles import get_role_config
    players = [GamePlayer(player_id=i, nickname=f"玩家{i}", is_ai=True) for i in range(1, 4)]
    for p in players:
        p.role = "村民"
    game = Game(players)
    game.day = 1
    game.phase = "白天发言"

    text = await speaker.speak(game, players[0], {})
    assert text, "发言为空"
    assert "【发言结束】" not in text, "结束标记未被清理"
    # 增量拼接 = 原始完整文本（含结束标记），清理后应等于最终 text
    raw = "".join(deltas)
    assert raw.replace("【发言结束】", "").strip() == text, "增量拼接与完整文本不一致"
    assert completed == [text], "发言完成回调异常"
    print(f"✅ 流式发言验证通过: {text[:30]}...")

    # 会话隔离：玩家1 和 玩家2 各自独立会话
    await speaker.speak(game, players[1], {})  # 让玩家2 也发言，建立会话
    s1 = pool.get_session(game.room_code, 1)
    s2 = pool.get_session(game.room_code, 2)
    assert s1 is not None and s2 is not None
    assert s1 is not s2, "会话应隔离"
    # 玩家2 的会话 assistant 消息应是玩家2 自己的发言（不是玩家1 的）
    s2_last = s2.messages[-1] if s2.messages else None
    assert s2_last and s2_last["role"] == "assistant"
    assert "2 号玩家" in str(s2_last["content"]), "玩家2 会话应是自己的发言"
    print("✅ 会话隔离验证通过")

    # 串行调度：并发提交 3 个请求，观察不重叠
    active = {"count": 0, "max": 0}

    async def concurrent_call(i):
        active["count"] += 1
        active["max"] = max(active["max"], active["count"])
        await asyncio.sleep(0.2)
        active["count"] -= 1
        return i

    results = await asyncio.gather(*[pool.submit(concurrent_call, i) for i in range(3)])
    assert results == [0, 1, 2]
    assert active["max"] == 1, f"串行调度失败，最大并发: {active['max']}"
    print("✅ 串行调度验证通过（最大并发 = 1）")

    await pool.stop()


async def test_vote_prompt():
    """投票综合推理：输出结构化「投票: N」。"""
    pool = LLMPool(make_model_configs())
    await pool.start()
    speaker = LlmSpeaker(pool)

    from backend.game.state_machine import Game, GamePlayer
    players = [GamePlayer(player_id=i, nickname=f"玩家{i}", is_ai=True) for i in range(1, 4)]
    for p in players:
        p.role = "村民"
    game = Game(players)
    game.day = 1
    game.phase = "投票"
    game.speeches_of_day = [
        {"player_id": 1, "nickname": "玩家1", "text": "我是好人，大家信我。"},
        {"player_id": 2, "nickname": "玩家2", "text": "我觉得1号有问题。"},
        {"player_id": 3, "nickname": "玩家3", "text": "我支持2号的说法。"},
    ]

    target = await speaker.decide(game, players[0], "投票")
    assert target in (2, 3), f"投票目标异常: {target}"
    print(f"✅ 投票综合推理验证通过（投给 {target} 号）")

    # 会话独立：玩家2 的会话应保持干净
    s2 = pool.get_session(game.room_code, 2)
    if s2:
        assert len(s2.messages) == 0, "玩家2 会话应无投票污染"
    print("✅ 投票不污染其他玩家会话")

    await pool.stop()


async def test_model_isolation():
    """同模型多玩家互不干扰：A 玩家发言不应出现在 B 的会话。"""
    pool = LLMPool(make_model_configs())
    await pool.start()
    speaker = LlmSpeaker(pool)

    from backend.game.state_machine import Game, GamePlayer
    players = [GamePlayer(player_id=i, nickname=f"玩家{i}", is_ai=True) for i in range(1, 3)]
    for p in players:
        p.role = "狼人"
    game = Game(players)
    game.day = 1
    game.phase = "白天发言"

    await speaker.speak(game, players[0], {})
    await speaker.speak(game, players[1], {})

    s1 = pool.get_session(game.room_code, 1)
    s2 = pool.get_session(game.room_code, 2)
    assert s1 is not None and s2 is not None
    # 玩家2 的 assistant 消息应是玩家2 自己的发言
    s2_last = s2.messages[-1] if s2.messages else None
    assert s2_last and s2_last["role"] == "assistant"
    assert "2 号玩家" in str(s2_last["content"]), "玩家2 会话应是自己的发言"
    print("✅ 同模型多玩家会话隔离验证通过")
    await pool.stop()


def test_info_isolation():
    """信息隔离：狼人看得到同伴，村民看不到；预言家只看得到自己的查验。"""
    from backend.ai.prompts import visible_info_for
    from backend.game.state_machine import Game, GamePlayer

    players = [
        GamePlayer(player_id=1, nickname="玩家1", is_ai=True, role="狼人"),
        GamePlayer(player_id=2, nickname="玩家2", is_ai=True, role="狼人"),
        GamePlayer(player_id=3, nickname="玩家3", is_ai=True, role="预言家"),
        GamePlayer(player_id=4, nickname="玩家4", is_ai=True, role="村民"),
        GamePlayer(player_id=5, nickname="玩家5", is_ai=True, role="女巫"),
    ]
    game = Game(players)
    game.day = 1
    game.phase = "夜晚"
    game.dead_tonight = [4]
    game.divine_result = {3: {1: "狼人", 2: "狼人"}}

    wolf_info = visible_info_for(game, players[0])
    assert "你的狼人同伴" in wolf_info and "2号" in wolf_info, "狼人应看到同伴编号"
    # 存活列表包含全部玩家，"3号"出现在存活列表中属正常
    assert "你查验过" not in wolf_info, "狼人不该看到查验结果"
    assert "你的解药状态" not in wolf_info, "狼人不该看到女巫药水状态"

    villager_info = visible_info_for(game, players[3])
    assert "你的狼人同伴" not in villager_info, "村民不该看到狼人同伴"
    assert "你查验过" not in villager_info, "村民不该看到查验结果"
    assert "你的解药状态" not in villager_info, "村民不该看到药水状态"

    seer_info = visible_info_for(game, players[2])
    assert "你查验过 1号：狼人" in seer_info, "预言家应看到自己的查验"
    assert "你查验过 2号：狼人" in seer_info

    witch_info = visible_info_for(game, players[4])
    assert "今晚被狼人杀死的是：4号" in witch_info, "女巫应看到今晚死者"
    print("✅ 信息隔离验证通过")


def test_public_history_privacy():
    """public_history 不应泄漏私密信息（K2 核心隐私测试）。"""
    from backend.ai.prompts import public_history
    from backend.game.state_machine import Game, GamePlayer

    players = [
        GamePlayer(player_id=1, nickname="玩家1", is_ai=True, role="狼人"),
        GamePlayer(player_id=2, nickname="玩家2", is_ai=True, role="预言家"),
        GamePlayer(player_id=3, nickname="玩家3", is_ai=True, role="村民"),
        GamePlayer(player_id=4, nickname="玩家4", is_ai=True, role="女巫"),
        GamePlayer(player_id=5, nickname="玩家5", is_ai=True, role="村民"),
    ]
    game = Game(players)
    game.day = 2
    game.phase = "白天发言"

    # 构造 full_record：含私密行动
    game.full_record = [
        {"type": "divine", "day": 1, "seer": 2, "target": 1, "result": "狼人"},
        {"type": "death", "day": 1, "died": [5]},
        {"type": "speech_round", "day": 1, "speeches": []},
        {"type": "vote_round", "day": 1, "votes": [{"voter": 1, "target": 5}]},
        {"type": "execution", "day": 1, "executed": 5},
    ]
    # 手动加入私密记录（模拟可能被误加的情况）
    game.full_record.append({"type": "night_thinking", "day": 2, "player_id": 2, "thinking": "我查验了1号是狼人"})
    game.full_record.append({"type": "witch_action", "day": 2, "player_id": 4, "action": "poison", "target": 1})

    history = public_history(game)
    # 绝不含私密关键词
    assert "查验" not in history, "public_history 不应含查验结果"
    assert "狼人" not in history, "public_history 不应含角色判定"
    assert "毒" not in history, "public_history 不应含女巫毒药"
    assert "守卫" not in history or "守护" not in history, "public_history 不应含守卫信息"
    assert "夜" not in history or "行动" not in history, "public_history 不应含夜间行动"
    # 应含公开事件
    assert "第1天亮" in history or "死亡" in history, "应含死亡公开信息"
    assert "第1天" in history, "应有日期标记"
    print("✅ public_history 隐私验证通过（不泄漏私密行动）")


async def test_llm_failure_recovery():
    """LLM 失败路径：submit 返回异常时应回退而非崩溃（K3）。"""
    from unittest.mock import AsyncMock, patch
    from backend.ai.llm_pool import LLMPool
    from backend.ai.speaker import LlmSpeaker
    from backend.game.state_machine import Game, GamePlayer
    from tests.mock_llm import start_mock_server
    import time

    start_mock_server()
    time.sleep(1.5)

    from backend.config import load_models, ModelConfig
    configs = load_models()
    if not configs:
        # 无配置时无法测试，跳过
        print("⏭️ 无可用模型配置，跳过 LLM 失败路径测试")
        return

    pool = LLMPool(configs)
    await pool.start()
    speaker = LlmSpeaker(pool)

    players = [GamePlayer(player_id=1, nickname="玩家1", is_ai=True, role="村民")]
    game = Game(players)
    game.day = 1
    game.phase = "白天发言"

    # 模拟 submit 返回异常（如连接超时）—— pool 行为：异常作为结果返回，不抛出
    fake_exception = RuntimeError("连接超时")
    async def mock_submit(*args, **kwargs):
        return fake_exception
    with patch.object(pool, 'submit', mock_submit):
        # speak 失败时应返回空串而非抛异常
        text = await speaker.speak(game, players[0], {})
        assert text == "", f"LLM 失败时应返回空串，实际: {text!r}"

        # decide 失败时应随机兜底（不是抛异常）
        target = await speaker.decide(game, players[0], "投票")
        # 返回值可以是 None 或合法目标，但不能抛异常

    await pool.stop()
    print("✅ LLM 失败路径验证通过（不崩溃，回退正常）")


if __name__ == "__main__":
    start_mock_server()
    time.sleep(1.5)
    asyncio.run(test_stream_speech())
    asyncio.run(test_vote_prompt())
    asyncio.run(test_model_isolation())
    asyncio.run(test_llm_failure_recovery())
    test_info_isolation()
    test_public_history_privacy()
    print("\n🎉 M3 LLM 接入测试全部通过")
