"""M1 房间逻辑验证脚本：直接调用 RoomManager 测试核心逻辑。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.room.manager import RoomManager


def test_room_basic():
    rm = RoomManager()
    # 创建房间
    room = rm.create_room("小明", 9)
    assert room.code and len(room.code) == 4, f"房间码异常: {room.code}"
    assert len(room.players) == 1
    # 房主编号随机（不再是固定的 1 号）
    host_id = room.host_player_id
    assert 1 <= host_id <= 9, f"房主编号应在 1-9: {host_id}"
    print(f"✅ 创建房间成功，房间码 {room.code}，房主编号 {host_id}")

    # 加入房间（编号从随机池取，各不相同）
    p2 = rm.add_player(room, "小红", is_human=True)
    p3 = rm.add_player(room, "AI-小狼", is_human=False)
    assert p2.player_id != p3.player_id, "编号不应重复"
    assert 1 <= p2.player_id <= 9 and 1 <= p3.player_id <= 9
    assert p3.is_ai and not p3.is_human
    print("✅ 人类/AI 玩家加入成功（编号随机不重复）")

    # 人数限制（最多 9 人）
    for i in range(6):
        rm.add_player(room, f"p{i}", is_human=True)
    assert len(room.players) == 9
    print("✅ 人数达到上限")

    # 快照
    snap = rm.room_snapshot(room)
    assert snap["max_players"] == 9
    assert len(snap["players"]) == 9
    # 房主标记正确（编号随机，不在首位）
    host_in_snap = next((p for p in snap["players"] if p["is_host"]), None)
    assert host_in_snap is not None and host_in_snap["player_id"] == host_id
    print("✅ 房间快照正确")

    # 按昵称查找
    found = rm.find_player_by_nickname(room, "小红")
    assert found and found.player_id == p2.player_id
    print("✅ 按昵称查找成功")

    # 移除
    rm.remove_player(room, p3.player_id)
    assert len(room.players) == 8
    print("✅ 移除玩家成功")

    print("\n🎉 全部房间逻辑测试通过")


if __name__ == "__main__":
    test_room_basic()
