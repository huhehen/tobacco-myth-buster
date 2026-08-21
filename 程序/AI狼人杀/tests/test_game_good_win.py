"""M2 补充验证：好人阵营胜利的完整局。"""
import asyncio
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.game.director import FakeSpeaker, GameDirector
from backend.game.roles import is_wolf
from backend.room.manager import Player, Room


def make_test_room(player_count: int = 9) -> Room:
    room = Room(code="GOOD", name="好人局", max_players=player_count, host_nickname="小明")
    room.host_player_id = 1
    for i in range(player_count):
        pid = i + 1
        # 全部用 AI（验证规则逻辑）
        room.players[pid] = Player(player_id=pid, nickname=f"玩家{pid}", is_human=False, is_ai=True)
    return room


class GoodWinsSpeaker(FakeSpeaker):
    """好人必胜的假 AI：狼人自杀、投票先投狼人。"""

    def __init__(self, game_provider):
        super().__init__(["我是好人，请大家相信我。"])
        self._game = game_provider

    async def speak(self, game, player, visible_info, on_streaming_delta=None, prior_speeches=None):
        return "我是好人，大家团结起来。"


async def test_good_win():
    room = make_test_room(9)
    events = []
    winner = {"value": None}

    async def on_broadcast(code, msg, only=None):
        events.append(msg)
        if msg["type"] == "game_over":
            winner["value"] = msg["winner"]

    director = GameDirector(room, on_broadcast)
    director.ai_speaker = FakeSpeaker(["我是好人，请大家相信我。"])

    # 好人必胜策略：狼人每晚杀自己人，投票也投狼人
    async def good_ai(game, player, action):
        if action == "狼人提议":
            # 狼人杀自己人（加速狼人灭亡）
            wolves = [p for p in game.alive_ids() if is_wolf(game.players[p].role) and p != player.player_id]
            return wolves[0] if wolves else game.get_alive_except({player.player_id})[0]
        if action == "投票":
            wolves = [p for p in game.alive_ids() if is_wolf(game.players[p].role)]
            return wolves[0] if wolves else game.get_alive_except({player.player_id})[0]
        if action == "预言家查验":
            return game.get_alive_except({player.player_id})[0]
        if action == "女巫救人":
            return True
        if action == "女巫毒人":
            wolves = [p for p in game.alive_ids() if is_wolf(game.players[p].role)]
            return wolves[0] if wolves else game.get_alive_except({player.player_id})[0]
        return game.get_alive_except({player.player_id})[0]

    director.ai_act = good_ai
    random.seed(7)
    await director.run()

    assert winner["value"] == "好人阵营", f"预期好人胜，实际: {winner['value']}"
    print(f"✅ 好人阵营胜利验证通过: {winner['value']}")

    # 验证日志完整
    types = {e["type"] for e in events}
    assert "game_over" in types and "vote_result" in types
    print(f"✅ 事件流完整（{len(events)} 条事件）")
    print("\n🎉 好人胜利局测试通过")


if __name__ == "__main__":
    asyncio.run(test_good_win())
