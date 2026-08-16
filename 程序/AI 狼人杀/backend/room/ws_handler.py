"""WebSocket 消息路由 + 断线检测 + 暂停/恢复。

消息协议（全部 JSON，中文语义）：
客户端 → 服务端：
  {"type": "create_room", "nickname": str, "player_count": int}
  {"type": "join_room", "nickname": str, "room_code": str}
  {"type": "leave_room"}
  {"type": "start_game"}
  {"type": "human_action", "action": str, "data": {...}}
服务端 → 客户端：
  {"type": "room_joined", "room": {...}, "player_id": int, "snapshot"?: {...}}   # snapshot 仅游戏内重连
  {"type": "room_players", "room": {...}}
  {"type": "your_role", "player_id": int, "role": str, "camp": str}              # 私密
  {"type": "game_started", "players": [...]}
  {"type": "phase_changed", "phase": str, "day": int}
  {"type": "narrator", "text": str, "private"?: bool}                            # 旁白（含 TTS）
  {"type": "night_result", "day": int, "died_ids": [...], "died_names": [...], "narrator_text": str}
  {"type": "divine_result", "player_id": int, "target_id": int, "camp": str}     # 仅本人
  {"type": "guard_result", "player_id": int, "target_id": int}                   # 仅本人
  {"type": "witch_action", "player_id": int, "action": str, "target_id"?: int}   # 仅本人
  {"type": "wolf_partners", "player_id": int, "partner_ids": [...]}              # 仅狼人本人
  {"type": "human_action_req", "player_id": int, "action": str}                  # 仅本人
  {"type": "action_invalid", "player_id": int, "message": str}                   # 仅本人
  {"type": "speech_turn", "player_id": int, "nickname": str}
  {"type": "speech_delta", "player_id": int, "text": str, "final": bool}
  {"type": "speech_end", "player_id": int}
  {"type": "speech_audio", "player_id": int, "audio": str}                       # base64 mp3
  {"type": "vote_update", "voter_id": int, "target_id": int}
  {"type": "vote_result", "eliminated_id": int|None, "eliminated_name": str|None, "narrator_text": str}
  {"type": "hunter_shot", "hunter_id": int, "target_id": int, "narrator_text": str}
  {"type": "you_died", "player_id": int}                                          # 仅本人：死亡瞬间触发上帝视角
  {"type": "decision_log_history", "logs": [...]}                                 # 仅死亡玩家：一次性补发历史
  {"type": "decision_log", "log": {...}}                                          # 仅死亡玩家：实时推送单条决策日志
  {"type": "game_paused", "reason": str}
  {"type": "player_disconnected", "nickname": str}
  {"type": "player_reconnected", "nickname": str}
  {"type": "game_over", "winner": str}
  {"type": "error", "message": str}
"""
import asyncio
from collections import deque
import json
from typing import Optional, Protocol

from fastapi import WebSocket

from ..game.director import FakeSpeaker, GameDirector
from .manager import Room, RoomManager

# 单条 WebSocket 发送超时（秒）：防慢客户端背压冻结游戏循环
SEND_TIMEOUT = 8
# 每个连接最多积压的非最终流式片段数；旧片段可丢，最终片段和其他消息不可丢。
MAX_PENDING_SPEECH_DELTAS = 64


def validate_nickname(nickname: str) -> bool:
    """昵称校验：非空、长度 ≤ 16、不含换行/引号（防 prompt 注入）。"""
    if not nickname or len(nickname) > 16:
        return False
    return not any(c in nickname for c in "\n\r\"'<>")


class _SendableWebSocket(Protocol):
    async def send_text(self, data: str) -> None: ...


