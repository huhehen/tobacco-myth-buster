"""ConnectionManager 的无网络发送队列测试。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.room.manager import RoomManager
from backend.room.ws_handler import ConnectionManager


class _State:
    name = "CONNECTED"


class FakeWebSocket:
    client_state = _State()

    def __init__(self, gate=None):
        self.gate = gate
        self.sent = []

    async def send_text(self, message):
        if self.gate:
            await self.gate.wait()
        self.sent.append(message)


def _room_with_two_connections():
    rooms = RoomManager()
    room = rooms.create_room("甲", 6)
    other = rooms.add_player(room, "乙", is_human=True)
    manager = ConnectionManager(rooms)
    slow_gate = asyncio.Event()
    slow = FakeWebSocket(slow_gate)
    fast = FakeWebSocket()
    manager.register(room.code, next(
        pid for pid, player in room.players.items() if player.nickname == "甲"
    ), slow)
    manager.register(room.code, other.player_id, fast)
    return manager, room, slow_gate, slow, fast


async def _wait_for(predicate):
    for _ in range(100):
        if predicate():
            return
        await asyncio.sleep(0.001)
    raise AssertionError("后台发送未在预期时间内完成")


async def test_slow_connection_does_not_block_broadcast():
    manager, room, slow_gate, slow, fast = _room_with_two_connections()
    try:
        started = asyncio.get_running_loop().time()
        await manager.broadcast_room(room.code, {
            "type": "speech_delta", "player_id": 1, "text": "甲", "final": False,
        })
        elapsed = asyncio.get_running_loop().time() - started
        assert elapsed < 0.05, f"广播被慢连接阻塞了 {elapsed:.3f}s"
        await _wait_for(lambda: len(fast.sent) == 1)
        assert not slow.sent
        slow_gate.set()
    finally:
        for player_id in room.players:
            await manager.disconnect(room.code, player_id)


async def test_each_connection_keeps_order_and_final():
    manager, room, slow_gate, slow, fast = _room_with_two_connections()
    messages = [
        {"type": "speech_delta", "player_id": 1, "text": "一", "final": False},
        {"type": "speech_delta", "player_id": 1, "text": "二", "final": False},
        {"type": "speech_delta", "player_id": 1, "text": "", "final": True},
        {"type": "speech_end", "player_id": 1},
    ]
    try:
        for message in messages:
            await manager.broadcast_room(room.code, message)
        await _wait_for(lambda: len(fast.sent) == len(messages))
        assert fast.sent == [
            '{"type": "speech_delta", "player_id": 1, "text": "一", "final": false}',
            '{"type": "speech_delta", "player_id": 1, "text": "二", "final": false}',
            '{"type": "speech_delta", "player_id": 1, "text": "", "final": true}',
            '{"type": "speech_end", "player_id": 1}',
        ]
        slow_gate.set()
        await _wait_for(lambda: len(slow.sent) == len(messages))
        assert slow.sent[-2:] == [
            '{"type": "speech_delta", "player_id": 1, "text": "", "final": true}',
            '{"type": "speech_end", "player_id": 1}',
        ]
    finally:
        for player_id in room.players:
            await manager.disconnect(room.code, player_id)


def main():
    asyncio.run(test_slow_connection_does_not_block_broadcast())
    print("✅ 慢连接不会阻塞广播")
    asyncio.run(test_each_connection_keeps_order_and_final())
    print("✅ 单连接顺序保持且 final 未丢")


if __name__ == "__main__":
    main()
