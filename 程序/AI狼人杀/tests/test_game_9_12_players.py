"""阶段1 回归：9/12 人局无 LLM 端到端测试。

PM 验收要求：必须自己加 1 条 9/12 人局无 LLM 端到端测试。
test_game.py 已有 6 人局，本文件专注 9 人局（M2 标准局）+ 12 人局（含守卫）。

每个测试独立可跑（自带 if __name__ == "__main__"），与项目约定一致。
"""
import asyncio
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.game.director import FakeSpeaker, GameDirector
from backend.game.roles import get_role_config
from backend.room.manager import Player, Room


def make_test_room(player_count: int, code: str) -> Room:
    room = Room(code=code, name=f"{player_count}人回归测试", max_players=player_count,
                host_nickname="小明")
    room.host_player_id = 1
    for i in range(player_count):
        pid = i + 1
        nickname = "小明" if pid == 1 else f"玩家{pid}"
        room.players[pid] = Player(player_id=pid, nickname=nickname,
                                   is_human=False, is_ai=True)
    return room


async def test_9_player_regression() -> None:
    """9 人局无 LLM 端到端：3 狼 + 1 预言家 + 1 女巫 + 1 猎人 + 3 村民。"""
    cfg = get_role_config(9)
    assert cfg == {"狼人": 3, "预言家": 1, "女巫": 1, "猎人": 1, "村民": 3}, cfg

    room = make_test_room(9, "REG9")
    events = []

    async def on_broadcast(code, msg, only=None):
        events.append(msg)

    director = GameDirector(room, on_broadcast)
    director.ai_speaker = FakeSpeaker([
        "我觉得 3 号很可疑，他发言太积极了。",
        "我同意上一位的看法，先观察一下。",
        "我是好人阵营，大家相信我。",
        "今晚的信息量很关键，大家仔细分析。",
        "我暂时不投，看后面的表现。",
    ])
    random.seed(42)
    await director.run()

    game = director.game
    assert game.winner in ("好人阵营", "狼人阵营"), f"9 人局应结束: {game.winner}"
    types = {e["type"] for e in events}
    for t in ("game_started", "night_result", "speech_turn", "vote_result", "game_over"):
        assert t in types, f"9 人局缺少事件: {t}"
    # 角色分配必须齐全
    roles = {p.role for p in game.players.values()}
    for required in ("狼人", "预言家", "女巫", "猎人", "村民"):
        assert required in roles, f"9 人局缺角色: {required}"
    print(f"✅ 9 人局回归通过，胜利方: {game.winner}，事件 {len(events)} 条")


async def test_12_player_regression() -> None:
    """12 人局无 LLM 端到端：4 狼 + 1 预言家 + 1 女巫 + 1 猎人 + 1 守卫 + 4 村民。"""
    cfg = get_role_config(12)
    assert cfg == {"狼人": 4, "预言家": 1, "女巫": 1, "猎人": 1, "守卫": 1, "村民": 4}, cfg

    room = make_test_room(12, "REG12")
    events = []

    async def on_broadcast(code, msg, only=None):
        events.append(msg)

    director = GameDirector(room, on_broadcast)
    director.ai_speaker = FakeSpeaker([
        "今天先听听大家的发言。",
        "我觉得 5 号发言有点问题。",
        "我是预言家，验了 7 号是好人。",
        "大家别急，慢慢分析。",
        "我支持把 5 号放出去。",
        "昨晚的信息很重要，大家要仔细想。",
    ])
    random.seed(12)
    await director.run()

    game = director.game
    assert game.winner in ("好人阵营", "狼人阵营"), f"12 人局应结束: {game.winner}"
    types = {e["type"] for e in events}
    for t in ("game_started", "night_result", "vote_result", "game_over"):
        assert t in types, f"12 人局缺少事件: {t}"
    # 守卫存在校验
    has_guard = any(p.role == "守卫" for p in game.players.values())
    assert has_guard, "12 人局必须配守卫"
    print(f"✅ 12 人局回归通过，胜利方: {game.winner}，事件 {len(events)} 条")


if __name__ == "__main__":
    asyncio.run(test_9_player_regression())
    asyncio.run(test_12_player_regression())
    print("\n🎉 9/12 人局回归测试全部通过")