class ConnectionManager:
    """管理所有 WebSocket 连接与房间绑定。"""

    def __init__(self, room_manager: RoomManager):
        self.room_manager = room_manager
        # (room_code, player_id) -> websocket（同一玩家重连时覆盖旧连接）
        self.connections: dict[tuple, _SendableWebSocket] = {}
        self._outbound: dict[tuple, _OutboundQueue] = {}

    def key(self, room_code: str, player_id: int) -> tuple:
        return (room_code, player_id)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()

    def register(self, room_code: str, player_id: int, websocket: _SendableWebSocket):
        """绑定连接，并为它创建独立、有序的后台发送队列。"""
        key = self.key(room_code, player_id)
        previous = self._outbound.pop(key, None)
        if previous:
            previous.close()
        self.connections[key] = websocket
        self._outbound[key] = _OutboundQueue(websocket)

    async def disconnect(self, room_code: str, player_id: int):
        """玩家断开：标记掉线，若游戏进行中则暂停并广播。"""
        key = self.key(room_code, player_id)
        if key not in self.connections:
            return
        self.connections.pop(key, None)
        outbound = self._outbound.pop(key, None)
        if outbound:
            outbound.close()
        room = self.room_manager.get_room(room_code)
        if not room:
            return
        player = room.players.get(player_id)
        if not player:
            return
        player.connected = False
        await self.broadcast_room(room_code, {
            "type": "player_disconnected",
            "nickname": player.nickname,
        })
        # 游戏进行中断线 → 暂停（用户要求：断开时游戏暂停）
        if room.game_started and not room.paused:
            room.paused = True
            room.paused_reason = f"{player.nickname} 已掉线"
            await self.broadcast_room(room_code, {
                "type": "game_paused",
                "reason": room.paused_reason,
            })

    async def send(self, room_code: str, player_id: int, data: dict):
        outbound = self._outbound.get(self.key(room_code, player_id))
        if outbound:
            outbound.enqueue(data)

    async def broadcast_room(self, room_code: str, data: dict, only: list[int] | None = None):
        """向房间内已连接玩家并发广播（only 指定玩家时定向发送）。"""
        room = self.room_manager.get_room(room_code)
        if not room:
            return
        for player_id in room.players:
            if only is not None and player_id not in only:
                continue
            outbound = self._outbound.get(self.key(room_code, player_id))
            if outbound:
                outbound.enqueue(data)


class _OutboundQueue:
    """单连接 FIFO：慢客户端只能阻塞自己的 worker。"""

    def __init__(self, websocket: _SendableWebSocket):
        self.websocket = websocket
        self.pending: deque[dict] = deque()
        self._wake = asyncio.Event()
        self._closed = False
        self._task = asyncio.create_task(self._run())

    def enqueue(self, data: dict):
        if self._closed:
            return
        if data.get("type") == "speech_delta" and not data.get("final"):
            self._trim_speech_deltas()
        self.pending.append(data)
        self._wake.set()

    def _trim_speech_deltas(self):
        deltas = sum(
            item.get("type") == "speech_delta" and not item.get("final")
            for item in self.pending
        )
        if deltas < MAX_PENDING_SPEECH_DELTAS:
            return
        for item in self.pending:
            if item.get("type") == "speech_delta" and not item.get("final"):
                self.pending.remove(item)
                return

    async def _run(self):
        try:
            while True:
                while self.pending:
                    data = self.pending.popleft()
                    try:
                        await asyncio.wait_for(
                            self.websocket.send_text(json.dumps(data, ensure_ascii=False)),
                            SEND_TIMEOUT,
                        )
                    except Exception:
                        pass
                self._wake.clear()
                if self.pending:
                    self._wake.set()
                await self._wake.wait()
        except asyncio.CancelledError:
            pass

    def close(self):
        self._closed = True
        self._task.cancel()


