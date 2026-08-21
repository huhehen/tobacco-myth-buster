"""M4 人类玩家交互测试：人类通过 WebSocket 完成所有行动（夜晚/发言/投票）。

1 人类 + 8 AI（假 AI），人类依次完成：
- 夜晚行动（视角色而定）
- 白天发言
- 投票
直到游戏结束。
"""
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

PORT = 8131


def start_server():
    from backend.main import app
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


async def recv_type(ws, msg_type, timeout=30):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
        if msg["type"] == msg_type:
            return msg
    raise TimeoutError(f"等待 {msg_type} 超时")


async def drain_until(ws, msg_type, timeout=60):
    """持续接收并丢弃消息，直到收到目标类型。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
        except asyncio.TimeoutError:
            continue
        if msg["type"] == msg_type:
            return msg
    raise TimeoutError(f"等待 {msg_type} 超时")


async def test_human_game():
    human_role = {"role": ""}

    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as ws:
        await ws.send(json.dumps({"type": "create_room", "nickname": "小明", "player_count": 9}))
        resp = json.loads(await asyncio.wait_for(ws.recv(), 5))
        room_code = resp["room"]["code"]
        human_id = resp["player_id"]
        print(f"✅ 创建房间: {room_code}（人类编号 {human_id}）")

        # 开始游戏（只有房主一人 → AI 自动补满 8 人）
        await ws.send(json.dumps({"type": "start_game"}))
        started = await recv_type(ws, "game_started")
        role_msg = await recv_type(ws, "your_role")
        assert role_msg["player_id"] == human_id, f"角色应发给人类: {role_msg}"
        human_role["role"] = role_msg["role"]
        assert human_role["role"], "角色不应为空"
        print(f"✅ 游戏开始，人类角色: {human_role['role']}", flush=True)

        # 单一事件循环：接收消息并处理，直到游戏结束
        finished = {"value": False}
        action_count = {"n": 0}
        alive_set = set(range(1, 10))  # 跟踪存活玩家，回复合法目标

        async def handle_action(action):
            action_count["n"] += 1
            print(f"  行动[{action_count['n']}]: {action}", flush=True)
            valid = [p for p in sorted(alive_set) if p != human_id]
            fallback = valid[0] if valid else 2
            if action == "女巫救人":
                await ws.send(json.dumps({"type": "human_action", "action": action, "data": {"save": True}}))
            elif action == "猎人开枪":
                await ws.send(json.dumps({"type": "human_action", "action": action, "data": {"target_id": fallback}}))
            elif action == "发言":
                await ws.send(json.dumps({"type": "human_action", "action": action, "data": {"text": "我是好人！"}}))
            else:
                await ws.send(json.dumps({"type": "human_action", "action": action, "data": {"target_id": fallback}}))

        deadline = asyncio.get_running_loop().time() + 180
        while not finished["value"]:
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError(f"游戏 180 秒未结束（已处理 {action_count['n']} 个行动）")
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 10))
            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                break
            if msg["type"] == "game_over":
                print(f"🏁 游戏结束: {msg['winner']}", flush=True)
                finished["value"] = True
            elif msg["type"] == "human_action_req":
                # 定向发送验证：人类只应收到发给自己的行动请求
                assert msg["player_id"] == human_id, f"收到他人的行动请求: {msg}"
                await handle_action(msg["action"])
            elif msg["type"] == "night_result":
                alive_set.difference_update(msg.get("died_ids") or [])
            elif msg["type"] == "vote_result" and msg.get("eliminated_id"):
                alive_set.discard(msg["eliminated_id"])
            elif msg["type"] == "hunter_shot" and msg.get("target_id"):
                alive_set.discard(msg["target_id"])

        # 断言：游戏正常结束，且所有行动请求都定向发给人类本人
        assert finished["value"], "游戏未正常结束"
        assert human_role["role"], "未收到角色分配"
        print(f"✅ 人类角色: {human_role['role']}，共完成 {action_count['n']} 个行动（角色随机，行动次数取决于角色与存活情况）")
        print("✅ 定向发送验证通过：未收到任何他人的行动请求")


def test_human():
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    time.sleep(2)
    asyncio.run(test_human_game())
    print("\n🎉 M4 人类玩家交互测试通过")


if __name__ == "__main__":
    test_human()
