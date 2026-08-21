"""阶段1 回归测试：9/12 人局无 LLM 端到端 (FakeSpeaker)。

C1 验收：FakeSpeaker.speak 的 speech_order 参数必须在 9/12 人局实际被调用过而不报错。
9 人局 / 12 人局两个 case 都必须 0 fail 跑通。
"""
import asyncio
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.game.director import FakeSpeaker, GameDirector
from backend.room.manager import Player, Room


def make_test_room(player_count: int) -> Room:
    room = Room(
        code="P1", name="阶段1", max_players=player_count, host_nickname="小明"
    )
    room.host_player_id = 1
    for i in range(player_count):
        pid = i + 1
        nickname = "小明" if pid == 1 else f"玩家{pid}"
        room.players[pid] = Player(
            player_id=pid, nickname=nickname, is_human=False, is_ai=True
        )
    return room


# 9 人局话术池（避免 12 人局话术不够）
SEED_9 = [
    "我觉得 3 号很可疑，他发言太积极了。",
    "我同意上一位的看法，先观察一下。",
    "我是好人阵营，大家相信我。",
    "今晚的信息量很关键，大家仔细分析。",
    "我暂时不投，看后面的表现。",
    "5 号发言太少，不像是好人。",
    "我支持放逐 6 号。",
]

SEED_12 = [
    "今天先听听大家的发言。",
    "我觉得 5 号发言有点问题。",
    "我是预言家，验了 7 号是好人。",
    "大家别急，慢慢分析。",
    "我支持把 5 号放出去。",
    "昨晚的信息很重要，大家要仔细想。",
    "我是女巫，今晚用解药救人。",
    "守卫请守好今晚。",
    "猎人亮身份，狼人你看着办。",
]


async def _run_one(player_count: int, seeds: list[str], seed: int) -> tuple[str, list[str]]:
    room = make_test_room(player_count)
    events: list[dict] = []

    async def on_broadcast(code, msg, only=None):
        events.append(msg)

    director = GameDirector(room, on_broadcast)
    director.ai_speaker = FakeSpeaker(seeds)
    random.seed(seed)
    await director.run()

    types = {e["type"] for e in events}
    return director.game.winner, sorted(types)


@pytest.mark.asyncio
async def test_phase1_9_player_no_llm():
    """9 人局无 LLM 端到端 (C1 回归：speech_order 必须被 FakeSpeaker 接受)."""
    winner, types = await _run_one(9, SEED_9, seed=42)
    assert winner in ("好人阵营", "狼人阵营"), f"9 人局应结束: {winner}"
    for t in ("game_started", "night_result", "vote_result", "game_over"):
        assert t in types, f"9 人局缺少事件: {t}"
    assert "speech_turn" in types, "9 人局应经历发言环节"


@pytest.mark.asyncio
async def test_phase1_12_player_no_llm():
    """12 人局无 LLM 端到端 (C1 回归：speech_order 必须被 FakeSpeaker 接受)."""
    winner, types = await _run_one(12, SEED_12, seed=12)
    assert winner in ("好人阵营", "狼人阵营"), f"12 人局应结束: {winner}"
    for t in ("game_started", "night_result", "vote_result", "game_over"):
        assert t in types, f"12 人局缺少事件: {t}"
    assert "speech_turn" in types, "12 人局应经历发言环节"
