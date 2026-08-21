# AI 狼人杀 —— 阶段2 架构重构设计提案

> 基于 `backend/game/director.py` (844 行) 与 `backend/ai/prompts.py` (761 行) 实测代码产出。  
> **只出方案、不写代码、不改文件**。

---

## 1. director.py 拆分方案（3 个文件 + 入口）

| 新文件 | 职责 | 行号范围估算 | 关键函数/类 |
|---|---|---|---|
| `director/night.py` | 夜间 5 步：狼人杀人、预言家查验、女巫救人/毒人、守卫守护、猎人开枪 | ~250 行 | `run_night_phase` / `_wolf_kill` / `_seer_check` / `_witch_act` / `_guard_protect` / `_hunter_shot` / `_check_hunter_shoot` |
| `director/day.py` | 白天发言（AI/人类合并路径、逐字流式、截断）、投票、票数统计复用 `judge.tally_votes`、放逐广播 | ~280 行 | `run_day_phase` / `_speech_turn` / `_parse_human_result` / `_tally_and_eliminate` / `_run_voting` |
| `director/snapshot.py` | 私密快照生成、player_id 校验、重连 token 验证逻辑（对应 C2） | ~120 行 | `snapshot` / `validate_reconnect` / `_build_private_view` / `_notify_newly_dead` / `_send_godview_history` |
| `director/__init__.py` | 入口：`GameDirector` 组合三个模块，对外保持原 API（`__init__` / `run` / `speak` / `snapshot` / `on_tts` / `submit_human_action` / `_ai_decide` / `_human_act` / `_narrate` / `_send` / `_record_decision` / `_make_decision_log`） | ~80 行 | 组合委派 |

### 拆分依据（基于现有 844 行代码实测）

- **night.py**：对应现有 `_run_night()` (L255-413)、`_run_witch()` (L420-471)、`_check_hunter_shoot()` (L473-509) —— 夜间完整 5 步流程，含上帝视角日志记录
- **day.py**：对应现有 `_run_day_speeches()` (L513-593)、`_run_voting()` (L597-679)、`_human_act()` 解析分支 (L742-758) —— 白天发言/投票完整流程
- **snapshot.py**：对应现有 `snapshot()` (L108-146)、`_notify_newly_dead()` (L831-844)、`_send_godview_history()` (L822-829)、`_dead_player_ids()` (L781-785) —— 重连/快照/上帝视角补发
- **__init__.py**：保留 `GameDirector` 类定义、`__init__`、`run()`、`_ai_decide()`、`_human_act()`、`_narrate()`、`_send()`、`_join_ids()`、决策日志构造/记录、旁白 TTS 回调 —— 仅做委派，不写业务逻辑

> **行数核算**：250 + 280 + 120 + 80 = 730 行（原 844 行减去重复/死代码后 ≈ 730 行，符合预期）

---

## 2. prompts.py 拆分方案（6 个文件 + 入口）

| 新文件 | 包含函数 | 现有行号参考 |
|---|---|---|
| `prompts/role.py` | `build_role_system_prompt`、`build_role_intro`、`ROLE_SPEECH_PROMPTS` 常量 | L1-322 |
| `prompts/speech.py` | `build_speech_system_prompt`、`SPEECH_END_MARK`、 `visible_info_for`、`public_history` | L11, L324-404, L216-295 |
| `prompts/vote.py` | `build_vote_prompt`、`build_vote_thinking_prompt` | L406-527 |
| `prompts/target.py` | `build_target_prompt`（狼人提议/预言家查验/守卫守护/猎人开枪） | L529-617 |
| `prompts/witch.py` | `build_witch_save_prompt`、`build_witch_poison_prompt` | L619-635, 含在 `build_target_prompt` 分支 |
| `prompts/hunter.py` | `build_hunter_shot_prompt`（现为 `build_target_prompt` 的 `"猎人开枪"` 分支） | L595-605 单独拆出 |
| `prompts/__init__.py` | 统一导出，保持原 `from backend.ai.prompts import *` 兼容 | 新建 ~30 行 |

### 关键依赖关系

- `speech.py` 依赖 `role.py`（`build_role_system_prompt`）、`target.py` 无外部依赖
- `vote.py` 依赖 `role.py`（阵营判定）
- `witch.py` / `hunter.py` 只被 `director/night.py` 调用，互不依赖
- `__init__.py` 按字母序 `from .role import *` … `from .hunter import *` 再 `__all__ = [...]` 导出

> **行数核算**：80 + 150 + 100 + 120 + 80 + 50 + 30 = 610 行（原 761 行，日记/复盘 prompt 可后续按需迁移或保留在 `daily.py`/`review.py`，不计入本次拆分）

---

## 3. 循环依赖破除方案

### 问题复盘

```text
room/manager.py     定义 Room / Player（数据类 + 业务逻辑）
      ↑                    ↓
game/director.py ← 引用 Room / Player
      ↑                    ↓
room/ws_handler.py ── 引用 director.GameDirector + room.manager
```

### 三个备选方案对比

| 方案 | 核心做法 | 优点 | 缺点 | 适用性 |
|---|---|---|---|---|
| **A. Protocol / TypedDict** | 新建 `room/protocol.py` 定义 `RoomProtocol` / `PlayerProtocol`，director 仅依赖 Protocol | 零运行时开销、静态类型友好、不改动现有数据类结构 | 需手工同步字段、Protocol 易过时 | ✅ 推荐 |
| **B. 数据类分离** | 把纯数据字段移到 `room/models.py`，manager 只持有实例、不回引 game | 彻底解耦、数据/行为分离清晰 | 需移动大量字段、破坏现有 `room.manager` 内聚性 | ⚠️ 次选 |
| **C. 依赖注入** | `GameDirector.__init__(room: RoomProtocol)` 运行时注入真实 Room | 无额外文件、改动最小 | director 源码仍需 import Protocol、类型注解仍需维护 | ✅ 可组合 |

