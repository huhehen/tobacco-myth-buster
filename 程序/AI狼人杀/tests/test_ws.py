"""M1 WebSocket 集成测试（真实服务器 + websockets 客户端）：
创建房间、加入、断线暂停、重连恢复。
"""
import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import uvicorn
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PORT = 8123


def start_server():
    from backend.main import app
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


def recv_json(ws, timeout=5):
    """接收一条 JSON 消息（跳过无关类型）。"""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(asyncio.wait_for(ws.recv(), timeout))


def test_ws_flow():
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    time.sleep(2)  # 等待服务器启动

    async def run():
        async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws1:
            await ws1.send(json.dumps({"type": "create_room", "nickname": "小明", "player_count": 9}))
            resp = json.loads(await asyncio.wait_for(ws1.recv(), 5))
            assert resp["type"] == "room_joined", f"收到: {resp}"
            room_code = resp["room"]["code"]
            player1_id = resp["player_id"]
            assert 1 <= player1_id <= 9, f"房主编号应在 1-9: {player1_id}"
            print(f"✅ 创建房间成功: {room_code}（房主编号 {player1_id}）")

            # 玩家 2 加入
            async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws2:
                await ws2.send(json.dumps({"type": "join_room", "nickname": "小红", "room_code": room_code}))
                resp2 = json.loads(await asyncio.wait_for(ws2.recv(), 5))
                assert resp2["type"] == "room_joined"
                player2_id = resp2["player_id"]
                assert 1 <= player2_id <= 9 and player2_id != player1_id, f"编号应不同: {player2_id}"
                # ws1 收到 players 广播
                bcast = json.loads(await asyncio.wait_for(ws1.recv(), 5))
                assert bcast["type"] == "room_players"
                assert len(bcast["room"]["players"]) == 2
                print("✅ 玩家 2 加入 + 广播成功")

                # ws2 断开 → ws1 收到断线广播
                await ws2.close()
                disc = json.loads(await asyncio.wait_for(ws1.recv(), 5))
                assert disc["type"] == "player_disconnected", f"收到: {disc}"
                assert disc["nickname"] == "小红"
                print("✅ 断线广播成功")

            # 小红重连（同名 → 同一 player_id）
            async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws3:
                await ws3.send(json.dumps({"type": "join_room", "nickname": "小红", "room_code": room_code}))
                resp3 = json.loads(await asyncio.wait_for(ws3.recv(), 5))
                assert resp3["type"] == "room_joined"
                assert resp3["player_id"] == player2_id, f"重连应恢复同一身份: {resp3}"
                print("✅ 重连恢复同一身份成功")

                # 房间不可重复昵称（在线状态）
                async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws4:
                    await ws4.send(json.dumps({"type": "join_room", "nickname": "小红", "room_code": room_code}))
                    resp4 = json.loads(await asyncio.wait_for(ws4.recv(), 5))
                    assert resp4["type"] == "error"
                    assert "已被使用" in resp4["message"]
                    print("✅ 重复昵称拒绝成功")

    asyncio.run(run())
    print("\n🎉 全部 WebSocket 测试通过")


if __name__ == "__main__":
    test_ws_flow()
