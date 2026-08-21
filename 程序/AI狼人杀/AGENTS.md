# AI 狼人杀项目 - 多智能体协作总览

> **版本**：v2.0（含异地联机 / 语音播报 / 投票综合推理）
> **交付方**：小爪（Hermes Agent）
> **执行方**：Claude Desktop（开发者直连）

## 1. 项目结构概览

```text
AI狼人杀/
├── README.md              # 项目简介、快速开始、测试命令
├── CLAUDE.md              # Claude Code 专用指引（核心约束、协议、陷阱）
├── AGENTS.md              # 本文件——多智能体协作的 PM 视角总览
├── AI狼人杀-项目需求说明书.md  # 完整需求文档（732 行）
├── AI狼人杀-执行计划.md  # Day1-D6 里程碑计划
├── .claude/               # Claude Code 配置
├── backups/               # 项目备份
├── logs/                  # 游戏日志
├── .venv/                 # Python 虚拟环境
├── requirements.txt       # 依赖声明
├── start.sh               # 一键启动脚本
├── tools/                 # 辅助工具（如 generate_role_images.py）
├── tts_samples/           # TTS 音频样本

├── backend/               # 后端核心（Python + FastAPI）
│   ├── __init__.py
│   ├── main.py            # FastAPI 入口：静态文件 + /ws 路由 + 启动信息
│   ├── config.py          # 配置加载：models.json + .env，模型校验，TTS_ENABLED
│   ├── models/            # 数据模型（pydantic.py - 待检查）
│   ├── config/            # config/models.json - 用户自填的 AI 模型列表
│   ├── room/              # 房间管理
│   │   ├── __init__.py
│   │   ├── manager.py     # RoomManager, Player, create_room, add_player
│   │   └── ws_handler.py  # WebSocket 路由，ConnectionManager, WsRouter
│   ├── game/              # 游戏逻辑
│   │   ├── __init__.py
│   │   ├── state_machine.py  # Game, GamePlayer, FSM: 夜/白/投票/结束
│   │   ├── roles.py       # 角色定义（中文）+ 人数配置(6/9/12)+阵营判定
│   │   ├── judge.py       # 纯函数判定（胜负、狼人投票、女巫/猎人合法性）
│   │   ├── director.py    # GameDirector：异步编排整局，调度 ai_speaker / 人类行动
│   │   └── events.py      # 游戏事件定义
│   ├── ai/                # AI 玩家层
│   │   ├── __init__.py
│   │   ├── llm_client.py  # httpx 异步调用 OpenAI 兼容 /chat/completions
│   │   ├── llm_pool.py    # LLMPool：会话隔离 + asyncio.Queue 全局串行
│   │   ├── speaker.py     # LlmSpeaker：流式发言 + 决策；FakeSpeaker 占位
│   │   └── prompts.py     # 角色 prompt + CoT 投票 prompt + 发言结束标记
│   └── replay.py          # 回放文件生成

├── frontend/              # 前端（无构建工具，HTML + Alpine.js）
│ ├── index.html         # 主页面（房间/游戏/历史）
│ ├── src/
│ │   ├── main.js
│ │   ├── components/
│ │   │   ├── Room.vue
│ │   │   ├── Game.vue
│ │   │   ├── Speech.vue
│ │   │   └── Vote.vue
│ │   └── ws.js          # WebSocket 客户端封装
│ └── static/
    ├── app.js         # Alpine.js 状态机 + WebSocket 客户端 + 音频播放
    ├── alpine.min.js  # Alpine.js v3
    └── roles/         # 5 张角色立绘（werewolf/seer/witch/hunter/villager.png）

└── tests/                 # 每个文件独立可跑，自带 if __name__ == "__main__"
    ├── test_room.py
    ├── test_ws.py
    ├── test_game.py
    ├── test_rules.py
    ├── test_llm.py        # 需要 mock_llm.py：无网络也跑
    ├── test_llm_full_game.py
    └── test_real_game.py  # 真实 LLM，需要 API key
```

---

## 2. 核心文件内容摘要

### 2.1 `backend/main.py` - FastAPI 入口
- **作用**：FastAPI 应用入口，包含 WebSocket 路由、静态文件服务、启动信息打印
- **关键组件**：
  - `lifespan`：后台定期回收无人房间及其 LLM 会话
  - `get_lan_ip()` / `is_private_lan_ip()`：获取本机局域网 IP
  - `print_startup_banner()`：打印包含局域网/Tailscale/公网链接的启动 banner
  - Model 检查：`check_models_and_print(MODELS)` - 启动时校验 API Key
  - 端点：`/` ( serving index.html), `/api/models` (给前端提供可用模型列表), `/ws` (WebSocket 处理)

### 2.2 `backend/config.py` - 配置加载
- **作用**：解析 `config/models.json` 与 `.env`，校验 API Key，提供 ModelConfig 对象
- **关键类/函数**：
  - `ModelConfig`：单模型配置（name, base_url, api_key_env, model, tts_voice, enabled, disabled_reason）
  - `load_env_file()`：从 `backend/.env` 加载环境变量，不覆盖已有变量
  - `load_models()`：读取 `models.json`，返回所有 ModelConfig
  - `check_models_and_print()`：启动时校验并打印中文警告
  - `TTS_ENABLED`：从环境变量读取的 TTS 开关（默认关闭）
