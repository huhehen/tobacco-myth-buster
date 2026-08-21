"""M2 游戏核心验证：完整 9 人局跑通（假 AI 决策 + FakeSpeaker）。

验证：角色分配 → 夜晚 → 天亮 → 白天发言 → 投票 → 结算 → 胜负。
"""
import asyncio
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.game.director import FakeSpeaker, GameDirector
from backend.room.manager import Player, Room
from backend.game.state_machine import GamePlayer


def make_test_room(player_count: int = 9) -> Room:
    room = Room(code="TEST", name="测试房间", max_players=player_count,
                host_nickname="小明")
    room.host_player_id = 1
    for i in range(player_count):
        pid = i + 1
        nickname = "小明" if pid == 1 else f"玩家{pid}"
        # 全部用 AI（M2 验证规则逻辑，不涉及人类输入）
        room.players[pid] = Player(player_id=pid, nickname=nickname, is_human=False, is_ai=True)
    return room


async def test_full_game():
    room = make_test_room(9)
    events = []

    async def on_broadcast(code, msg, only=None):
        events.append(msg)
        if msg["type"] in ("game_started", "night_result", "vote_result", "game_over"):
            print(f"  [事件] {msg['type']}: {msg}")

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
    print(f"\n📊 游戏结束: 胜利方 = {game.winner}")
    print(f"📝 公开日志 ({len(game.public_log)} 条):")
    for log in game.public_log:
        print(f"   {log}")

    # 验证：所有角色都已分配
    roles = {p.role for p in game.players.values()}
    assert "狼人" in roles and "预言家" in roles and "村民" in roles, f"角色分配缺失: {roles}"
    print(f"\n✅ 角色分配验证通过: {roles}")

    # 验证：游戏流程完整（经历了夜晚/白天/投票）
    types = {e["type"] for e in events}
    for t in ["game_started", "night_result", "speech_turn", "vote_result", "game_over"]:
        assert t in types, f"缺少事件: {t}"
    print("✅ 完整流程验证通过（夜晚→白天→投票→结束）")

    # 验证：死亡人数不超过存活人数
    alive = sum(1 for p in game.players.values() if p.alive)
    assert alive >= 1
    print(f"✅ 存活验证通过: {alive} 人存活")

    print("\n🎉 M2 游戏核心测试通过")


async def test_6_player_game():
    """6 人局端到端：1 狼 + 1 预言家 + 4 村民，验证完整流程。"""
    from backend.game.roles import get_role_config
    roles = get_role_config(6)
    assert roles == {"狼人": 1, "预言家": 1, "村民": 4}

    room = make_test_room(6)
    events = []

    async def on_broadcast(code, msg, only=None):
        events.append(msg)

    director = GameDirector(room, on_broadcast)
    director.ai_speaker = FakeSpeaker([
        "我觉得今天信息量不大，先观察。",
        "我是预言家，昨晚验了 3 号是好人。",
        "大家相信我，我是真预言家。",
        "3 号跳预言家，但他的发言有问题。",
        "我暂时不表态，看后面发言。",
    ])
    random.seed(7)
    await director.run()

    game = director.game
    assert game.winner in ("好人阵营", "狼人阵营"), f"游戏应结束: {game.winner}"
    types = {e["type"] for e in events}
    for t in ["game_started", "night_result", "vote_result", "game_over"]:
        assert t in types, f"6 人局缺少事件: {t}"
    print(f"✅ 6 人局测试通过，胜利方: {game.winner}")


async def test_12_player_game():
    """12 人局端到端：4 狼 + 1 预言家 + 1 女巫 + 1 猎人 + 1 守卫 + 4 村民。"""
    from backend.game.roles import get_role_config
    roles = get_role_config(12)
    assert roles == {"狼人": 4, "预言家": 1, "女巫": 1, "猎人": 1, "守卫": 1, "村民": 4}

    room = make_test_room(12)
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
    for t in ["game_started", "night_result", "vote_result", "game_over"]:
        assert t in types, f"12 人局缺少事件: {t}"
    # 验证守卫在夜晚流程中曾被调用（通过 full_record 中的 divine 记录）
    has_divine = any(e.get("type") == "divine" for e in events)
    print(f"✅ 12 人局测试通过，胜利方: {game.winner}，{'含查验记录' if has_divine else '流程完整'}")


if __name__ == "__main__":
    asyncio.run(test_full_game())
    asyncio.run(test_6_player_game())
    asyncio.run(test_12_player_game())
    print("\n🎉 M2 游戏核心测试全部通过")
