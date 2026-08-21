# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目一句话

局域网网页版狼人杀：人类 + AI 玩家同局，AI 由不同大模型（OpenAI 兼容端点）扮演，支持语音播报，Claude 风格前端。完整需求见 `AI狼人杀-项目需求说明书.md` + `AI狼人杀-执行计划.md`。

## 启动 / 测试

```bash
# 启动后端（开发主要用 .venv + uvicorn）
.venv/bin/python -m backend.main
# 或一键: ./start.sh

# 跑测试（项目没有用 pytest 套件，直接 python 执行，每个文件自带 main）
.venv/bin/python tests/test_room.py
.venv/bin/python tests/test_ws.py
.venv/bin/python tests/test_game.py
.venv/bin/python tests/test_rules.py
.venv/bin/python tests/test_human.py
.venv/bin/python tests/test_tts.py
.venv/bin/python tests/test_llm.py        # 需要 mock_llm.py：无网络也跑
.venv/bin/python tests/test_llm_full_game.py
.venv/bin/python tests/test_real_game.py  # 真实 LLM，需要 API key
```

`.claude/launch.json` 已配置 `werewolf-backend` 启动项，浏览器预览走 `http://localhost:8000`。

## 项目结构（核心脉络）

```
backend/
  main.py                  # FastAPI 入口：静态文件 + /ws 路由 + 启动 banner
  config.py                # 解析 .env + config/models.json；ModelConfig 校验
  config/models.json       # 用户自填的 AI 模型列表（OpenAI 兼容端点）
  room/
    manager.py             # RoomManager / Player / Room 数据类（内存房间）
    ws_handler.py          # ConnectionManager + WsRouter + _run_game() 启动 GameDirector
  game/
    state_machine.py       # Game / GamePlayer / 阶段流转（夜晚/白天/投票/结束）
    roles.py               # 角色定义（中文）+ 人数配置（6/9/12 人）+ 阵营判定
    judge.py               # 纯函数判定（胜负、狼人投票、女巫/猎人合法性）
    director.py            # GameDirector：异步编排整局，调度 ai_speaker / 人类行动
  ai/
    llm_client.py          # httpx 异步调用 OpenAI 兼容 /chat/completions（含流式）
    llm_pool.py            # LLMPool：会话隔离 + asyncio.Queue 全局串行
    speaker.py             # LlmSpeaker：流式发言 + 决策；FakeSpeaker 占位
    prompts.py             # 角色 prompt + CoT 投票 prompt + 发言结束标记
    tts.py                 # edge-tts 流式封装（按句末切 audio chunk）

frontend/
  index.html               # Claude 风格前端（无构建工具，单 HTML + Alpine.js）
  static/
    app.js                 # Alpine.js 状态机 + WebSocket 客户端 + 音频播放
    alpine.min.js          # Alpine.js v3
    roles/                 # 5 张角色立绘（werewolf/seer/witch/hunter/villager.png）

tools/
  generate_role_images.py  # 一次性预生成角色立绘（调用 agnescli）

tests/                     # 每个文件独立可跑，自带 if __name__ == "__main__"
  mock_llm.py              # 假冒 LLM HTTP 服务，给 test_llm 用
```

## 关键架构约束

**1. 角色名一律中文（狼人/预言家/女巫/猎人/村民/守卫）**。不要在代码、prompt、UI、日志中引入英文标识符。

**2. 信息隔离硬约束**：`backend/ai/prompts.py` 是诚实 AI 的生命线，每个 AI 玩家只能看到自己角色允许的信息。修改任何 prompt 时必须确认没把其他玩家信息泄漏给本人。

**3. LLM 调用串行**：每个 AI 玩家持独立 `PlayerSession.messages`（会话隔离），但所有 LLM 调用走 `LLMPool._queue` 串行消费，避免并发挤占 API 限流。修改时不要绕过 `pool.submit()`。