- **初始化顺序**：`load_env_file()` → `_init_models()` → `load_models()` → `MODELS`

### 2.3 `backend/room/manager.py` - 房间管理
- **作用**：内存中的房间管理，创建/加入/离开房间，人数管理
- **关键类**：
  - `Player`（dataclass）：player_id, nickname, is_human, is_ai, connected, role, alive, seat
  - `Room`：房间对象，包含 players dict, max_players, code, host_player_id, join_mode, etc.
- **关键方法**：
  - `create_room(nickname, player_count)`：创建房间
  - `add_player(room, nickname, is_human)`：添加玩家
  - `room_snapshot(room)`：房间快照
  - `find_player_by_nickname(room, nickname)`：查找玩家
  - `set_join_mode(room, mode, approved_nicks)`：设置加入模式（open/private）

### 2.4 `backend/room/ws_handler.py` - WebSocket 消息路由
- **作用**：WebSocket 连接管理，消息路由，断线检测，暂停/恢复
- **关键类**：
  - `ConnectionManager`：管理所有 WebSocket 连接，广播消息
  - `WsRouter`：消息路由器，处理 create_room, join_room, start_game, human_action, leave_room 等
- **关键协议**（全部 JSON，中文语义）：
  - 客户端 → 服务端：`create_room`, `join_room`, `leave_room`, `start_game`, `human_action`
  - 服务端 → 客户端：`room_joined`, `room_players`, `game_started`, `phase_changed`, `speech_turn`, `speech_delta`, `speech_end`, `speech_audio`, `vote_update`, `vote_result`, `night_result`, `divine_result`, `witch_action`, `wolf_partners`, `hunter_shot`, `game_over`, `error`

### 2.5 `backend/game/state_machine.py` - 游戏状态机
- **作用**：纯确定性逻辑，负责阶段推进和角色行动裁决
- **关键类**：
  - `GamePlayer`（dataclass）：player_id, nickname, is_ai, role, alive, seat, divine_results, witch_antidote/witch_poison, shot_used
  - `Game`：游戏主类，管理玩家列表，当前阶段，发言记录，公共日志，胜负判定
- **阶段流转**：`夜晚 → 白天发言 → 投票 → 结算`（循环直到胜负）
- **关键属性**：`speeches_of_day`, `public_log`, `full_record`, `day`, `phase`, `winner`

### 2.6 `backend/game/roles.py` - 角色定义
- **作用**：所有角色的中文定义、阵营、数量、技能
- **ROLES 表**：
  - 狼人：狼人阵营，3人，夜晚协商杀一人，互知同伙
  - 预言家：好人阵营，1人，每晚查验一名玩家身份
  - 女巫：好人阵营，1人，解药救活一人、毒药毒死一人（各一次）
  - 猎人：好人阵营，1人，被放逐或被狼杀时可开枪带走一人
  - 村民：好人阵营，3人，无技能
- **CONFIGS 表**：6/9/12 人局的人数配置

### 2.7 `backend/game/judge.py` - 纯函数判定
- **作用**：确定性判定逻辑，不依赖 LLM
- **关键函数**：
  - `can_act_night(player) -> bool`：判断角色是否可在夜晚行动
  - `pick_wolf_target(game, proposals) -> int | None`：狼人目标选择
  - `valid_target(game, target_id, exclude_self=None) -> bool`：验证目标合法性
  - `divine_valid(game, diviner_id, target_id) -> bool`：预言家查验合法性
  - `witch_can_save(game, witch_id) -> bool`：女巫是否可救人
  - `witch_can_poison(game, witch_id, target_id) -> bool`：女巫是否可下毒
  - `guard_valid(game, guard_id, target_id) -> bool`：守卫是否可守护
  - `hunter_can_shoot(game, hunter_id) -> bool`：猎人是否可开枪
  - `tally_votes(votes) -> int | None`：投票结算（票数最多者出局，平票不死）
  - `end_game_reason(game) -> str`：生成胜负描述

### 2.8 `backend/game/director.py` - 游戏导演
- **作用**：异步编排整局游戏，广播事件，管理 AI 决策
- **关键类**：
  - `GameDirector`：游戏总导演
  - `FakeSpeaker`：假 AI 发言器，固定话术，用于无模型配置时验证
- **游戏流程**：
  - 夜晚：狼人提议 → 狼群决策 → 预言家查验 → 女巫行动 → 守卫行动 → 天亮结算
  - 白天：发言 → 投票 → 结算
- **上帝视角（死亡玩家全视角）**：
  - 每个 AI 决策环节（投票/狼杀/女巫/预言家/守卫/猎人）都生成结构化日志
  - 日志只广播给已死亡玩家，避免泄露 AI CoT
  - 玩家死亡瞬间补发完整历史，之后每个新日志实时推送

