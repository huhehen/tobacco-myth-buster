# 🐺 AI 狼人杀

局域网内可玩的网页版狼人杀：人类与 AI 同局，AI 由不同大模型扮演，支持语音播报。

## 功能

- **人类 + AI 混合对局**：人数不足时 AI 自动补位（房主只设总人数即可）
- **多模型扮演**：2-3 个不同模型扮演不同 AI 玩家，会话互相隔离
- **局域网网页**：同一 WiFi 下的朋友用浏览器访问即可加入
- **语音播报**：AI 发言自动转语音（edge-tts，多音色）
- **真实推理**：AI 基于角色信息隔离发言，投票前综合全部发言推理
- **断线暂停**：玩家掉线游戏自动暂停，重连后恢复

## 快速开始

### 1. 安装依赖

```bash
cd "AI 狼人杀"
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
```

### 2. 配置模型（重要：留白由你自填）

编辑 `backend/config/models.json`，填入你使用的模型：

```json
{
  "models": [
    {
      "name": "DeepSeek",
      "provider": "openai_compatible",
      "base_url": "https://api.deepseek.com/v1",
      "api_key_env": "DEEPSEEK_API_KEY",
      "model": "deepseek-chat",
      "tts_voice": "zh-CN-YunxiNeural"
    }
  ]
}
```

> 兼容所有 OpenAI 兼容端点：DeepSeek / 通义千问 / 豆包 / GLM / Kimi 等。
> `base_url` 填 `/v1` 结尾的地址，`api_key_env` 是环境变量名，`tts_voice` 可留空（用默认音色）。
> 中文音色参考：`zh-CN-XiaoxiaoNeural`(女) `zh-CN-YunxiNeural`(男) `zh-CN-YunjianNeural`(沉稳男) `zh-CN-XiaoyiNeural`(甜美女)。

复制 `.env.example` 为 `.env` 并填入 API Key：

```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env 填入你的 key
```

### 3. 启动

```bash
.venv/bin/python -m backend.main
```

启动后终端会打印局域网地址（如 `http://192.168.1.100:8000`），把链接发给同一 WiFi 下的朋友即可加入。

### 4. 开始游戏

1. 房主输入昵称 → 选人数（6/9/12）→ 创建房间
2. 朋友输入昵称 + 房间码加入
3. 房主点「开始游戏」→ AI 自动补满空位 → 随机分配角色（中文）
4. 夜晚按角色行动，白天按座位依次发言，投票放逐
5. 狼人全灭 → 好人胜；狼人数 ≥ 好人数 → 狼人胜

## 异地联机（可选）

局域网之外的朋友可通过 Tailscale 加入：

1. 主机安装 Tailscale 并登录：`brew install tailscale && tailscale up`
2. 朋友安装 Tailscale 加入同一账号/网络
3. 主机启动游戏后，朋友访问 `http://<tailscale-ip>:8000`（`tailscale ip` 查询）

## 角色表（9 人局）

| 角色 | 阵营 | 数量 | 技能 |
|---|---|---|---|
| 狼人 | 狼人阵营 | 3 | 夜晚协商杀一人，互知同伙 |
| 预言家 | 好人阵营 | 1 | 每晚查验一名玩家身份 |
| 女巫 | 好人阵营 | 1 | 解药救活一人、毒药毒死一人（各一次） |
| 猎人 | 好人阵营 | 1 | 被放逐或被狼杀时可开枪带走一人 |
| 村民 | 好人阵营 | 3 | 无技能 |

## 测试

```bash
.venv/bin/python tests/test_room.py      # 房间逻辑
.venv/bin/python tests/test_ws.py        # WebSocket 断线重连
.venv/bin/python tests/test_game.py      # 完整局（假 AI）
.venv/bin/python tests/test_rules.py     # 角色规则
.venv/bin/python tests/test_llm.py       # LLM 会话隔离/串行（需 mock 服务器）
.venv/bin/python tests/test_human.py     # 人类玩家交互
.venv/bin/python tests/test_tts.py       # 语音生成
```
