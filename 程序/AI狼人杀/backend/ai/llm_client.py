"""OpenAI 兼容 LLM 客户端：httpx 异步调用 /chat/completions，支持流式。

兼容 DeepSeek / Qwen(百炼) / 豆包 / GLM / Kimi 等所有提供 OpenAI 兼容端点的模型。
用户只需在 config/models.json 配置 base_url + api_key_env + model。
"""
import json

import httpx

TIMEOUT = 60  # 秒
MAX_RETRIES = 2  # 失败重试次数（含首次 = 最多 2 次调用）
POOL_LIMITS = httpx.Limits(max_connections=10, max_keepalive_connections=5)


class LLMError(Exception):
    pass


class LLMClient:
    """单个模型的 OpenAI 兼容客户端。"""

    def __init__(self, model_name: str, base_url: str, api_key: str, model: str):
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._client: httpx.AsyncClient | None = None

    @property
    def url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _get_client(self) -> httpx.AsyncClient:
        """复用持久化 AsyncClient，避免每次调用重建连接池/TLS 握手。"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=TIMEOUT, limits=POOL_LIMITS)
        return self._client

    async def aclose(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.8,
        max_tokens: int | None = None,
    ) -> str:
        """非流式调用，返回完整文本。max_tokens 默认不限制。"""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        headers = {"Authorization": f"Bearer {self.api_key}"}

        last_error = None
        client = self._get_client()
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.post(self.url, json=payload, headers=headers)
                if resp.status_code != 200:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    data = resp.json()
                    msg = data["choices"][0]["message"]
                    # 推理模型（如 Agnes flash）可能只给 reasoning_content 不给 content
                    return msg.get("content") or msg.get("reasoning_content") or ""
            except (httpx.HTTPError, LLMError, KeyError, json.JSONDecodeError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    await asyncio_sleep(1.0 * (attempt + 1))
        raise LLMError(f"模型「{self.model_name}」调用失败: {last_error}")

    async def chat_stream(self, messages: list[dict], temperature: float = 0.8) -> str:
        """流式调用：逐 chunk 返回文本增量，返回完整文本。"""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        last_error = None
        client = self._get_client()
        for attempt in range(MAX_RETRIES):
            try:
                async with client.stream("POST", self.url, json=payload, headers=headers) as resp:
                        if resp.status_code != 200:
                            body = await resp.aread()
                            raise LLMError(f"HTTP {resp.status_code}: {body[:200]}")
                        async for line in resp.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                delta = chunk["choices"][0]["delta"].get("content", "")
                            except (KeyError, json.JSONDecodeError):
                                continue
                            if delta:
                                yield delta
                return  # 成功：正常结束生成器
            except (httpx.HTTPError, LLMError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    await asyncio_sleep(1.0 * (attempt + 1))
        raise LLMError(f"模型「{self.model_name}」流式调用失败: {last_error}")


def asyncio_sleep(seconds: float):
    import asyncio

    return asyncio.sleep(seconds)