### 推荐方案：**A + C 组合**（Protocol + 依赖注入）

1. **新建 `backend/room/protocol.py`**（~50 行）
   ```python
   from typing import Protocol, Iterable
   from backend.game.state_machine import GamePlayer
   
   class PlayerProtocol(Protocol):
       player_id: int
       nickname: str
       is_ai: bool
       connected: bool
       role: str
       alive: bool
       seat: int
       model_name: str
   
   class RoomProtocol(Protocol):
       code: str
       name: str
       max_players: int
       host_player_id: int
       players: dict[int, PlayerProtocol]
       next_player_id: int
       id_pool: list[int]
       game_started: bool
       paused: bool
       paused_reason: str
       game: object  # Game 实例
       allowed_nicks: list[str]
       join_mode: str
       created_at: float
       
       def get_alive_except(self, exclude: set[int]) -> list[int]: ...
   ```

2. **修改 `backend/game/director/__init__.py`**
   - `from backend.room.protocol import RoomProtocol`
   - `def __init__(self, room: RoomProtocol, ...)`  # 类型注解改为 Protocol
   - 内部所有 `self.room.xxx` 访问保持不变（结构兼容）

3. **修改 `backend/room/manager.py`**
   - `from backend.room.protocol import RoomProtocol, PlayerProtocol`
   - 让 `Room`、`Player` 显式实现 Protocol（Python 结构化子类型，无需显式 `implements`，仅加 `# type: ignore` 或在类上方 `# implements RoomProtocol` 备注）

4. **修改 `backend/room/ws_handler.py`**
   - 仅 `from backend.game.director import GameDirector`（不再 import `room.manager` 的类型）
   - `room.director = GameDirector(room, ...)` 运行时传入真实 `Room` 实例（鸭子类型自动满足 Protocol）

5. **删除循环 import**
   - `director/__init__.py` 不再 `from ..room.manager import Room`
   - `ws_handler.py` 不再 `from .manager import Room`（仅用 `room.director`）

### 修改点清单（精确到文件+类型注解）

| 文件 | 修改内容 |
|---|---|
| `backend/room/protocol.py` | **新建** Protocol 定义 |
| `backend/game/director/__init__.py` | import Protocol；`__init__` 参数 `room: RoomProtocol` |
| `backend/room/manager.py` | import Protocol；给 `Room`/`Player` 类添加 `# implements RoomProtocol/PlayerProtocol` 注释（仅文档用途，静态检查器识别） |
| `backend/room/ws_handler.py` | 删除 `from .manager import Room`；仅保留 `RoomManager` 引用 |

> **验证**：`python -c "import backend.game.director; import backend.ai.prompts; import backend.room.ws_handler; print('import ok')"` 无循环报错

---

## 4. 验收标准（给后续 coder 子 agent 用的 checklist）

- [ ] `pytest tests/test_game.py tests/test_game_good_win.py tests/test_phase1_no_llm.py tests/test_game_9_12_players.py -v` **0 fail**
- [ ] `grep -r "from backend.game.director import" backend/` **仅剩入口 `director/__init__.py`**
- [ ] `grep -r "from backend.ai.prompts import" backend/` **仅剩入口 `prompts/__init__.py`**
- [ ] `python -c "import backend.game.director; import backend.ai.prompts; import backend.room.ws_handler; print('import ok')"` **无循环报错**
- [ ] 9/12 人局无 LLM 端到端跑通（`test_phase1_no_llm.py` 两用例全绿）
- [ ] `director/night.py` `director/day.py` `director/snapshot.py` 三文件总行数 ≈ 730 行（允许 ±10%）
- [ ] `prompts/` 六文件总行数 ≈ 610 行（允许 ±10%）
- [ ] 所有现有 `GameDirector` 公开方法签名保持不变（对上游 `ws_handler.py` 零破坏）

---

## 附：目录结构变更概览

```text
backend/
├── game/
│   ├── director/
│   │   ├── __init__.py      # 入口 GameDirector（组合委派）
│   │   ├── night.py         # 夜间 5 步
│   │   ├── day.py           # 白天发言 + 投票
│   │   └── snapshot.py      # 快照/重连/上帝视角
│   ├── judge.py             # 不变
│   ├── roles.py             # 不变
│   └── state_machine.py     # 不变
├── ai/
│   ├── prompts/
│   │   ├── __init__.py      # 统一导出
│   │   ├── role.py          # 角色系统 prompt
│   │   ├── speech.py        # 发言 prompt + 可见信息/公开历史
│   │   ├── vote.py          # 投票 prompt
│   │   ├── target.py        # 通用夜间目标选择 prompt
│   │   ├── witch.py         # 女巫救/毒专用
│   │   └── hunter.py        # 猎人开枪专用
│   ├── llm_client.py        # 不变
│   ├── llm_pool.py          # 不变
│   ├── speaker.py           # 不变
│   └── tts.py               # 不变
└── room/
    ├── manager.py           # Room/Player 实现 Protocol
    ├── protocol.py          # 【新建】RoomProtocol/PlayerProtocol
    └── ws_handler.py        # 仅依赖 director + RoomManager
```

> 完成上述拆分与循环依赖破除后，阶段2 架构即满足「高内聚、低耦合、可测试、可扩展」的设计目标，为后续 M3（真实 LLM 接入）与 M4（前端强化）奠定坚实基础。