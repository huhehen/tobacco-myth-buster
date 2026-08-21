"""Mock OpenAI 兼容 LLM 服务器（用于本地测试，无真实 API Key）。

模拟流式 /chat/completions 响应。
"""
import asyncio
import json
import re
import threading

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()

SPEECHES = [
    "我觉得2号发言有点反常，他一直在转移话题。大家怎么看？【发言结束】",
    "我是好人，昨天我就怀疑3号了，他说话前后矛盾。【发言结束】",
    "先别急，我们分析一下昨晚的情况再说。我觉得大家应该多听听预言家的意见。【发言结束】",
]

_speech_idx = 0


@app.post("/v1/chat/completions")
async def chat(request: Request):
    global _speech_idx
    body = await request.json()
    messages = body["messages"]
    stream = body.get("stream", False)
    system_prompt = messages[0]["content"] if messages else ""

    # 决策类请求（简短返回数字）
    if "直接输出你选择的玩家编号" in system_prompt or "是否使用" in system_prompt:
        content = "我选择 2" if "编号" in system_prompt else "救"
    elif "投票" in system_prompt and "发言记录" in system_prompt:
        content = "思考：2号前后矛盾，嫌疑最大。\n投票: 2"
    else:
        content = SPEECHES[_speech_idx % len(SPEECHES)]
        _speech_idx += 1
        # 从 prompt 中提取玩家编号模拟个性化回显
        m = re.search(r"你是\s*(\d+)\s*号玩家", system_prompt)
        if m:
            content = f"我是 {m.group(1)} 号玩家：大家好，我来说两句。{content}"

    if not stream:
        return {
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }

    # 流式：按字切分
    async def gen():
        for i, char in enumerate(content):
            yield f"data: {json.dumps({'choices': [{'delta': {'content': char}, 'finish_reason': None}]})}\n\n"
            await asyncio.sleep(0.01)
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


def start_mock_server(port: int = 9000):
    thread = threading.Thread(
        target=lambda: uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning"),
        daemon=True,
    )
    thread.start()
    return thread