**4. 发言结束标记**：白天发言 prompt 要求 AI 输出 `SPEECH_END_MARK = "【发言结束】"`，后端识别后清理再广播。修改 prompt 必须保留这个标记。

**5. 协议消息骨架**（ws_handler ↔ app.js，类型全中文）：
- 客户端 → 服务端：`create_room` / `join_room` / `start_game` / `human_action` / `leave_room`
- 服务端 → 客户端：`room_joined` / `room_players` / `game_started`(含 roles) / `phase_changed` / `speech_turn` / `speech_delta`（增量流式，最后一段 `final=true`）/ `speech_audio`（base64 mp3 chunk）/ `speech_end` / `night_result` / `divine_result`（仅本人） / `witch_action`（仅本人） / `wolf_partners`（仅狼人本人） / `human_action_req` / `vote_update` / `vote_result` / `hunter_shot` / `game_paused` / `player_disconnected` / `player_reconnected` / `game_over` / `error`

修改前端时优先复用现有消息类型，不要新增！

**6. 流式发言链路**：`director.py` 调 `ai_speaker.speak(..., on_streaming_delta=...)` → `LlmSpeaker` 每收 LLM chunk 立即回调 → director 转 `speech_delta` 广播 → 前端累积到当前气泡（看 `app.js` `speech_delta` 分支）。TTS 在发言全部完毕后整段触发（`director.py` 在 `speak()` 返回后调 `on_tts`），与逐字显示并行。

**7. 角色可见规则**：前端 `canSeeRole(pid)` 决定头像是否揭示 —— 自己始终可见，其他人**死后**才可见。修改时不要把"提前揭示"放进可见条件（会破坏推理公平性）。

**8. 模型配置留白**：`backend/config/models.json` 由用户自填。**修改时不要预填默认模型**，否则会泄露用户私有 key 偏好的猜测。修改后跑一遍 `backend.main` 看启动 banner 是否对每个模型打了 `✅ 已启用` / `⚠️ 已禁用：未设置环境变量 XXX_API_KEY`。

**9. 无 LLM 时的回退**：未配置任何模型时启动，director 走 `FakeSpeaker(["我是 AI 玩家，请多指教。"])`（30ms/字 模拟流式），仍可跑完一局。修改默认值时保证有 fallback。

**10. 前端无构建工具**：HTML + Alpine.js 在 `frontend/static/alpine.min.js`，JS 写在 `app.js`。**不要**引入需 npm 的依赖。

## 常用陷阱

- **断线 = 暂停**：`ConnectionManager.disconnect()` 在游戏进行中会 `paused = True` 并广播 `game_paused`。修改时不要让断线悄悄踢人。
- **重启清空**：所有房间/玩家/游戏状态在内存中，无持久化。修改后必须重启验证。
- **API Key 走环境变量**：`backend/config.py:load_env_file()` 读 `backend/.env`（不覆盖已有环境变量）。**不要**把 `.env` 提交到 git，README 提示但没加进 `.gitignore` 是已知问题（项目目前还没 git 仓库）。
- **edge-tts 失败静默**：`tts.py` 在异常时返回空生成器，游戏不中断。修改时不要让它抛异常。
- **agnescli 角色图**：`tools/generate_role_images.py` 调 `agnes image generate --out <file.png>`（CLI 自动读取 `~/.agnes/config.json`）。超时 300s。已生成图自动跳过。

## 修改风格协议

- 中文优先（CLAUDE.md / 用户偏好）
- 5 行内的修改不要写注释
- 唯一性编辑时优先用 `Edit` 而非 `Write`
- 修改任何公开 WS 消息字段前先看 `ws_handler.py` 和 `app.js` 两边的协议对齐
- 调整前端样式时保持暖白底 `#faf9f5` + 衬线大标题 + 橙强调 `#d97706` 的 Claude 风格统一，**不引入 emoji**（已明确约定）
