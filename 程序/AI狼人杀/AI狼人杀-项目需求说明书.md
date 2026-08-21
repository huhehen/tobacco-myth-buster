# 🐺 AI 狼人杀 — 项目需求说明书

> **版本**：v2.0（含异地联机 / 语音播报 / 投票综合推理）
> **交付方**：小爪（Hermes Agent）
> **执行方**：Claude Desktop（开发者直连）
> **创建日期**：2026-08-12
> **预期落地周期**：5-6 天可出可玩 demo

---

## 📋 目录

1. [项目背景与目标](#1-项目背景与目标)
2. [核心需求（v1 + v2）](#2-核心需求)
3. [非功能性需求](#3-非功能性需求)
4. [技术栈（强约束）](#4-技术栈强约束)
5. [架构设计](#5-架构设计)
6. [游戏规则](#6-游戏规则)
7. [AI 玩家设计](#7-ai-玩家设计)
8. [投票综合推理机制](#8-投票综合推理机制-⭐新增)
9. [语音播报设计](#9-语音播报设计-⭐新增)
10. [异地联机方案](#10-异地联机方案-⭐新增)
11. [里程碑与验收标准](#11-里程碑与验收标准)
12. [参考资源](#12-参考资源)
13. [风险与禁忌](#13-风险与禁忌)

---

## 1. 项目背景与目标

### 1.1 为什么做这个

狼人杀是一个**重度依赖社交推理**的游戏，现实中凑齐 8-12 人越来越难。本项目用 AI 填补空缺，让用户随时能和 AI（甚至不需要真人）玩一局完整的狼人杀，同时保留和朋友一起玩的社交乐趣。

### 1.2 目标用户

- **主要**：3-5 个朋友想玩狼人杀但凑不齐人
- **次要**：想一个人和 AI 玩狼人杀
- **场景**：家里 / 宿舍 / 异地朋友相聚

### 1.3 产品差异化

| 现有产品 | 我们的差异化 |
|---|---|
| aiwerewolf.net（公网页面） | ❌ 全 AI，玩家只能 1vN |
| Wolfcha（猹杀） | ❌ 仅公网，需部署到服务器 |
| wolf_bot（GitHub 17⭐） | ❌ 仅单机 127.0.0.1 |
| 桌游 App（太空杀等） | ❌ 无 AI |

**我们的特色**：局域网 + 异地（双模式）+ AI 填位 + 多模型扮演 + 语音播报

---

## 2. 核心需求

### 2.1 功能性需求（v1 原始）

| ID | 需求 | 优先级 |
|---|---|---|
| F1 | 支持人类玩家和 AI 玩家混合参与同一局游戏 | P0 |
| F2 | AI 玩家能基于角色和局势进行**真实的推理与发言** | P0 |
| F3 | 至少支持 2-3 种不同的大模型扮演不同 AI 玩家 | P0 |
| F4 | 同一局域网内的人能通过浏览器加入房间一起玩 | P0 |
| F5 | 系统以"局域网内可打开的网页"作为主要交互形式 | P0 |

### 2.2 功能性需求（v2 新增）⭐

| ID | 需求 | 优先级 |
|---|---|---|
| F6 | **支持邀请不在同一局域网的朋友远程加入**（异地联机） | P0 |
| F7 | **每个角色发言时进行语音播报**（多音色 + 流式） | P0 |
| F8 | **投票必须基于全部发言记录综合推理后做出**（禁止"就近投票"偏差） | P0 |

### 2.3 玩家人数

- **最少**：6 人（4 村民 + 1 预言家 + 1 狼人）
- **标准**：9 人（3 狼人 + 1 预言家 + 1 女巫 + 1 猎人 + 3 村民）
- **上限**：12 人（支持更多神职角色）

---

## 3. 非功能性需求

| 维度 | 要求 |
|---|---|
| 启动时间 | < 5 秒（单机启动到房间可加入） |
| 单局延迟 | 投票阶段 LLM 响应 < 10 秒 |
| TTS 延迟 | 流式播放，第一个音频包 < 1.5 秒 |
| 并发能力 | 同时支持 12 房间 × 9 玩家 = 108 路 WebSocket |
| 成本控制 | 单局 9 人 LLM token < 5 万（避免破产） |
| 部署复杂度 | 单进程启动，一行命令搞定（不要 Docker 不要 Redis） |
| 跨平台 | macOS（开发者）/ Windows（部分朋友） / 移动浏览器（iOS/Android） |

---

## 4. 技术栈（强约束）

> ⚠️ 这是经过调研的优选方案，**不要随意替换**，否则会破坏整体设计。

### 4.1 后端

```python
# 核心栈
Python 3.11+
FastAPI 0.110+              # Web + WebSocket 框架
uvicorn[standard] 0.27+      # ASGI 服务器
pydantic 2.0+               # 数据验证
litellm 1.30+               # 统一多模型调用（GPT/Claude/DeepSeek/Qwen/豆包）
websockets 12.0+            # WebSocket 客户端（可选，用 FastAPI 内置即可）
edge-tts 6.1+               # 微软免费 TTS（多音色 + 流式）
python-multipart 0.0.9+     # 文件上传（如有需要）
```

### 4.2 前端

```javascript
// 保持最简，避免重型框架
Vue 3 + Vite (推荐)         // 或纯 HTML + Alpine.js 也行
原生 WebSocket API           // 不要 socket.io（多一层 overhead）
Web Audio API                // 流式播放 TTS
localStorage                 // 持久化房间历史（可选）
```

### 4.3 不需要的依赖（请勿引入）

❌ Redis（单进程内存够用）
❌ PostgreSQL / SQLite（不需要持久化玩家账号）
❌ Docker Compose（部署复杂度爆炸）
❌ Socket.IO（FastAPI WebSocket 原生够用）
❌ 任何微服务框架（杀鸡用牛刀）

### 4.4 LLM 模型配置

```json
// config/models.json
{
  "models": {
    "gpt-4o-mini":         {"provider": "openai",   "role": "general"},
    "claude-3-5-haiku":    {"provider": "anthropic", "role": "general"},
    "deepseek-chat":       {"provider": "deepseek", "role": "general"},
    "qwen-plus":           {"provider": "qwen",     "role": "villager"},
    "gpt-4o":              {"provider": "openai",   "role": "key_reasoning"}
  },
  "default_tts_voice_map": {
    "gpt-4o-mini":         "zh-CN-XiaoxiaoNeural",
    "claude-3-5-haiku":    "zh-CN-YunxiNeural",
    "deepseek-chat":       "zh-CN-YunjianNeural",
    "qwen-plus":           "zh-CN-XiaoyiNeural"
  }
}
```

---

## 5. 架构设计

### 5.1 整体架构

```
┌─────────────────────────────────────────────┐
│  浏览器 (Vue3) - 每个玩家一个标签页          │
│  ┌─ 房间大厅  ┌─ 角色分配  ┌─ 发言气泡     │
│  ├─ 投票按钮  ┌─ Web Audio 流式 TTS 播放器│
│  └─ WebSocket 客户端                        │
└──────────┬──────────────────────────────────┘
           │ WSS (局域网直连 / Tailscale / Cloudflare Tunnel)
┌──────────▼──────────────────────────────────┐
│  FastAPI 单进程 (uvicorn --host 0.0.0.0)    │
│  ┌─ WebSocket 房间管理（多房间）           │
│  ├─ 游戏状态机 (FSM: 夜/日/投票/结束)     │
│  ├─ LLM 调度层 (LiteLLM → 多 provider)    │
│  ├─ TTS 服务 (edge-tts 流式 → mp3 chunk)   │
│  ├─ 日志 & 回放 (replay_{ts}.json)         │
│  └─ 静态文件服务 (前端 build/dist)         │
└──────────┬──────────────────────────────────┘
           │ HTTPS (LLM API)
┌──────────▼──────────────────────────────────┐
│  LLM Providers                              │
│  - OpenAI (gpt-4o-mini / gpt-4o)            │
│  - Anthropic (claude-3-5-haiku / sonnet)    │
│  - DeepSeek (deepseek-chat)                 │
│  - 阿里百炼 (qwen-plus / qwen-max)          │
└─────────────────────────────────────────────┘
```

### 5.2 模块划分

```
backend/
├── main.py                 # FastAPI 入口
├── game/
│   ├── state_machine.py    # 夜晚/白天/投票状态机
│   ├── roles.py            # 角色定义（狼人/女巫/预言家...）
│   ├── judge.py            # 裁判逻辑（确定性，不用 LLM）
│   └── events.py           # 游戏事件定义
├── ai/
│   ├── llm_client.py       # LiteLLM 封装
│   ├── prompts.py          # 各角色系统 prompt
│   ├── voting.py           # ⭐ 综合推理投票
│   └── tts.py              # ⭐ 流式 TTS
├── room/
│   ├── manager.py          # 房间管理（创建/加入/离开）
│   └── ws_handler.py       # WebSocket 消息路由
├── models/
│   └── pydantic.py         # 数据模型（Player/Room/GameState）
├── config.py               # 配置加载
└── replay.py               # 回放文件生成
frontend/
├── index.html              # 主页面（房间/游戏/历史）
├── src/
│   ├── main.js             # Vue3 入口
│   ├── components/
│   │   ├── Room.vue        # 房间大厅
│   │   ├── Game.vue        # 游戏主界面
│   │   ├── Speech.vue      # 发言气泡（含音频播放器）
│   │   └── Vote.vue        # 投票面板
│   └── ws.js               # WebSocket 客户端封装
└── vite.config.js
```

### 5.3 数据流

```
玩家发言
  ↓
WebSocket 消息 {type: "speech", player_id: 3, text: "..."}
  ↓
后端 ws_handler 接收
  ↓
广播给所有房间成员 + 同时调 edge-tts 流式生成音频
  ↓
每个客户端收到 {type: "speech", player_id, text, audio_url}
  ↓
前端 Speech.vue 渲染气泡 + <audio> 流播放

投票（⭐v2 关键改动）
  ↓
所有玩家发言完成后
  ↓
后端为每个 AI 玩家构造综合推理 prompt（包含全部发言）
  ↓
LLM 返回 {analysis, vote_target}
  ↓
汇总投票 → 票数最高者出局（如平票则随机）
```

---

## 6. 游戏规则

### 6.1 标准 9 人局配置

| 角色 | 阵营 | 人数 | 技能 |
|---|---|---|---|
| 狼人 | 狼人阵营 | 3 | 夜晚共同商议杀死一名玩家 |
| 预言家 | 好人阵营 | 1 | 夜晚查验一名玩家身份 |
| 女巫 | 好人阵营 | 1 | 拥有一瓶解药和一瓶毒药，各限一次 |
| 猎人 | 好人阵营 | 1 | 被放逐或被狼杀时可开枪带走一人 |
| 村民 | 好人阵营 | 3 | 无特殊技能 |

### 6.2 游戏流程（标准局）

```
游戏开始 → 分配角色 → 夜晚阶段 → 天亮公布死者 → 白天发言 → 投票 → 结算
循环直到任一阵营达成胜利条件。
```

**详细步骤**：

1. **夜晚**（所有人闭眼）
   - 狼人 → 共同商议杀一名玩家
   - 预言家 → 查验一名玩家
   - 女巫 → 可使用解药救人 / 毒药杀人（各限一次）

2. **天亮**
   - 公布昨晚死者（如有）
   - 猎人若被狼杀可立即开枪

3. **白天发言**
   - 按座位顺序，每人说一次话
   - 每人发言时间上限 60 秒（AI 自动生成约 30 秒）

4. **投票**
   - 每人投给最可疑的玩家（综合全部发言推理）
   - 得票最多者被放逐（如平票则不死）
   - 猎人若被放逐可立即开枪

5. **胜利判定**
   - 狼人全部死亡 → 好人胜利
   - 狼人数量 ≥ 好人数量 → 狼人胜利

### 6.3 角色信息隔离（关键）

**每个 AI 玩家只能看到自己角色允许看到的信息**：
- 普通村民：只知道自己是村民
- 预言家：知道自己 + 查验历史
- 女巫：知道自己 + 解药/毒药状态
- 狼人：知道自己是狼 + 同伙是谁

→ 这必须在 prompt 层面硬约束，否则模型会"作弊"暴露其他角色信息。

---

## 7. AI 玩家设计

### 7.1 双层扮演机制（参考 Wolfcha）

```
Layer 1: AI 扮演一个有性格/背景/说话习惯的"虚拟玩家"
Layer 2: 这个虚拟玩家在游戏里扮演具体角色（预言家/狼人等）
```

### 7.2 角色 Prompt 模板（核心）

```python
# 每个 AI 玩家的 system prompt 结构
SYSTEM_PROMPT = """
你是 {player_name}，一个 {personality} 的人。

【你的游戏身份】
角色：{role}（{camp}阵营）
能力：{abilities}
限制：{restrictions}

【你看到的信息】
{visible_info}

【你不知道的信息（严禁伪造）】
{hidden_info}

【游戏规则】
{game_rules}

【发言要求】
1. 用第一人称说话，模拟真人玩家
2. 推理必须基于你看到的信息，不要假设你不知道的信息
3. 发言长度 30-80 字，自然口语化
4. 可以撒谎（狼人）也可以推测（预言家/村民）

【输出格式】
发言: <你的发言内容>
"""
```

### 7.3 性格预设示例

```python
PERSONAS = {
    "aggressive":  "激进型，发言直接，喜欢主动出击",
    "analytical":  "分析型，喜欢列举证据，逻辑严密",
    "cautious":    "谨慎型，话少，但一开口就有分量",
    "humorous":    "幽默型，喜欢打趣缓解气氛",
    "leader":      "领袖型，喜欢主导讨论方向"
}
```

### 7.4 不同模型的能力差异

| 模型 | 推荐场景 | 性格预设 |
|---|---|---|
| gpt-4o / gpt-4o-mini | 综合推理，预言家 | analytical |
| claude-3-5-sonnet | 深度策略，狼人 | cautious |
| deepseek-chat | 高性价比，村民 | leader |
| qwen-plus | 中文表达自然，村民/女巫 | humorous |
| gpt-4o-mini | 兜底，玩家众多时 | aggressive |

---

## 8. 投票综合推理机制 ⭐v2 关键

### 8.1 问题背景

**现有项目（包括 aiwerewolf.net）的投票 prompt 普遍有问题**：

```python
# ❌ 有问题的现有做法
vote_prompt = f"""
你是{me}，本轮发言记录：{all_speeches}
请投票。
"""
# → 模型倾向于"扫一眼就投给最先被怀疑的人"（就近偏差）
```

### 8.2 改进方案：强制链式推理

```python
# ✅ 改进后的 vote prompt
vote_prompt = f"""
【发言阶段结束，以下是本轮全部 {len(speeches)} 条发言记录】
（顺序已随机打乱，避免位置偏差）
{randomize_order(speeches)}

你是 {me}，你的身份是 {role}。

现在请你按以下步骤推理（不要跳步）：

Step 1: 列出本轮发言中你认为"矛盾"或"反常"的点（至少 3 条）
Step 2: 评估每个被怀疑者的证据强度
Step 3: 综合考虑你的角色立场，做最终决策

【严格输出格式】
分析: <Step 1-3 的推理过程>
投票: <player_id>

如果解析失败，重试 1 次（最多 2 次）。
"""
```

### 8.3 三个关键设计细节

1. **顺序随机打乱**：发言记录**乱序展示**，避免"位置偏差"（Kaggle Game Arena 的现成做法）
2. **强制结构化输出**：投票必须填 `<player_id>`，解析失败重试
3. **发言阶段不约束投票**：保留"边说边怀疑"的表达自由，**只在投票阶段整合**

### 8.4 投票结果处理

```python
def tally_votes(votes: List[Player_id]) -> Optional[Player_id]:
    """投票结算"""
    counter = Counter(votes)
    top = counter.most_common(2)
    if len(top) == 1 or top[0][1] > top[1][1]:
        return top[0][0]  # 票数最多者出局
    else:
        return None  # 平票，不死
```

---

## 9. 语音播报设计 ⭐v2 关键

### 9.1 技术方案对比

| 方案 | 中文质量 | 流式 | 成本 | 推荐度 |
|---|---|---|---|---|
| **edge-tts**（微软） | ⭐⭐⭐⭐ | ✅ | **免费** | ⭐⭐⭐⭐⭐ MVP首选 |
| 阿里 CosyVoice 2.0 | ⭐⭐⭐⭐⭐ | ✅ | ¥0.5/万字 | ⭐⭐⭐⭐ 想要质感 |
| 字节火山 TTS | ⭐⭐⭐⭐ | ✅ | 按字符 | ⭐⭐⭐ 备选 |
| 本地部署 CosyVoice | ⭐⭐⭐⭐⭐ | 看 GPU | 一次性 | ⭐⭐ 想完全可控 |

### 9.2 实施细节

```python
# ai/tts.py
import edge_tts
import asyncio

async def stream_speech(text: str, voice: str = "zh-CN-XiaoxiaoNeural"):
    """流式生成 TTS 音频"""
    communicate = edge_tts.Communicate(text, voice)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]  # mp3 bytes

# WebSocket 端推流
async def broadcast_speech(room_id, player_id, text, voice):
    async for audio_chunk in stream_speech(text, voice):
        await ws_manager.broadcast(
            room_id,
            {
                "type": "speech_audio",
                "player_id": player_id,
                "audio": base64(audio_chunk),  # 或上传到临时 URL
                "is_final": False
            }
        )
    await ws_manager.broadcast(room_id, {"type": "speech_audio", "is_final": True})
```

### 9.3 前端播放策略

```javascript
// 多个 AI 同时发言时：每路独立播放，互不覆盖
const audioContext = new AudioContext();
const players = new Map();  // player_id → AudioBufferSourceNode

async function playSpeechChunk(playerId, audioBytes) {
    const buffer = await audioContext.decodeAudioData(audioBytes);
    const source = audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(audioContext.destination);
    source.start();
}
```

### 9.4 音色映射

```json
// 每个 AI 玩家绑定一个音色（可在 config/models.json 配置）
{
  "gpt-4o-mini":         "zh-CN-XiaoxiaoNeural",   // 温柔女声
  "claude-3-5-haiku":    "zh-CN-YunxiNeural",       // 阳光男声
  "deepseek-chat":       "zh-CN-YunjianNeural",     // 沉稳男声
  "qwen-plus":           "zh-CN-XiaoyiNeural"       // 甜美女声
}
```

---

## 10. 异地联机方案 ⭐v2 关键

### 10.1 方案对比

| 方案 | 朋友加入方式 | 国内延迟 | 安全 | 推荐度 |
|---|---|---|---|---|
| **Tailscale 客户端** | 装客户端加入 tailnet | OK | 高 | ⭐⭐⭐⭐⭐ 默认推荐 |
| **Tailscale Funnel** | 给朋友一个公网链接 | OK | 高 | ⭐⭐⭐⭐ 备选 |
| **Cloudflare Tunnel** | 公网临时链接 | 国内慢 | 高 | ⭐⭐⭐ 兜底 |
| **frp + 自有 VPS** | 稳定域名 | 看你 VPS | 中 | ⭐⭐ 长期方案 |

### 10.2 双轨策略

```
默认方案：Tailscale 客户端组网
  - 主机: 安装 Tailscale → 拿到 100.x.x.x IP
  - 朋友: 装 Tailscale → 加入同一 tailnet → 浏览器访问 http://100.x.x.x:8000

备选方案：Tailscale Funnel（给懒装客户端的朋友）
  - 主机: tailscale funnel 8000
  - 朋友: 直接访问 https://<machine-name>.ts.net（无需装任何东西）
```

### 10.3 局域网 + 异地统一入口

```python
# 后端启动时打印所有可访问的 URL
print(f"""
========================================
  狼人杀服务器已启动！
  局域网:    http://192.168.1.100:8000
  Tailscale: http://100.x.x.x:8000
  公网(Funnel): https://{hostname}.ts.net
========================================
""")
```

---

## 11. 里程碑与验收标准

### 11.1 Day 1：跑通 wolf_bot 原版

**任务**：
- 在本机 clone 并跑通 `mewamew/wolf_bot`
- 验证 `python web.py` 后能本地打开网页
- 完整玩一局 9 人局（暂时不用改任何代码）

**验收标准**：
- [ ] 本地浏览器能打开游戏页面
- [ ] 能完整玩完一局狼人杀（投票 → 出局 → 胜负判定）
- [ ] 日志文件 `logs/replay_*.json` 正确生成

---

### 11.2 Day 2：加 WebSocket 房间 + 局域网访问

**任务**：
- 把 wolf_bot 改成支持多人 WebSocket 连接
- 改 `web.py` 监听 `0.0.0.0:8000`
- 加房间大厅（创建/加入房间）

**验收标准**：
- [ ] 主机开服，手机浏览器能连入 `http://<主机IP>:8000`
- [ ] 两个浏览器标签页可以加入同一房间
- [ ] 投票结果在两个标签页同步显示

---

### 11.3 Day 3：接多模型（LiteLLM）

**任务**：
- 引入 LiteLLM，统一支持 OpenAI/Claude/DeepSeek/Qwen
- 实现 config.json 配置不同玩家用不同模型
- API key 走环境变量，不硬编码

**验收标准**：
- [ ] config.json 里至少配 3 个模型
- [ ] 一局游戏中能看到不同 AI 用了不同模型
- [ ] 单局 token 消耗 < 5 万

---

### 11.4 Day 4：接 edge-tts 流式语音

**任务**：
- 加 `ai/tts.py`，封装 edge-tts 流式 API
- WebSocket 推送 `speech_audio` 消息
- 前端用 Web Audio API 流播放

**验收标准**：
- [ ] AI 发言时同步播放语音
- [ ] 多个 AI 说话不会互相覆盖
- [ ] 第一个音频包延迟 < 1.5 秒

---

### 11.5 Day 5：改投票为综合推理

**任务**：
- 重写 vote prompt 为 3-step chain-of-thought
- 发言顺序随机打乱
- 强制结构化输出（失败重试 1 次）

**验收标准**：
- [ ] AI 投票时会输出完整推理过程（可见）
- [ ] 投票结果不偏向"最先被怀疑的人"
- [ ] 平票处理正确

---

### 11.6 Day 6：异地联机测试

**任务**：
- 配置 Tailscale（自己 + 朋友）
- 配置 Tailscale Funnel 作为公网备选
- 写部署文档（README.md）

**验收标准**：
- [ ] 朋友装 Tailscale 客户端能连进来
- [ ] 不装客户端的朋友能通过 Funnel 链接连进来
- [ ] 跨网络延迟 < 300ms（局域网或 P2P 直连时）

---

## 12. 参考资源

### 12.1 必看的开源项目

| 项目 | 用途 | URL |
|---|---|---|
| **mewamew/wolf_bot** | 起步底座（必 clone） | https://github.com/mewamew/wolf_bot |
| **Wolfcha（猹杀）** | 双层扮演 + 多模型范式 | https://github.com/ruanyf/weekly/issues/8772 |
| **hiper2d/werewolf-ai-party-game** | 前端 UI 参考 | https://github.com/hiper2d/werewolf-ai-party-game |
| **aiwerewolf.net** | 在线版体验 | https://aiwerewolf.net |
| **xuyuzhuang11/Werewolf (ChatArena)** | Prompt 范式 | https://github.com/xuyuzhuang11/Werewolf |

### 12.2 关键技术文档

- **FastAPI WebSocket**: https://fastapi.tiangolo.com/advanced/websockets/
- **LiteLLM Providers**: https://docs.litellm.ai/docs/providers
- **edge-tts GitHub**: https://github.com/rany2/edge-tts
- **Tailscale Funnel**: https://tailscale.com/kb/1223/funnel/

### 12.3 Prompt 工程论文

- "Enhance Reasoning for LLMs in Werewolf" (arxiv 2402.02330)
- "Strategic Language Agents in Werewolf" (arxiv 2502.04686)
- Kaggle Game Arena: https://www.kaggle.com/blog/game-arena-werewolf

---

## 13. 风险与禁忌

### 13.1 禁止事项（请勿做）

❌ **不要引入 Redis / PostgreSQL** — 杀鸡用牛刀
❌ **不要拆微服务** — 单进程足够
❌ **不要用 Socket.IO** — FastAPI WebSocket 原生够用
❌ **不要让 AI 看到其他角色的隐藏信息** — 必须信息隔离
❌ **不要用免费的 OpenAI 弱模型给关键角色** — 预言家/狼王要用 gpt-4o
❌ **不要把所有发言一次性塞进 prompt** — 顺序随机打乱 + 分步推理
❌ **不要硬编码 API key** — 走环境变量
❌ **不要写"看起来跑通了"的代码** — 每个功能都要有验证脚本

### 13.2 已知风险与缓解

| 风险 | 概率 | 缓解 |
|---|---|---|
| Tailscale 朋友懒得装 | 中 | 用 Tailscale Funnel 给公网链接兜底 |
| TTS 延迟过高 | 中 | edge-tts 流式 chunk + 前端预缓冲 |
| LLM 投票偏差 | 高 | 强制 CoT + 乱序 + 结构化输出 |
| Token 成本爆炸 | 中 | 复用对话上下文 + 便宜模型兜底 |
| 朋友网络差 | 低 | WebSocket 自带重连 + 状态快照 |
| macOS 依赖装不上 | 中 | Claude 跑报错时优先查 homebrew / pyenv |

### 13.3 验收硬指标

完成全部 Day1-Day6 后，必须达成：

- [ ] 完整跑完 3 局不同结局的狼人杀（好人胜 / 狼人胜 / 平局）
- [ ] 单局 token 消耗 < 5 万
- [ ] AI 投票时会输出完整推理（玩家可见）
- [ ] 至少 1 个朋友通过局域网 / Tailscale 加入并玩完一局
- [ ] 至少 1 个 AI 角色用语音播报（不是默认静音）

---

## 📎 附录

### A. 一句话启动命令（最终目标）

```bash
cd ~/程序/AI狼人杀 && python -m backend.main
```

启动后打印：

```
========================================
  🎮 狼人杀服务器已启动
  ──────────────────────────────────
  局域网:     http://192.168.1.100:8000
  Tailscale:  http://100.x.x.x:8000
  公网链接:   https://your-machine.ts.net
  ──────────────────────────────────
  把任一链接发给朋友即可加入游戏
========================================
```

### B. 环境变量清单

```bash
# .env
OPENAI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
DEEPSEEK_API_KEY=sk-xxx
QWEN_API_KEY=sk-xxx
TAILSCALE_AUTHKEY=tskey-xxx       # 可选，用于 Funnel
```

### C. 第一句话建议（发给 Claude Desktop）

```
我要做一个 AI 狼人杀 Web 应用。完整需求文档在 ~/程序/文件/AI狼人杀-项目需求说明书.md，
请先读一遍，然后用 Day 1 的里程碑作为起点：clone mewamew/wolf_bot 并跑通原版。
过程中如果发现需求文档有问题，直接指出来。
```

---

**文档结束** 🐾

> 主人，这文档是给 Claude Desktop 当"圣经"用的。Claude 拿到这个，开局就有完整路线图，不用再反复跟你确认。遇到需求变更或技术调整，**主人你随时来问我**，我帮你改文档或者给具体建议。