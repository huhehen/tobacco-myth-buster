"""LLM 会话池：每个 AI 玩家独立的对话会话 + 全局串行调度队列。

- 玩家会话隔离：每个 AI 玩家持有独立 messages[] 历史，同模型多玩家互不干扰
- 串行调度：全局 asyncio.Queue，同一时刻只有一个 LLM 调用在执行
- 模型分配：按配置顺序轮询分配给 AI 玩家
- 音色分配：从音色池轮询分配，让每个 AI 玩家有不同声音
"""
import asyncio
import json
from pathlib import Path

from ..config import ModelConfig
from .llm_client import LLMClient


class PlayerSession:
    """一个 AI 玩家的独立对话会话。"""

    def __init__(self, client: LLMClient):
        self.client = client
        self.messages: list[dict] = []

    def set_system_prompt(self, prompt: str):
        # 系统 prompt 是会话的基础，替换而非追加（重建会话时）
        self.messages = [{"role": "system", "content": prompt}]

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})


class LLMPool:
    """模型客户端 + 会话管理 + 串行调度 + 音色分配。"""

    # 默认音色池（从 models.json 读取）
    DEFAULT_VOICE_POOL = {
        "male": ["zh-CN-YunxiNeural", "zh-CN-YunyangNeural", "zh-CN-YunhaoNeural", "zh-CN-YunjianNeural"],
        "female": ["zh-CN-XiaoxiaoNeural", "zh-CN-XiaoyiNeural", "zh-CN-YunxiaNeural"],
    }

    def __init__(self, model_configs: list[ModelConfig]):
        self._model_configs = model_configs
        self.clients: list[LLMClient] = [
            LLMClient(m.name, m.base_url, m.api_key, m.model)
            for m in model_configs if m.enabled
        ]
        self.sessions: dict[tuple, PlayerSession] = {}
        self._queue: asyncio.Queue | None = None
        self._next_model = 0
        self._submit_timeout = 90  # 秒：串行队列提交的兜底超时（防永久挂起）
        self._voice_cache: dict[tuple, str] = {}  # (room_code, player_id) -> voice
        self._voice_index = 0  # 音色轮询索引
        self._voice_pool = self._load_voice_pool()

    async def start(self):
        self._queue = asyncio.Queue()
        # 启动单个消费 worker，保证全局串行
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self):
        if self._queue is not None:
            await self._queue.put(None)
            try:
                await asyncio.wait_for(self._worker_task, 10)
            except asyncio.TimeoutError:
                self._worker_task.cancel()
            self._queue = None
        for client in self.clients:
            await client.aclose()

    async def _worker(self):
        while True:
            item = await self._queue.get()
            if item is None:
                break
            task_type, args, kwargs, fut = item
            try:
                result = await task_type(*args, **kwargs)
            except asyncio.CancelledError:
                # 任务被取消：结果置为异常，worker 自身继续存活
                result = RuntimeError("任务已取消")
            except Exception as e:
                result = e
            try:
                if not fut.done():
                    fut.set_result(result)
            except (asyncio.InvalidStateError, RuntimeError):
                pass

    async def submit(self, task_type, *args, **kwargs):
        """提交任务到串行队列，等待完成。带兜底超时，防止队列无消费者时永久挂起。"""
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        try:
            await self._queue.put([task_type, args, kwargs, fut])
        except AttributeError:
            raise RuntimeError("LLM 池未启动")
        try:
            return await asyncio.wait_for(fut, self._submit_timeout)
        except asyncio.TimeoutError:
            raise RuntimeError("LLM 调用超时")

    # ---------- 会话管理 ----------

    def assign_model(self, room_code: str, player_id: int) -> LLMClient:
        """为 AI 玩家轮询分配一个模型（若已有会话则复用）。会话按 (房间码, 玩家号) 隔离。"""
        key = (room_code, player_id)
        if key in self.sessions:
            return self.sessions[key].client
        client = self.clients[self._next_model % len(self.clients)]
        self._next_model += 1
        session = PlayerSession(client)
        self.sessions[key] = session
        return client

    def get_session(self, room_code: str, player_id: int) -> PlayerSession | None:
        return self.sessions.get((room_code, player_id))

    def _load_voice_pool(self) -> list[str]:
        """从 models.json 加载音色池，未配置则使用默认池。"""
        from ..config import MODELS_FILE
        if MODELS_FILE.exists():
            try:
                data = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
                pool = data.get("voice_pool", {})
                voices = []
                for key in ("male", "female"):
                    voices.extend(pool.get(key, []))
                if voices:
                    return voices
            except Exception:
                pass
        return self.DEFAULT_VOICE_POOL

    def assign_voice(self, room_code: str, player_id: int) -> str:
        """为 AI 玩家分配音色（按玩家 ID 轮询不同音色）。"""
        key = (room_code, player_id)
        if key in self._voice_cache:
            return self._voice_cache[key]

        # 轮询音色池
        voices = self._voice_pool
        if not voices:
            voices = ["zh-CN-XiaoxiaoNeural"]

        voice = voices[self._voice_index % len(voices)]
        self._voice_index += 1
        self._voice_cache[key] = voice
        return voice

    def get_tts_voice(self, room_code: str, player_id: int) -> str:
        """返回玩家绑定模型的音色（优先使用模型配置，否则从音色池分配）。"""
        session = self.sessions.get((room_code, player_id))
        if session:
            for mc in self._model_configs:
                if mc.enabled and session.client.model_name == mc.name and mc.tts_voice:
                    return mc.tts_voice
        # 未配置模型音色时，从音色池分配
        return self.assign_voice(room_code, player_id)

    def cleanup_room(self, room_code: str):
        """释放一个房间的会话与音色缓存，防止游戏结束后长期驻留内存。"""
        for key in [k for k in self.sessions if k[0] == room_code]:
            del self.sessions[key]
        for key in [k for k in self._voice_cache if k[0] == room_code]:
            del self._voice_cache[key]

    def has_models(self) -> bool:
        return len(self.clients) > 0
