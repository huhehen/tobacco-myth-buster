"""夜间阶段：狼人杀人、预言家查验、女巫救人/毒人、守卫守护、猎人开枪。"""
import asyncio
import random
import time

from ..judge import (
    divine_valid,
    guard_valid,
    hunter_can_shoot,
    pick_wolf_target,
    valid_target,
    witch_can_poison,
    witch_can_save,
)
from ..roles import is_wolf
from ..state_machine import Game, GamePlayer

# 上帝视角日志的阶段 / 种类标识
DECISION_KIND_LABELS = {
    "wolf_proposal": "狼人提议",
    "wolf_consensus": "狼群决议",
    "divine": "预言家查验",
    "witch_save": "女巫救人",
    "witch_poison": "女巫毒人",
    "guard": "守卫守护",
    "hunter_shoot": "猎人开枪",
    "vote": "投票",
}


class NightDirector:
    """夜间阶段导演：编排夜晚 5 步流程。"""

    def __init__(self, director):
        """director: GameDirector 实例（用于委派广播、记录决策日志等）"""
        self.director = director
        self.game: Game = director.game
        self.broadcast = director.broadcast
        self.room = director.room

    # ---------- 公开入口 ----------
    async def run_night_phase(self):
        """执行完整夜晚流程。"""
        game = self.game

        # 1. 狼人协商杀人
        wolves = game.wolves()
        await self.director._narrate(
            "狼人请睁眼，请选择今晚要袭击的玩家",
            only=[w.player_id for w in wolves],
        )
        proposals = []
        for wolf in wolves:
            if wolf.is_ai:
                target = await self.director._ai_decide(wolf, "狼人提议")
            else:
                target = await self.director._human_act(wolf, "狼人提议")
            proposals.append(target or 0)
            # 上帝视角日志：每只狼的提议 + CoT 思考
            thinking = game.decision_thinking.get(wolf.player_id, "")
            await self.director._record_decision(self.director._make_decision_log(
                day=game.day, phase="夜晚",
                kind="wolf_proposal",
                actor=wolf,
                thinking=thinking,
                target_id=target or 0,
                target_name=f"{target}号玩家" if target else "",
            ))
        target = pick_wolf_target(game, proposals)
        if target is None:
            good = [pid for pid in game.alive_ids() if not is_wolf(game.players[pid].role)]
            if good:
                target = random.choice(good)
        # 狼群决议日志：汇总每只狼的提议 + 最终击杀目标
        proposal_summary = [
            {"wolf_id": w.player_id, "wolf_nickname": w.nickname, "target_id": t}
            for w, t in zip(wolves, proposals)
        ]
        await self.director._record_decision(self.director._make_decision_log(
            day=game.day, phase="夜晚",
            kind="wolf_consensus",
            actor=None,
            thinking="狼群投票汇总",
            target_id=target or 0,
            target_name=f"{target}号玩家" if target else "",
            extra={
                "actor_role": "狼群",
                "proposals": proposal_summary,
            },
        ))
        if target is not None:
            game.apply_night_kill(target)
        # 狼刀目标属狼人私密信息：只记入 game 状态，不进 full_record（防泄漏）
        game.night_wolf_target = target or 0

        # 2. 预言家查验
        for player in game.players.values():
            if player.role == "预言家" and player.alive:
                await self.director._narrate(
                    "预言家请睁眼，请选择要查验的玩家",
                    only=[player.player_id],
                )
                if player.is_ai:
                    div_target = await self.director._ai_decide(player, "预言家查验")
                else:
                    div_target = await self.director._human_act(player, "预言家查验")
                # 上帝视角日志：查验决策
                thinking = game.decision_thinking.get(player.player_id, "")
                if div_target:
                    await self.director._record_decision(self.director._make_decision_log(
                        day=game.day, phase="夜晚",
                        kind="divine",
                        actor=player,
                        thinking=thinking,
                        target_id=div_target,
                        target_name=f"{div_target}号玩家",
                        extra={
                            "result": "狼人" if is_wolf(game.players[div_target].role) else "好人",
                        },
                    ))
                if div_target and divine_valid(game, player.player_id, div_target):
                    game.apply_divine(player.player_id, div_target)
                    game.full_record.append({
                        "type": "divine",
                        "day": game.day,
                        "seer": player.player_id,
                        "target": div_target,
                        "result": "狼人" if is_wolf(game.players[div_target].role) else "好人",
                    })
                    await self.director._send(player.player_id, {
                        "type": "divine_result",
                        "player_id": player.player_id,
                        "target_id": div_target,
                        "camp": game.divine_result[player.player_id][div_target],
                    })

        # 3. 女巫行动
        for player in game.players.values():
            if player.role == "女巫" and player.alive:
                await self.director._narrate(
                    "女巫请睁眼，请选择是否使用药剂",
                    only=[player.player_id],
                )
                await self._run_witch(player)

        # 4. 守卫行动（12 人局）
        for player in game.players.values():
            if player.role == "守卫" and player.alive:
                await self.director._narrate(
                    "守卫请睁眼，请选择今晚要守护的玩家",
                    only=[player.player_id],
                )
                if player.is_ai:
                    guard_target = await self.director._ai_decide(player, "守卫守护")
                else:
                    guard_target = await self.director._human_act(player, "守卫守护")
                # 上帝视角日志：守卫守护决策
                thinking = game.decision_thinking.get(player.player_id, "")
                if guard_target:
                    await self.director._record_decision(self.director._make_decision_log(
                        day=game.day, phase="夜晚",
                        kind="guard",
                        actor=player,
                        thinking=thinking,
                        target_id=guard_target,
                        target_name=f"{guard_target}号玩家",
                    ))
                if guard_target and guard_valid(game, player.player_id, guard_target):
                    game.apply_guard(player.player_id, guard_target)
                    await self.director._send(player.player_id, {
                        "type": "guard_result",
                        "player_id": player.player_id,
                        "target_id": guard_target,
                    })

        # 5. 天亮结算
        died = game.resolve_night()

        # 记录公开死讯（所有玩家可见）——死亡名单是公开信息
        if died:
            game.full_record.append({
                "type": "death",
                "day": game.day,
                "died": died,
            })

        if died:
            text = f"天亮了，昨晚 {self.director._join_ids(died)} 死亡"
        else:
            text = "天亮了，昨晚是平安夜"
        await self.director._narrate(text, public=True)
        await self.broadcast(self.room.code, {
            "type": "night_result",
            "day": game.day,
            "died_ids": died,
            "died_names": [f"{d}号玩家" for d in died],
            "narrator_text": text,
        })

        # 死亡瞬间补发上帝视角历史（只对新死者；_notified_dead 去重）
        if died:
            await self.director._notify_newly_dead(died)

        # 6. 猎人被狼杀可开枪
        await self._check_hunter_shoot(died)

        # 7. 检查胜负
        if game.check_winner():
            return
        game.enter_day()
        await self.broadcast(self.room.code, {
            "type": "phase_changed",
            "phase": "白天发言",
            "day": game.day,
        })

    # ---------- 内部方法 ----------
    async def _run_witch(self, witch: GamePlayer):
        game = self.game
        # 救人（仅当晚有可救对象时）
        if game.dead_tonight and witch_can_save(game, witch.player_id):
            if witch.is_ai:
                save = await self.director._ai_decide(witch, "女巫救人")
            else:
                save = await self.director._human_act(witch, "女巫救人")
            # 上帝视角日志：女巫救人决策
            thinking = game.decision_thinking.get(witch.player_id, "")
            await self.director._record_decision(self.director._make_decision_log(
                day=game.day, phase="夜晚",
                kind="witch_save",
                actor=witch,
                thinking=thinking,
                target_id=game.dead_tonight[0] if game.dead_tonight else 0,
                target_name=f"{game.dead_tonight[0]}号玩家" if game.dead_tonight else "",
                extra={"decision_text": "使用解药救人" if save else "不使用解药"},
            ))
            if save:
                game.apply_witch_save()
                await self.director._send(witch.player_id, {
                    "type": "witch_action",
                    "player_id": witch.player_id,
                    "action": "救人",
                })
        # 毒人（只要毒药未用，就询问是否使用及目标）
        if not game.witch_used_poison:
            if witch.is_ai:
                poison_target = await self.director._ai_decide(witch, "女巫毒人")
            else:
                poison_target = await self.director._human_act(witch, "女巫毒人")
            # 上帝视角日志：女巫毒人决策
            thinking = game.decision_thinking.get(witch.player_id, "")
            if poison_target:
                await self.director._record_decision(self.director._make_decision_log(
                    day=game.day, phase="夜晚",
                    kind="witch_poison",
                    actor=witch,
                    thinking=thinking,
                    target_id=poison_target,
                    target_name=f"{poison_target}号玩家",
                    extra={"decision_text": "使用毒药"},
                ))
            if poison_target and witch_can_poison(game, witch.player_id, poison_target):
                game.apply_witch_poison(poison_target)
                await self.director._send(witch.player_id, {
                    "type": "witch_action",
                    "player_id": witch.player_id,
                    "action": "毒人",
                    "target_id": poison_target,
                })

    async def _check_hunter_shoot(self, died_ids: list[int]):
        game = self.game
        for pid in died_ids:
            player = game.players[pid]
            if player.role == "猎人" and hunter_can_shoot(game, pid):
                await self.director._narrate(
                    f"{pid}号玩家被杀害，猎人发动技能，请选择开枪带走谁",
                    only=[pid],
                )
                if player.is_ai:
                    shoot_target = await self.director._ai_decide(player, "猎人开枪")
                else:
                    shoot_target = await self.director._human_act(player, "猎人开枪")
                # 上帝视角日志：猎人开枪决策
                thinking = game.decision_thinking.get(player.player_id, "")
                if shoot_target:
                    await self.director._record_decision(self.director._make_decision_log(
                        day=game.day, phase="夜晚",
                        kind="hunter_shoot",
                        actor=player,
                        thinking=thinking,
                        target_id=shoot_target,
                        target_name=f"{shoot_target}号玩家",
                        extra={"trigger": f"{pid}号玩家死亡触发"},
                    ))
                if shoot_target and valid_target(game, shoot_target):
                    player.shot_used = True
                    game.kill(shoot_target, died_by="枪击")
                    await self.director._narrate(f"猎人开枪带走了 {shoot_target}号玩家", public=True)
                    await self.broadcast(self.room.code, {
                        "type": "hunter_shot",
                        "hunter_id": pid,
                        "target_id": shoot_target,
                        "narrator_text": f"猎人开枪带走了 {shoot_target}号玩家",
                    })
                    # 猎人开枪致死的玩家也需要补发上帝视角历史
                    await self.director._notify_newly_dead([shoot_target])
                if game.check_winner():
                    return