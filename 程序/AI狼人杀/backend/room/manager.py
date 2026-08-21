"""房间管理：创建/加入/离开，人数管理，AI 补位标记。"""
import random
import string
import time
from dataclasses import dataclass, field


@dataclass
class Player:
    player_id: int
    nickname: str
    is_human: bool = True
    is_ai: bool = False
    connected: bool = True
    role: str = ""          # 游戏开始后分配（中文角色名）
    alive: bool = True
    seat: int = 0           # 座位号（发言顺序）
    model_name: str = ""    # AI 玩家绑定的模型配置名


@dataclass
class Room:
    code: str
    name: str
    max_players: int
    host_nickname: str
    players: dict[int, Player] = field(default_factory=dict)
    next_player_id: int = 1
    id_pool: list[int] = field(default_factory=list)  # 随机编号池（1..max_players 的随机排列）
    game_started: bool = False
    paused: bool = False
    paused_reason: str = ""
    game: object = None     # Game 实例（M2 引入）
    allowed_nicks: list[str] = field(default_factory=list)  # 房主批准的允许加入昵称列表
    join_mode: str = "open"     # "open"=任何人可加入, "private"=需房主批准
    created_at: float = field(default_factory=time.time)


class RoomManager:
    """内存房间管理（单进程）。"""

    def __init__(self):
        self.rooms: dict[str, Room] = {}

    @staticmethod
    def generate_code() -> str:
        while True:
            code = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
            # 排除易混淆字符
            code = code.replace("0", "O").replace("1", "I")
            if len(code) == 4:
                return code

    def create_room(self, host_nickname: str, max_players: int) -> Room:
        self.prune_stale_rooms()
        code = self.generate_code()
        while code in self.rooms:
            code = self.generate_code()
        room = Room(code=code, name=f"房间-{code}", max_players=max_players,
                    host_nickname=host_nickname)
        # 预生成 1..max_players 的随机编号池，房主拿第一个（编号随机，不再固定 1 号）
        pool = list(range(1, max_players + 1))
        random.shuffle(pool)
        room.id_pool = pool
        player = self.add_player(room, host_nickname, is_human=True)
        room.host_player_id = player.player_id
        self.rooms[code] = room
        return room

    def add_player(self, room: Room, nickname: str, is_human: bool = True) -> Player:
        # 从随机编号池取号
        if room.id_pool:
            player_id = room.id_pool.pop(0)
        else:
            player_id = room.next_player_id
            room.next_player_id += 1
        player = Player(player_id=player_id, nickname=nickname, is_human=is_human)
        player.is_ai = not is_human
        room.players[player.player_id] = player
        return player

    def get_room(self, code: str) -> Room | None:
        return self.rooms.get(code.upper())

    def remove_player(self, room: Room, player_id: int):
        room.players.pop(player_id, None)

    def prune_stale_rooms(self, now: float | None = None, max_idle_seconds: int = 3600) -> list[str]:
        """清理长时间无人连接且未开局的房间，返回被清理的房间码。"""
        now = time.time() if now is None else now
        stale = [
            code for code, room in self.rooms.items()
            if not room.game_started
            and not any(p.connected for p in room.players.values())
            and now - room.created_at >= max_idle_seconds
        ]
        for code in stale:
            self.rooms.pop(code, None)
        return stale

    def remove_room(self, code: str) -> Room | None:
        return self.rooms.pop(code.upper(), None)

    def find_player_by_nickname(self, room: Room, nickname: str) -> Player | None:
        for p in room.players.values():
            if p.nickname == nickname:
                return p
        return None

    def set_join_mode(self, room: Room, mode: str, approved_nicks: list[str] | None = None):
        """设置房间加入模式：open=公开，private=需批准。"""
        if mode not in ("open", "private"):
            return False
        room.join_mode = mode
        if approved_nicks is not None:
            room.allowed_nicks = approved_nicks
        return True

    def room_snapshot(self, room: Room) -> dict:
        """房间公开状态（不含角色等私密信息）。"""
        return {
            "code": room.code,
            "name": room.name,
            "max_players": room.max_players,
            "game_started": room.game_started,
            "paused": room.paused,
            "paused_reason": room.paused_reason,
            "join_mode": room.join_mode,
            "allowed_nicks": room.allowed_nicks,
            "players": [
                {
                    "player_id": p.player_id,
                    "nickname": p.nickname,
                    "is_ai": p.is_ai,
                    "connected": p.connected,
                    "is_host": p.player_id == room.host_player_id,
                }
                for p in sorted(room.players.values(), key=lambda x: x.player_id)
            ],
        }
