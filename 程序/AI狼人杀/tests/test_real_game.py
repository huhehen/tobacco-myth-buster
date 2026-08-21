"""真实模型完整局验证：9 个 AI 玩家全部由真实 LLM 驱动（无 mock），完整跑一局。

验证内容：
- 9 个 AI 玩家的发言/夜晚行动/投票全部由真实大模型推测
- 游戏能正常推进到结束（狼人/好人阵营获胜）
- 统计：每阶段耗时、发言次数、模型分配、错误次数
"""
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# API Key 从环境变量或 backend/.env 读取，绝不硬编码
os.environ.setdefault("NVIDIA_API_KEY", "")
os.environ.setdefault("AGNES_API_KEY", "")

from backend.ai.llm_pool import LLMPool
from backend.ai.speaker import LlmSpeaker
from backend.config import load_env_file, load_models
from backend.game.director import GameDirector
from backend.game.state_machine import Game, GamePlayer
from backend.room.manager import Player, Room

load_env_file()

# .env 也加载后重新读模型（保证环境变量完整）
MODELS = load_models()


def make_room(player_count: int = 9) -> Room:
    room = Room(code="REAL", name="真实验证局", max_players=player_count, host_nickname="小明")
    room.host_player_id = 1
    for i in range(player_count):
        pid = i + 1
        room.players[pid] = Player(player_id=pid, nickname=f"玩家{pid}",
                                   is_human=False, is_ai=True)
    return room


async def test_real_full_game():
    room = make_room(9)
    stats = {
        "speech_count": 0,
        "llm_calls": 0,
        "errors": 0,
        "phase_times": [],
        "last_phase": None,
        "phase_start": time.time(),
        "models_used": set(),
        "day": 1,
    }
    t_start = time.time()

    async def on_broadcast(code, msg, only=None):
        t = msg["type"]
        # 阶段耗时统计
        if t == "phase_changed":
            now = time.time()
            stats["phase_times"].append((stats["last_phase"], round(now - stats["phase_start"], 1)))
            stats["last_phase"] = f"{msg['phase']}第{msg.get('day','')}天"
            stats["phase_start"] = now
            stats["day"] = msg.get("day", stats["day"])
            print(f"  📌 阶段: {msg['phase']} 第{msg.get('day','')}天")
        elif t == "night_result":
            died = msg.get("died_names") or []
            print(f"  🌙 夜晚结束，死亡: {died if died else '平安夜'}")
        elif t == "vote_result":
            name = msg.get("eliminated_name")
            print(f"  🗳️ 投票结果: {name if name else '平票无人出局'}")
        elif t == "hunter_shot":
            print(f"  💥 猎人开枪!")
        elif t == "speech_delta" and msg.get("final"):
            stats["speech_count"] += 1
            print(f"  💬 {msg['player_id']}号发言: {msg['text'][:50]}")
        elif t == "game_over":
            elapsed = time.time() - t_start
            print(f"\n🏁 游戏结束: {msg['winner']}（总耗时 {elapsed:.0f} 秒）")

    pool = LLMPool(MODELS)
    await pool.start()
    assert pool.has_models(), "没有可用模型！"

    director = GameDirector(room, on_broadcast)
    speaker = LlmSpeaker(pool)
    speaker.room_code = room.code

    # 统计 LLM 调用与错误
    orig_submit = pool.submit

    async def counting_submit(task_type, *args, **kwargs):
        stats["llm_calls"] += 1
        try:
            result = await orig_submit(task_type, *args, **kwargs)
            if isinstance(result, Exception):
                stats["errors"] += 1
                print(f"  ⚠️ LLM 调用失败: {type(result).__name__}: {result}")
            return result
        except Exception as e:
            stats["errors"] += 1
            print(f"  ⚠️ 提交异常: {type(e).__name__}: {e}")
            raise

    pool.submit = counting_submit
    director.ai_speaker = speaker

    print("🎮 开始真实模型完整局（9 个 AI 全部由真实 LLM 驱动）...")
    await director.run()

    # 验证
    types = [e[0] for e in stats["phase_times"]]
    print(f"\n===== 验证结果 =====")
    print(f"✅ AI 发言次数: {stats['speech_count']}")
    print(f"✅ LLM 调用总次数: {stats['llm_calls']}")
    print(f"⚠️ 调用失败次数: {stats['errors']}")
    print(f"✅ 经历阶段: {types}")
    for phase, dur in stats["phase_times"]:
        if phase:
            print(f"   {phase}: {dur}s")
    assert stats["speech_count"] > 0, "没有 AI 发言"
    assert stats["errors"] == 0, f"存在 {stats['errors']} 次调用失败"

    # 验证会话隔离与模型分配（仅检查参与过行动的玩家，死亡玩家无会话是正常行为）
    sessions = {pid: pool.get_session(room.code, pid) for pid in room.players}
    active = [pid for pid, s in sessions.items() if s is not None]
    assert len(active) >= 5, f"只有 {len(active)} 个玩家有会话（应至少 5 个存活发言者）"
    models = {s.client.model_name for s in sessions.values() if s is not None}
    print(f"✅ {len(active)} 个 AI 玩家有独立会话，模型分配: {models}")
    print(f"⚠️ 未参与行动（死亡等）: {[pid for pid in room.players if pid not in active]}")

    await pool.stop()
    print("\n🎉 真实模型完整局验证通过")


if __name__ == "__main__":
    asyncio.run(test_real_full_game())