class WsRouter:
    """WebSocket 消息路由。"""

    def __init__(self, conn_manager: ConnectionManager, llm_pool=None):
        self.cm = conn_manager
        self.rooms = conn_manager.room_manager
        self.llm_pool = llm_pool

    async def handle(self, websocket: WebSocket):
        await self.cm.connect(websocket)
        current: Optional[tuple] = None  # (room_code, player_id)
        try:
            while True:
                text = await websocket.receive_text()
                try:
                    msg = json.loads(text)
                except json.JSONDecodeError:
                    await websocket.send_text(json.dumps(
                        {"type": "error", "message": "消息格式错误"}, ensure_ascii=False))
                    continue
                current = await self.route(websocket, msg, current)
        except Exception:
            pass
        finally:
            if current is not None:
                await self.cm.disconnect(current[0], current[1])

    async def route(self, websocket: WebSocket, msg: dict, current: Optional[tuple]) -> Optional[tuple]:
        msg_type = msg.get("type")

        if msg_type == "create_room":
            nickname = (msg.get("nickname") or "").strip()
            if not validate_nickname(nickname):
                await websocket.send_text(json.dumps(
                    {"type": "error", "message": "昵称需为 1-16 个字符，不含引号和换行"}, ensure_ascii=False))
                return current
            try:
                player_count = int(msg.get("player_count") or 9)
            except (TypeError, ValueError):
                player_count = 9
            if player_count not in (6, 9, 12):
                player_count = 9
            room = self.rooms.create_room(nickname, player_count)
            player = room.players[room.host_player_id]
            await websocket.send_text(json.dumps({
                "type": "room_joined",
                "player_id": player.player_id,
                "room": self.rooms.room_snapshot(room),
            }, ensure_ascii=False))
            self.cm.register(room.code, player.player_id, websocket)
            return (room.code, player.player_id)

        if msg_type == "join_room":
            nickname = (msg.get("nickname") or "").strip()
            room_code = (msg.get("room_code") or "").strip().upper()
            room = self.rooms.get_room(room_code)
            if not room:
                await websocket.send_text(json.dumps(
                    {"type": "error", "message": "房间不存在"}, ensure_ascii=False))
                return current
            if not validate_nickname(nickname):
                await websocket.send_text(json.dumps(
                    {"type": "error", "message": "昵称需为 1-16 个字符，不含引号和换行"}, ensure_ascii=False))
                return current
            existing = self.rooms.find_player_by_nickname(room, nickname)
            snapshot = None
            # 同名掉线玩家 → 视为重连（含游戏内重连，优先于"游戏已开始"拒绝）
            if existing and not existing.connected:
                player = existing
                player.connected = True
                if room.game_started and getattr(room, "director", None):
                    snapshot = room.director.snapshot(player.player_id)
                    room.paused = False
                    room.paused_reason = ""
            elif existing and existing.connected:
                await websocket.send_text(json.dumps(
                    {"type": "error", "message": "该昵称已被使用"}, ensure_ascii=False))
                return current
            else:
                if room.game_started:
                    await websocket.send_text(json.dumps(
                        {"type": "error", "message": "游戏已开始，无法加入"}, ensure_ascii=False))
                    return current
                if len(room.players) >= room.max_players:
                    await websocket.send_text(json.dumps(
                        {"type": "error", "message": "房间已满"}, ensure_ascii=False))
                    return current
                # 安全检查：private 模式需房主批准
                if getattr(room, "join_mode", "open") == "private":
                    approved = getattr(room, "allowed_nicks", [])
                    if nickname not in approved:
                        await websocket.send_text(json.dumps(
                        {"type": "error", "message": f'该房间为私密房间，昵称"{nickname}"未被房主批准，无法加入'}, ensure_ascii=False))
                        return current
                player = self.rooms.add_player(room, nickname, is_human=True)
            await websocket.send_text(json.dumps({
                "type": "room_joined",
                "player_id": player.player_id,
                "room": self.rooms.room_snapshot(room),
                **({"snapshot": snapshot} if snapshot else {}),
            }, ensure_ascii=False))
            self.cm.register(room.code, player.player_id, websocket)
            await self.cm.broadcast_room(room.code, {
                "type": "room_players",
                "room": self.rooms.room_snapshot(room),
            })
            if existing and room.game_started:
                await self.cm.broadcast_room(room.code, {
                    "type": "player_reconnected",
                    "nickname": player.nickname,
                })
            return (room.code, player.player_id)

        if msg_type == "start_game":
            if current is None:
                return current
            room_code, player_id = current
            room = self.rooms.get_room(room_code)
            if not room:
                return current
            if player_id != room.host_player_id:
                await websocket.send_text(json.dumps(
                    {"type": "error", "message": "只有房主可以开始游戏"}, ensure_ascii=False))
                return current
            if room.game_started:
                await websocket.send_text(json.dumps(
                    {"type": "error", "message": "游戏已经开始"}, ensure_ascii=False))
                return current
            if len(room.players) < 1:
                await websocket.send_text(json.dumps(
                    {"type": "error", "message": "房间没有玩家"}, ensure_ascii=False))
                return current
            # 创建 AI 玩家补满空位
            self._fill_ai_players(room)
            room.game_started = True
            room.paused = False
            room.paused_reason = ""
            # 启动游戏（后台任务）
            asyncio.create_task(self._run_game(room))
            return current

        if msg_type == "human_action":
            """人类玩家行动提交：{action, data}"""
            if current is None:
                return current
            room = self.rooms.get_room(current[0])
            director = getattr(room, "director", None) if room else None
            if director:
                director.submit_human_action(
                    current[1],
                    msg.get("action", ""),
                    msg.get("data", {}),
                )
            return current

        if msg_type == "leave_room":
            if current is not None:
                await self.cm.disconnect(current[0], current[1])
            return None

        if msg_type == "set_room_mode":
            """房主设置房间加入模式：open=公开，private=私密（需批准昵称）。"""
            if current is None:
                return current
            room_code, player_id = current
            room = self.rooms.get_room(room_code)
            if not room:
                return current
            if player_id != room.host_player_id:
                await websocket.send_text(json.dumps(
                    {"type": "error", "message": "只有房主可以设置房间模式"}, ensure_ascii=False))
                return current
            if room.game_started:
                await websocket.send_text(json.dumps(
                    {"type": "error", "message": "游戏进行中无法修改房间模式"}, ensure_ascii=False))
                return current
            mode = (msg.get("mode") or "").strip().lower()
            approved = msg.get("approved_nicks") or []
            if mode not in ("open", "private"):
                await websocket.send_text(json.dumps(
                    {"type": "error", "message": f"无效的模式: {mode}，请使用 open 或 private"}, ensure_ascii=False))
                return current
            self.rooms.set_join_mode(room, mode, approved if isinstance(approved, list) else [])
            await websocket.send_text(json.dumps({
                "type": "room_mode_set",
                "mode": room.join_mode,
                "allowed_nicks": room.allowed_nicks,
            }, ensure_ascii=False))
            await self.cm.broadcast_room(room.code, {
                "type": "room_players",
                "room": self.rooms.room_snapshot(room),
            })
            return current

        if msg_type == "play_again":
            """再来一局：保留房间，重置游戏状态后重新开局（仅房主）。"""
            if current is None:
                return current
            room_code, player_id = current
            room = self.rooms.get_room(room_code)
            if not room:
                return current
            if player_id != room.host_player_id:
                await websocket.send_text(json.dumps(
                    {"type": "error", "message": "只有房主可以重新开始"}, ensure_ascii=False))
                return current
            if room.game_started:
                # 游戏进行中不允许重置
                await websocket.send_text(json.dumps(
                    {"type": "error", "message": "游戏进行中"}, ensure_ascii=False))
                return current
            # 重置：保留玩家与房间码，重新补 AI 并开局
            room.game_started = False
            room.paused = False
            room.paused_reason = ""
            room.director = None
            self._fill_ai_players(room)
            room.game_started = True
            asyncio.create_task(self._run_game(room))
            return current

        await websocket.send_text(json.dumps(
            {"type": "error", "message": f"未知消息类型: {msg_type}"}, ensure_ascii=False))
        return current

    def _fill_ai_players(self, room: Room):
        """创建 AI 玩家补满空位（中文昵称 + 轮询分配模型）。昵称用尽时加数字后缀。"""
        AI_NAMES = ["阿狼", "小狐", "狸猫", "夜枭", "白鸦", "花豹", "灰鸽", "银鹿", "赤狐", "黑熊"]
        used = {p.nickname for p in room.players.values()}
        need = room.max_players - len(room.players)
        idx = 0
        while need > 0:
            name = AI_NAMES[idx % len(AI_NAMES)]
            if idx >= len(AI_NAMES):
                name = f"{name}{idx // len(AI_NAMES) + 1}"
            if name not in used:
                self.rooms.add_player(room, name, is_human=False)
                used.add(name)
                need -= 1
            idx += 1

    async def _run_game(self, room: Room):
        """后台运行游戏。"""
        from ..ai.llm_pool import LLMPool
        from ..ai.speaker import LlmSpeaker
        from ..config import TTS_ENABLED

        async def broadcast(code, msg, only=None):
            await self.cm.broadcast_room(code, msg, only=only)

        # TTS 默认关闭（edge-tts 不稳定）；TTS_ENABLED=1 时启用语音播报
        # 关键：on_tts 用 fire-and-forget 模式，让 TTS 后台异步执行
        # 否则 await stream_speech 会阻塞 LLM 流式输出
        async def _do_tts(player_id, text_chunk):
            from ..ai.tts import stream_speech_segmented
            voice = (
                self.llm_pool.get_tts_voice(room.code, player_id)
                if self.llm_pool else "zh-CN-XiaoxiaoNeural"
            )
            async for b64_chunk in stream_speech_segmented(text_chunk, voice):
                await self.cm.broadcast_room(room.code, {
                    "type": "speech_audio",
                    "player_id": player_id,
                    "audio": b64_chunk,
                })

        async def on_tts(player_id, text_chunk):
            if not TTS_ENABLED:
                return
            # fire-and-forget：立即返回，不阻塞 LLM 流
            asyncio.create_task(_do_tts(player_id, text_chunk))

        async def on_narrator(code, text, voice, only):
            if not TTS_ENABLED:
                return
            from ..ai.tts import stream_speech

            async def _narrate():
                parts = []
                async for b64 in stream_speech(text, voice):
                    parts.append(b64)
                for b64 in parts:
                    await self.cm.broadcast_room(room.code, {
                        "type": "speech_audio",
                        "player_id": 0,
                        "audio": b64,
                    }, only=only)
            asyncio.create_task(_narrate())

        director = GameDirector(room, broadcast, on_narrator=on_narrator, on_tts=on_tts)

        # LLM 池（全局单例，避免每局重建）
        if self.llm_pool is None:
            from ..main import MODELS
            self.llm_pool = LLMPool(MODELS)
        if self.llm_pool._queue is None:
            await self.llm_pool.start()

        if self.llm_pool.has_models():
            speaker = LlmSpeaker(self.llm_pool)
            speaker.room_code = room.code
            director.ai_speaker = speaker
        else:
            # 无模型配置：使用假发言（固定话术）保证可玩
            director.ai_speaker = FakeSpeaker(["我是 AI 玩家，请多指教。"])

        room.director = director
        try:
            await director.run()
        except Exception as e:
            await self.cm.broadcast_room(room.code, {
                "type": "error",
                "message": f"游戏运行出错: {e}",
            })
        finally:
            # 游戏结束或出错后清理房间状态，允许重新开局
            room.paused = False
            room.paused_reason = ""
            room.game_started = False
            room.director = None
            if self.llm_pool is not None:
                self.llm_pool.cleanup_room(room.code)
