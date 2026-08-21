"""M2 专项验证：女巫救毒、猎人开枪、平票不死。"""
import asyncio
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.game.director import FakeSpeaker, GameDirector
from backend.game.judge import hunter_can_shoot, pick_wolf_target, tally_votes
from backend.game.roles import get_role_config, is_wolf
from backend.game.state_machine import Game, GamePlayer
from backend.room.manager import Player, Room


def make_game(roles: dict) -> Game:
    """按指定角色顺序构造一局（player_id 从 1 开始）。"""
    players = []
    for i, role in enumerate(roles, start=1):
        players.append(GamePlayer(player_id=i, nickname=f"玩家{i}", is_ai=True, role=role))
    return Game(players)


def test_witch_save_and_poison():
    """女巫救毒：救活被狼杀的玩家；毒药杀死目标。"""
    game = make_game(["狼人", "村民", "女巫", "村民", "村民"])
    # 夜晚：狼人杀 2 号，女巫救人
    game.apply_night_kill(2)
    game.apply_witch_save()
    assert game.dead_tonight == [], f"解药应救活死者: {game.dead_tonight}"
    print("✅ 女巫解药救人成功")

    # 毒人
    game.apply_witch_poison(4)
    assert game.dead_tonight == [4]
    died = game.resolve_night()
    assert died == [4] and not game.players[4].alive
    print("✅ 女巫毒药杀人成功")


def test_hunter_shoot():
    """猎人被狼杀可开枪带走一人；被毒死的猎人不可开枪。"""
    game = make_game(["猎人", "村民", "村民", "狼人"])
    game.kill(1, died_by="狼人")  # 猎人被狼杀
    assert hunter_can_shoot(game, 1)
    game.players[1].shot_used = True
    game.kill(4, died_by="枪击")  # 带走狼人
    assert not game.players[4].alive
    print("✅ 猎人开枪验证成功")

    # 被毒死的猎人不可开枪
    game2 = make_game(["猎人", "村民", "村民", "狼人"])
    game2.kill(1, died_by="毒药")
    assert not hunter_can_shoot(game2, 1), "毒死的猎人不应能开枪"
    print("✅ 毒死猎人不可开枪验证成功")


def test_witch_poison_overlap_wolf_kill():
    """毒药与狼刀重叠：同一目标只死一次；不同目标都死。"""
    # 毒药目标是狼刀目标 → 只死一次（死因毒药）
    game = make_game(["狼人", "村民", "女巫", "村民", "村民"])
    game.apply_night_kill(2)
    game.apply_witch_poison(2)
    died = game.resolve_night()
    assert died == [2], f"重叠目标应只死一次: {died}"
    assert not game.players[2].alive
    assert game.players[2].died_by == "毒药"
    print("✅ 毒药与狼刀重叠只死一次")

    # 毒药目标是另一人 → 两人都死
    game2 = make_game(["狼人", "村民", "女巫", "村民", "村民"])
    game2.apply_night_kill(2)
    game2.apply_witch_poison(4)
    died2 = game2.resolve_night()
    assert set(died2) == {2, 4}, f"两个目标都应死: {died2}"
    assert game2.players[2].died_by == "狼人"
    assert game2.players[4].died_by == "毒药"
    print("✅ 毒药与狼刀不同目标都死")


def test_guard_blocks_wolf_kill():
    """守卫守护狼刀目标 → 平安夜。"""
    game = make_game(["狼人", "村民", "守卫", "村民", "村民"])
    game.apply_night_kill(2)
    game.apply_guard(3, 2)
    died = game.resolve_night()
    assert died == [], f"守卫守护应平安夜: {died}"
    assert game.players[2].alive
    print("✅ 守卫守护平安夜验证成功")


def test_tally_tie():
    """平票不死。"""
    votes = {1: 2, 2: 3, 3: 4}   # 2号1票, 3号1票, 4号1票 → 平票
    assert tally_votes(votes) is None, "平票应无人出局"
    votes2 = {1: 3, 2: 3, 3: 3}  # 3号得3票 → 出局
    assert tally_votes(votes2) == 3, "票数最多者应出局"
    print("✅ 平票不死 + 多数出局验证成功")