### 2.9 `backend/ai/speaker.py` - AI 发言驱动器
- **作用**：基于 LLM 的 AI 玩家发言/决策器
- **关键类**：
  - `LlmSpeaker`：流式发言，TTS 集成，投票决策
- **核心功能**：
  - `speak()`：让 AI 玩家流式发言，检测句末标点即时触发 TTS
  - `decide()` / `_decide_target()`：决策目标选择
  - 投票时的 3-step CoT（链式推理）：列出矛盾点 → 评估证据 → 综合决策
  - `_parse_vote()`：解析投票输出，优先取「投票：N」行
  - `clean_thinking()`：清理思考文本，优先 JSON 解析，兜底提取
  - `parse_number()`：从 LLM 输出中解析玩家编号，整词匹配
- **TTS 流式设计**：LLM 输出边检测句末边触发 TTS，首包延迟降至 0.5-1s

### 2.10 `backend/ai/prompts.py` - 角色提示词
- **作用**：所有 AI 玩家的 system prompt 模板
- **关键常量/函数**：
  - `SPEECH_END_MARK = "【发言结束】"`：发言结束标记
  - `ROLE_SPEECH_PROMPTS`：5 个角色模板（狼人/预言家/女巫/猎人/村民）
  - `build_speech_system_prompt()`：构建发言系统提示词
  - `build_target_prompt()`：构建目标选择提示词
  - `build_vote_prompt()`：构建投票 CoT 提示词（3-step，含顺序随机打乱）
  - `build_review_prompt()`：游戏结束后复盘提示词
- **信息隔离原则**：每个 AI 玩家只能看到自己角色允许看到的信息

### 2.11 `backend/ai/llm_pool.py` - LLM 会话池
- **作用**：每个 AI 玩家独立的对话会话 + 全局串行调度队列
- **关键类**：
  - `PlayerSession`：单个玩家的会话隔离（独立 messages[] 历史）
  - `LLMPool`：全局单例，asyncio.Queue 串行消费，避免并发挤占 API 限流
- **设计原则**：
  - 玩家会话隔离：每个 AI 玩家持有独立 messages[] 历史
  - 串行调度：全局 asyncio.Queue，同一时刻只有一个 LLM 调用在执行
  - 模型分配：按配置顺序轮询分配给 AI 玩家
  - 音色分配：从音色池轮询分配，让每个 AI 玩家有不同声音

### 2.12 `frontend/index.html + app.js` - 前端
- **技术栈**：HTML + Alpine.js (无构建工具)
- **关键特性**：
  - Claude 风格统一：暖白底 `#faf9f5` + 衬线大标题 + 橙强调 `#d97706`
  - WebSocket 客户端封装
  - Web Audio API 流式 TTS 播放
  - `canSeeRole(pid)`：自己始终可见，其他人死后才可见
  - 每路独立播放，互不覆盖
  - 5 张角色立绘在 `static/roles/`

---

## 3. 关键架构约束（来源 CLAUDE.md）

1. **角色名一律中文**：狼人/预言家/女巫/猎人/村民/守卫
2. **信息隔离硬约束**：AI 玩家只能看到自己角色允许的信息
3. **LLM 调用串行**：通过 LLMPool._queue 串行消费，避免并发挤占
4. **发言结束标记**：`SPEECH_END_MARK = "【发言结束】"` 必须保留
5. **协议消息骨架**：WS 消息类型全中文，修改前端优先复用现有类型
6. **流式发言链路**：director → LlmSpeaker → streaming delta → front-end
7. **角色可见规则**：`canSeeRole(pid)`：自己始终可见，其他人死后可见
8. **模型配置留白**：`config/models.json` 由用户自填，不预填默认模型
9. **无 LLM 回退**：使用 FakeSpeaker 固定话术，保证可玩
10. **前端无构建工具**：HTML + Alpine.js，不引入 npm 依赖

---

## 4. 关键约束与陷阱

- **断线 = 暂停**：ConnectionManager.disconnect() 在游戏进行中会暂停并广播
- **重启清空**：所有房间/玩家/游戏状态在内存中，无持久化
- **API Key 走环境变量**：读 backend/.env，不要提交到 git
- **edge-tts 失败静默**：异常时返回空生成器，游戏不中断
- **agnescli 角色图**：调用 agnes image generate --out <file.png>，超时 300s
- **TTS 默认关闭**：TTS_ENABLED=1 时启用

---

## 5. 里程碑与验收标准（来源执行计划）

### Day 1：跑通 wolf_bot 原版
### Day 2：加 WebSocket 房间 + 局域网访问
### Day 3：接多模型（LiteLLM）
### Day 4：接 edge-tts 流式语音
### Day 5：改投票为综合推理（3-step CoT）
### Day 6：异地联机测试（Tailscale）

**完成判定**：单 persona "改完" 不算完成——需 verifier 子 agent 独立复验 + PM 汇总三方对齐

---

## 6. 作者与联系
- **用户**：heng（语音输入，习惯口语化，偏爱中文，极简优先）
- **交付方**：小爪（Hermes Agent）
- **PM 协调**：多智能体协作系统，本文件为 PM 视角总览

---
*文件末尾 - 项目总览完成*