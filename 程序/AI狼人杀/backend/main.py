"""FastAPI 入口：静态文件服务 + WebSocket 路由 + 启动信息打印。"""
import asyncio
import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .ai.llm_pool import LLMPool
from .config import FRONTEND_DIR, MODELS, check_models_and_print, load_env_file
from .room.manager import RoomManager
from .room.ws_handler import ConnectionManager, WsRouter

load_env_file()

CLEANUP_INTERVAL = 300  # 秒：定期清理无人房间


@asynccontextmanager
async def lifespan(app: FastAPI):
    """后台定期回收无人房间及其 LLM 会话，避免长期运行内存膨胀。"""

    async def cleanup_loop():
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL)
            removed = ROOM_MANAGER.prune_stale_rooms()
            for code in removed:
                LLM_POOL.cleanup_room(code)

    task = asyncio.create_task(cleanup_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await LLM_POOL.stop()


app = FastAPI(title="AI 狼人杀", lifespan=lifespan)

ROOM_MANAGER = RoomManager()
LLM_POOL = LLMPool(MODELS)
CONN_MANAGER = ConnectionManager(ROOM_MANAGER)
WS_ROUTER = WsRouter(CONN_MANAGER, llm_pool=LLM_POOL)

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")


@app.get("/")
async def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/api/models")
async def api_models():
    """给前端提供可用模型列表（仅已启用的）。"""
    return {"models": [
        {"name": m.name, "model": m.model, "tts_voice": m.tts_voice}
        for m in MODELS if m.enabled
    ]}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await WS_ROUTER.handle(websocket)


def get_lan_ip() -> str:
    """获取本机局域网 IP：遍历所有网卡，优先选择私有网段地址。"""
    try:
        import socket as _socket

        hostname = _socket.gethostname()
        for addr in _socket.getaddrinfo(hostname, None):
            ip = addr[4][0]
            if is_private_lan_ip(ip):
                return ip
    except OSError:
        pass
    # 兜底：UDP 探测路由表
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if is_private_lan_ip(ip):
            return ip
    except OSError:
        pass
    return "127.0.0.1"


def is_private_lan_ip(ip: str) -> bool:
    """判断是否为局域网私有 IP（排除回环、Tailscale 100.x、VPN 等虚拟网段）。"""
    if ip.startswith("127.") or ip.startswith("100."):
        return False
    if ip.startswith("192.168."):
        return True
    if ip.startswith("10."):
        return True
    if ip.startswith("172."):
        try:
            return 16 <= int(ip.split(".")[1]) <= 31
        except ValueError:
            return False
    return False


def print_startup_banner():
    ip = get_lan_ip()
    print("========================================")
    print("  🎮 狼人杀服务器已启动")
    print("  ──────────────────────────────────")
    print(f"  本机访问:   http://127.0.0.1:8000")
    print(f"  局域网:     http://{ip}:8000")
    print("  ──────────────────────────────────")
    print("  把局域网链接发给同一 WiFi 下的朋友即可加入游戏")
    print("========================================")


def main():
    import uvicorn

    check_models_and_print(MODELS)
    print_startup_banner()
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