def test_hunter_shot_after_execution():
    """猎人被放逐后应能开枪（规则测试）。"""
    game = make_game(["猎人", "村民", "狼人", "狼人"])
    # 白天放逐猎人
    game.execute(1)
    assert not game.players[1].alive
    assert game.players[1].died_by == "放逐"
    assert hunter_can_shoot(game, 1), "放逐的猎人应能开枪"
    print("✅ 猎人被放逐后可开枪验证成功")


def test_wolf_win_boundary():
    """狼人胜利边界：狼数 >= 好数 → 狼人胜；狼全灭 → 好人胜。"""
    # 1 狼 2 好 → 未胜
    game = make_game(["狼人", "村民", "村民"])
    result = game.check_winner()
    assert result is None, "1 狼 2 好不应结束"

    # 2 狼 2 好 → 狼人胜
    game2 = make_game(["狼人", "狼人", "村民", "村民"])
    result2 = game2.check_winner()
    assert result2 == "狼人阵营", "2 狼 2 好应狼人胜"
    assert game2.phase == "结束"

    # 1 狼 1 好 → 狼人胜
    game3 = make_game(["狼人", "村民"])
    result3 = game3.check_winner()
    assert result3 == "狼人阵营"

    # 所有狼人死 → 好人胜
    game4 = make_game(["狼人", "村民", "村民", "预言家"])
    game4.kill(1)  # 狼死了
    result4 = game4.check_winner()
    assert result4 == "好人阵营", "狼全灭应好人胜"
    print("✅ 狼人胜利边界验证成功")


def test_guard_does_not_save_poisoned():
    """守卫守护狼刀目标时，女巫毒的另一人仍应死亡（C4 回归测试）。"""
    game = make_game(["狼人", "村民", "守卫", "女巫", "村民"])
    # 狼刀 2 号，女巫毒 4 号，守卫守 2 号
    game.apply_night_kill(2)
    game.apply_witch_poison(4)
    game.apply_guard(3, 2)
    died = game.resolve_night()
    # 2 号被守卫守护 → 平安（不被狼刀杀）
    # 4 号被女巫毒 → 仍应死
    assert 2 not in died, f"被守护目标不应死: {died}"
    assert 4 in died, f"被毒目标应死: {died}"
    assert game.players[4].died_by == "毒药"
    print("✅ 守卫不误救女巫毒药受害者验证成功")


def test_parse_number_no_substring_match():
    """parse_number 不应将「11号」误判为「1号」（C3 回归测试）。"""
    from backend.ai.speaker import parse_number
    alive_12 = list(range(1, 13))
    # 注意：「N号」格式必须紧连，中间不能有空格
    assert parse_number("我投11号", alive_12) == 11, "11号 不应被误判为 1"
    assert parse_number("11号玩家很可疑", alive_12) == 11
    assert parse_number("12号是狼人", alive_12) == 12
    # 纯数字行测试
    assert parse_number("11", alive_12) == 11
    assert parse_number("1", alive_12) == 1
    print("✅ parse_number 子串匹配修复验证成功")


def test_wolf_target_pick():
    """狼人协商：多数优先，平票随机。"""
    game = make_game(["狼人", "狼人", "狼人", "村民", "村民"])
    # 2 只狼选 4，1 只狼选 5 → 4 号
    target = pick_wolf_target(game, [4, 4, 5])
    assert target == 4
    # 平票 → 随机但必须是好人
    target2 = pick_wolf_target(game, [4, 5])
    assert target2 in (4, 5)
    print("✅ 狼人协商目标选择验证成功")


def test_role_config():
    """角色配置：6/9/12 人局。"""
    assert get_role_config(6) == {"狼人": 1, "预言家": 1, "村民": 4}
    assert sum(get_role_config(9).values()) == 9
    assert sum(get_role_config(12).values()) == 12
    assert get_role_config(12)["守卫"] == 1
    print("✅ 角色配置验证成功")


if __name__ == "__main__":
    test_witch_save_and_poison()
    test_hunter_shoot()
    test_witch_poison_overlap_wolf_kill()
    test_guard_blocks_wolf_kill()
    test_tally_tie()
    test_wolf_target_pick()
    test_role_config()
    test_hunter_shot_after_execution()
    test_wolf_win_boundary()
    test_guard_does_not_save_poisoned()
    test_parse_number_no_substring_match()
    print("\n🎉 M2 专项规则测试全部通过")
