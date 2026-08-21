"""M3 WebSocket 集成测试：创建房间 → 开始游戏 → 假 AI 完整局。"""
import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path

import uvicorn
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 禁用真实模型（.env 里的 Key 不覆盖已有环境变量），保证测试走 FakeSpeaker
os.environ.setdefault("NVIDIA_API_KEY", "")
os.environ.setdefault("AGNES_API_KEY", "")

PORT = 8129


def start_server():
    from backend.main import app
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


async def recv_until(ws, msg_type, timeout=30):
    """接收消息直到匹配类型。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
        if msg["type"] == msg_type:
            return msg
    raise TimeoutError(f"等待 {msg_type} 超时")


async def test_game_via_ws():
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws:
        # 创建房间
        await ws.send(json.dumps({"type": "create_room", "nickname": "小明", "player_count": 9}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
        assert resp["type"] == "room_joined"
        room_code = resp["room"]["code"]
        player1_id = resp["player_id"]
        print(f"✅ 创建房间: {room_code}（房主编号 {player1_id}）")

        # 加入第二名玩家（小红）
        async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws2:
            await ws2.send(json.dumps({"type": "join_room", "nickname": "小红", "room_code": room_code}))
            resp2 = json.loads(await asyncio.wait_for(ws2.recv(), 5))
            assert resp2["type"] == "room_joined"
            player2_id = resp2["player_id"]
            # ws1 收到 players 广播
            bcast = json.loads(await asyncio.wait_for(ws.recv(), 5))
            assert bcast["type"] == "room_players"

            # 开始游戏（房主）
            await ws.send(json.dumps({"type": "start_game"}))
            started = await recv_until(ws, "game_started")
            assert len(started["players"]) == 9, f"应有 9 个玩家: {len(started['players'])}"
            print("✅ 游戏开始，9 名玩家就位")

            # ws2 也应收到游戏开始
            started2 = await recv_until(ws2, "game_started")
            assert len(started2["players"]) == 9
            print("✅ 玩家 2 也收到游戏开始")

            # 角色为私密推送：各收到自己的角色
            role1 = await recv_until(ws, "your_role")
            assert role1["player_id"] == player1_id
            assert role1["role"]
            role2 = await recv_until(ws2, "your_role")
            assert role2["player_id"] == player2_id
            assert role2["role"]
            print(f"✅ 角色私密推送成功（玩家{player1_id}={role1['role']}，玩家{player2_id}={role2['role']}）")

            # 等待游戏结束：并发读取两个连接（避免单连接洪流饿死另一连接）
            by_id = {player1_id: ws, player2_id: ws2}
            alive = set(range(1, 10))  # 跟踪存活玩家，回复合法目标
            queue = asyncio.Queue()

            async def reader(w):
                while True:
                    try:
                        queue.put_nowait(await w.recv())
                    except Exception:
                        break

            t1 = asyncio.create_task(reader(ws))
            t2 = asyncio.create_task(reader(ws2))
            deadline = asyncio.get_running_loop().time() + 180
            over = None
            try:
                while asyncio.get_running_loop().time() < deadline:
                    try:
                        raw = await asyncio.wait_for(queue.get(), 3)
                    except asyncio.TimeoutError:
                        continue
                    msg = json.loads(raw)
                    if msg["type"] == "game_over":
                        over = msg
                        break
                    # 跟踪死亡
                    if msg["type"] == "night_result":
                        alive.difference_update(msg.get("died_ids") or [])
                    elif msg["type"] == "vote_result" and msg.get("eliminated_id"):
                        alive.discard(msg["eliminated_id"])
                    elif msg["type"] == "hunter_shot" and msg.get("target_id"):
                        alive.discard(msg["target_id"])
                    if msg["type"] == "human_action_req":
                        action = msg["action"]
                        target_ws = by_id[msg["player_id"]]
                        valid = [p for p in sorted(alive) if p != msg["player_id"]]
                        if action == "女巫救人":
                            await target_ws.send(json.dumps({"type": "human_action", "action": action, "data": {"save": True}}))
                        elif action == "发言":
                            await target_ws.send(json.dumps({"type": "human_action", "action": action, "data": {"text": "我是好人！"}}))
                        elif action == "投票" and valid:
                            await target_ws.send(json.dumps({"type": "human_action", "action": action, "data": {"target_id": valid[0]}}))
                        elif valid:
                            await target_ws.send(json.dumps({"type": "human_action", "action": action, "data": {"target_id": valid[0]}}))
            finally:
                t1.cancel()
                t2.cancel()
            if over:
                print(f"✅ 游戏结束: {over['winner']}")
            else:
                print("❌ 游戏 180 秒未结束（可能卡住）")
                raise TimeoutError("游戏未结束")

        # 收集过程中收到的消息类型
        print("🎉 WebSocket 游戏流程测试通过")


def test_ws_game():
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    time.sleep(2)
    asyncio.run(test_game_via_ws())
    print("\n🎉 M3 WebSocket 游戏流程全部通过")


if __name__ == "__main__":
    test_ws_game()
