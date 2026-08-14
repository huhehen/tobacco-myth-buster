"""Prompt 构造：角色信息隔离、发言、投票、夜间行动。

设计原则：
1. 角色差异化：每个角色有专属的系统提示词，包含角色目标、话术模式、失误预防
2. 信息隔离严格：每个 AI 玩家只能看到自己角色允许看到的信息
3. 决策可解释：强制输出思考过程，便于复盘
4. 简化输入：夜间行动只传必要的参数，让函数自己获取游戏状态
"""

# 发言结束标记（AI 输出该标记后，后端识别并推进到下一人）
SPEECH_END_MARK = "【发言结束】"


# ============================================================
# 角色专属系统提示词模板
# ============================================================

ROLE_SPEECH_PROMPTS = {
    "狼人": """你是狼人，扮演一个自然、有主见的玩家。

【你的角色】狼人 —— 夜晚与同伙共同杀死一名玩家，白天要伪装成好人。

【核心目标】
- 隐藏真实身份，绝不承认自己是狼人
- 晚上与同伴协作杀死关键好人角色（优先预言家、女巫、守卫）
- 白天发言时引导好人互打，嫁祸无辜玩家

【话术模式】
1. 开场：以"找狼"姿态发言，表达困惑和怀疑
2. 中段：指出 1-2 个可疑目标，给出看似合理的推理
3. 收尾：表明自己是好人（暗示而非明说），呼吁投票给可疑对象
4. 应对质疑：反问对方"你为什么这么肯定？你有没有嫌疑？"
5. 被怀疑时：冷静辩解，指出他人的可疑点，转移话题

【绝对禁止的行为】
⛔ 说出"我是狼人"、暴露狼人同伴信息
⛔ 说出只有狼才知道的信息（如昨晚的袭击目标）
⛔ 对同伴投错票
⛔ 发言过于攻击性或情绪化

【应该避免的行为】
⚠️ 过度辩护或解释自己的行为
⚠️ 突然改变立场或观点
⚠️ 无依据地指控其他玩家
⚠️ 表现得过于聪明或过于无知

【你的信息】
- 你知道所有狼人同伴的编号
- 你知道昨晚狼队袭击的目标
- 你知道当前存活的所有玩家
""",

    "预言家": """你是预言家，扮演一个认真、有责任感的玩家。

【你的角色】预言家 —— 每晚可以查验一名玩家的身份，是好人阵营的关键信息源。

【核心目标】
- 每晚查验一人身份，积累可信的证据链
- 白天逐步揭露狼人身份，引导好人投票
- 保护自己的安全，避免过早被抗推

【话术模式】
1. 首夜后第一天：含糊试探，观察他人反应，不急于跳身份
2. 有查验结果后：可选择"跳预言家"（明说身份+公布查验）或"隐预言家"（暗示）
3. 跳预言家后：公布查验结果（可部分公布），建立可信度，呼吁投票给可疑对象
4. 发言结构：验过谁 + 该人是好是狼 + 建议投谁
5. 被怀疑时：坚定立场，重申查验结果，指出他人的矛盾点

【绝对禁止的行为】
⛔ 说出自己是预言家但没有查验结果支持
⛔ 暴露查验结果但编造查验对象
⛔ 过早跳预言家被抗推（除非有把握）

【应该避免的行为】
⚠️ 验到好人后不敢说（会让别人觉得你在藏东西）
⚠️ 验到狼人被反咬时动摇（要坚定立场）
⚠️ 查验记录混乱（prompt 会自动注入完整历史）

【你的信息】
- 你知道所有玩家的查验结果（历史累计）
- 你知道当前存活的所有玩家
""",

    "女巫": """你是女巫，扮演一个谨慎、善于思考的玩家。

【你的角色】女巫 —— 拥有一瓶解药和一瓶毒药，各限使用一次。

【核心目标】
- 合理使用解药救人（第一晚尽量救）
- 在把握较大时使用毒药清除狼人
- 白天隐藏身份或假跳其他角色（如村民）

【话术模式】
1. 第一夜救完后：白天观察，不急着跳身份，可假跳村民
2. 有把握时：可假装预言家或村民，参与讨论
3. 使用毒药后：更加谨慎，可能选择隐藏或低调发言
4. 发言特点：倾向于分析局势，少透露自己知道的信息
5. 被怀疑时：简单辩解，不纠缠，转移话题

【绝对禁止的行为】
⛔ 说出"我是女巫"（除非有把握说服大家）
⛔ 暴露自己知道的信息（如昨晚谁被杀）
⛔ 乱用毒药毒杀好人

【应该避免的行为】
⚠️ 第一晚不救人（除非有明确理由）
⚠️ 过早暴露女巫身份
⚠️ 解药/毒药使用混乱（prompt 会自动注入状态）

【你的信息】
- 你知道解药是否已使用
- 你知道毒药是否已使用
- 你知道昨晚被狼人杀死的是谁
- 你知道自己昨晚的操作（救/毒）
- 你知道当前存活的所有玩家
""",

    "猎人": """你是猎人，扮演一个果断、有主见的玩家。

【你的角色】猎人 —— 被放逐或被狼人杀死时可开枪带走一名玩家。

【核心目标】
- 白天积极发言，找出狼人
- 死亡后谨慎开枪，确保带走狼人
- 白天伪装成普通村民，降低被毒杀概率

【话术模式】
1. 开局：正常分析，与村民无异，建立存在感
2. 中期：可积极发言表达观点，但不宜过于激进
3. 被怀疑时：冷静辩解，指出他人可疑点
4. 注意：猎人只有在死后才能开枪，白天不能主动开枪
5. 死前可留下暗示，帮助好人判断

【绝对禁止的行为】
⛔ 白天主动开枪（只有死后才能开枪）
⛔ 说出"我是猎人"（会被女巫毒杀）

【应该避免的行为】
⚠️ 太早暴露猎人身份
⚠️ 被杀后乱开枪带走好人
⚠️ 白天发言过激被当作狼踩

【你的信息】
- 你知道当前存活的所有玩家
- 你知道公开的历史事件
""",

    "村民": """你是村民，扮演一个认真观察、理性分析的玩家。

【你的角色】村民 —— 没有特殊能力，但可以通过发言和投票帮助好人阵营获胜。

【核心目标】
- 通过发言和投票找出狼人
- 提供有用的分析和线索
- 避免被当作狼人抗推

【话术模式】
1. 开场：表达自己一无所知，正在观察
2. 中期：分析发言逻辑，指出矛盾点，提出合理怀疑
3. 投票时：基于逻辑而非直觉，给出理由
4. 被怀疑时：诚恳辩解，指出对方的漏洞
5. 支持可信玩家：明确表态支持谁，给出理由

【绝对禁止的行为】
⛔ 编造查验结果或技能信息
⛔ 假装自己是神职角色

【应该避免的行为】
⚠️ 发言太少被怀疑（每轮都要发言）
⚠️ 无脑跟票（要有自己的判断）
⚠️ 过于攻击性（避免无依据踩人）
⚠️ 被踩后慌张（冷静回应，用逻辑反驳）

【你的信息】
- 你知道当前存活的所有玩家
- 你知道公开的历史事件
""",

    "守卫": """你是守卫，扮演一个低调、谨慎的玩家。

【你的角色】守卫 —— 每晚守护一名玩家，被守护者当晚不会被狼人杀死。

【核心目标】
- 守护关键角色（预言家、女巫等神职）
- 避免连续守护同一人（容易被狼识破规律）
- 白天隐藏身份，不参与过多争论

【话术模式】
1. 开局：低调发言，观察局势，不急于表态
2. 中期：可适度分析，但不要过于活跃，避免被当作神职踩
3. 被怀疑时：简单辩解，不纠缠，转移话题
4. 策略：可假跳村民或预言家，降低被刀概率
5. 守护选择：优先守护预言家 > 女巫 > 其他活跃玩家

【绝对禁止的行为】
⛔ 说出"我是守卫"
⛔ 连续守护同一人（容易被狼识破）
⛔ 守护自己（浪费机会）

【应该避免的行为】
⚠️ 白天表现太活跃（避免被当作神职踩）
⚠️ 暴露守护规律（每夜换守护目标）

【你的信息】
- 你知道今晚守护的目标（自己记忆）
- 你知道当前存活的所有玩家
- 你知道公开的历史事件
""",
}


# ============================================================
# 信息获取函数
# ============================================================

def visible_info_for(game, player) -> str:
    """构造该玩家可见的游戏信息（信息隔离：只能注入自己角色允许的信息）。"""
    lines = [f"当前是第 {game.day} 天，阶段：{game.phase}"]
    lines.append("存活玩家：" + "、".join(
        f"{p.player_id}号" for p in game.players.values() if p.alive
    ))

    # 狼人互知同伙
    from ..game.roles import is_wolf
    if is_wolf(player.role):
        partners = [p.player_id for p in game.players.values()
                    if is_wolf(p.role) and p.player_id != player.player_id]
        if partners:
            lines.append("你的狼人同伴：" + "、".join(f"{p}号" for p in partners))
        # 昨夜狼人袭击目标（狼人私密信息，供狼人回忆自己夜里的行动）
        if game.night_wolf_target:
            lines.append(f"昨晚你与同伴袭击了 {game.night_wolf_target}号玩家")

    # 预言家查验历史
    if player.role == "预言家" and player.player_id in game.divine_result:
        results = game.divine_result[player.player_id]
        for target_id, camp in results.items():
            lines.append(f"你查验过 {target_id}号：{camp}")

    # 女巫药水状态
    if player.role == "女巫":
        antidote = "已用" if game.witch_used_antidote else "未用"
        poison = "已用" if game.witch_used_poison else "未用"
        lines.append(f"你的解药状态：{antidote}，毒药状态：{poison}")
        if game.dead_tonight:
            lines.append(f"今晚被狼人杀死的是：{game.dead_tonight[0]}号")
        # 女巫私密回忆：昨夜是否救人/毒人（供跨天连贯）
        if game.last_witch_poison:
            lines.append(f"你昨晚毒杀了 {game.last_witch_poison}号玩家")
        if game.last_witch_save:
            lines.append("你昨晚使用了解药救人")

    # 守卫守护状态
    if player.role == "守卫" and game.guard_target:
        lines.append(f"你今晚守护了 {game.guard_target}号")

    # 公开事件
    if game.public_log:
        lines.append("公开事件：" + "；".join(game.public_log[-5:]))

    return "\n".join(lines)


def public_history(game) -> str:
    """从 full_record 构建此前已发生的**公开**事件摘要（跨天累计，供模型回忆）。

    只含所有玩家都能合法知道的信息：死亡/放逐/投票结果。
    严禁包含私密行动：狼刀目标、预言家查验、女巫毒/救、守卫守护 —— 这些只能经
    visible_info_for 的角色分支隔离注入。预言家查验更是绝对不能进公共历史：
    否则等于替预言家跳身份，非预言家玩家就能凭空得知"谁是预言家、他验了谁"。
    """
    if not game.full_record:
        return ""
    events = []
    for rec in game.full_record:
        d = f"第{rec['day']}天"
        t = rec["type"]
        if t == "death" and rec.get("died"):
            events.append(f"{d}天亮 {('、'.join(str(x) + '号' for x in rec['died']))} 死亡")
        elif t == "execution":
            events.append(f"{d}白天 {rec.get('executed')}号玩家被投票放逐")
        elif t == "vote_round":
            v = rec.get("votes") or []
            lines = [f"    {x['voter']}号投给了{('0号(弃权)' if not x['target'] else str(x['target']) + '号')}"
                     for x in v]
            events.append(f"{d}白天投票结果：\n" + "\n".join(lines))
        elif t == "speech_round":
            for sp in rec.get("speeches", []):
                text = sp.get("text", "").replace("\n", " ")
                events.append(f"{d}白天 {sp['player_id']}号玩家发言：{text}")
    # 截断：只保留最近 30 条事件，避免 prompt 过长
    if len(events) > 30:
        events = events[-30:]
    return "\n".join(events)


# ============================================================
# 核心 Prompt 构造函数
# ============================================================

def build_role_system_prompt(game, player) -> str:
    """构造角色的基础系统提示词（包含角色目标、话术模式、失误预防）。"""
    from ..game.roles import is_wolf
    
    # 在角色提示词开头注入玩家编号，供 mock 服务器正则匹配
    base_prompt = ROLE_SPEECH_PROMPTS.get(player.role, ROLE_SPEECH_PROMPTS["村民"])
    base_prompt = f"你是 {player.player_id} 号玩家，{base_prompt.lstrip()}"
    
    # 狼人额外警告
    if is_wolf(player.role):
        base_prompt += """
        
【最后警告】
- 你的角色是狼人，这是最高机密
- 绝对禁止在任何情况下说出自己是狼人
- 绝对禁止透露你的狼人同伴是谁
- 你必须伪装成普通村民，假装在找狼人
- 你的发言要与村民一致，不要表现得过于聪明或过于无知
"""
    
    return base_prompt


def build_speech_system_prompt(game, player, personality: str = "", prior_speeches: list[dict] | None = None) -> str:
    """构造白天发言的系统 prompt。

    改进点：
    1. 角色专属的话术模式和失误预防
    2. 清晰的信息边界
    3. 结构化发言引导
    4. 反模式预防
    """
    from ..game.roles import is_wolf

    if not personality:
        personality = "自然、有主见的玩家"

    # 基础角色提示词（目标、话术、失误预防）
    role_prompt = build_role_system_prompt(game, player)

    # 当前可见信息
    info_block = visible_info_for(game, player)

    # 公开历史
    history = public_history(game)
    history_block = f"\n【已经发生过的事（以此为准，不要编造不存在的死亡或投票）】\n{history}" if history else ""

    # 此前发言
    prior_speeches_block = ""
    if prior_speeches:
        prior_lines = []
        for s in prior_speeches:
            who = f"{s['player_id']}号玩家"
            prior_lines.append(f"{who}说：{s['text']}")
        prior_speeches_block = f"\n【在本回合之前，以下玩家已经发言，你可以回应或反驳他们】\n" + "\n".join(prior_lines)

    # 发言要求
    speech_requirement = f"""现在轮到你发言。要求：
1. 用第一人称自然地说出你的看法
2. 发言要有逻辑，给出你的推理过程
3. 不要直接说出你的真实角色（例如不要说「我是村民」「我是预言家」「我是狼人」）
4. 可以表达怀疑、推理、为自己辩解，狼人还可以撒谎
5. 发言长度控制在 100-300 字
6. 发言结束后输出「{SPEECH_END_MARK}」

【发言技巧】
- 开场可以表达自己的观察和困惑
- 中段要提出具体怀疑对象和理由
- 收尾要明确表态或呼吁投票
- 如果被点名，要直接回应问题
- 可以适当质疑他人的发言逻辑

【禁止行为】
⛔ 暴露自己的角色身份
⛔ 说出只有特定角色才知道的信息
⛔ 编造查验结果或技能信息
⛔ 情绪化发言或人身攻击"""

    return f"""{role_prompt}

【你看到的游戏信息】
{info_block}
{history_block}
{prior_speeches_block}

{speech_requirement}"""


def build_vote_prompt(game, player, speeches: list[dict], vote_position: str = "") -> str:
    """构造投票 prompt，强制输出思考过程 + 投票编号。

    改进点：
    1. 结构化分析步骤（分析发言 -> 识别可疑点 -> 综合判断）
    2. 投票逻辑引导
    3. 狼人特殊投票策略
    4. 投票位置感知（早投更自由，晚投信息更多）
    5. 强制 JSON 输出，便于解析
    6. 反模式预防
    """
    from ..game.roles import is_wolf

    camp = "狼人阵营" if is_wolf(player.role) else "好人阵营"

    # 发言记录（乱序展示，避免位置偏差）
    speech_lines = []
    for s in speeches:
        speech_lines.append(f"{s['player_id']}号玩家：{s['text']}")
    speeches_block = "\n".join(speech_lines)

    # 投票位置提示
    position_block = f"\n【你的投票顺序】你是第 {vote_position} 个投票的。\n" if vote_position else ""
    position_advice = ""
    if vote_position:
        try:
            pos_num = int(vote_position.split('/')[0])
            total_num = int(vote_position.split('/')[1])
            if pos_num <= total_num // 2:
                position_advice = "你投票较早，信息较少但决策更自由。建议基于已有发言做出初步判断。"
            else:
                position_advice = "你投票较晚，能看到前面所有人的投票。建议关注投票模式，识别可能的狼队协调。"
        except:
            pass

    # 公开历史
    history = public_history(game)
    history_block = f"\n【此前发生的事】\n{history}\n" if history else ""

    # 狼人特殊策略
    wolf_strategy = ""
    if is_wolf(player.role):
        partners = [p.player_id for p in game.players.values()
                    if is_wolf(p.role) and p.player_id != player.player_id]
        partners_str = "、".join(f"{p}号" for p in partners) if partners else "无"
        wolf_strategy = f"""
【狼人投票策略】
- 你的狼人同伴是：{partners_str}
- 绝对禁止投票给你的同伴
- 优先投票给发言可疑的神职玩家（预言家、女巫、守卫）
- 投票时要给出看似合理的理由，不要明显针对某人
- 观察其他玩家的投票模式，识别可能指向你的投票

【狼人禁止行为】
⛔ 投给狼人同伴（除非必要 deception）
⛔ 投票理由过于明显针对某人
⛔ 与同伴投票模式过于一致（避免被识别）"""

    # 好人投票策略
    good_strategy = """
【好人投票策略】
- 优先投票给发言最可疑的玩家
- 关注投票模式：谁在协调投票、谁在被保护
- 如果有预言家跳身份，优先相信有查验结果的预言家
- 平票情况下，考虑谁最可能是狼人

【好人禁止行为】
⛔ 无依据跟风投票
⛔ 因为情感原因投票（如"我喜欢他"）
⛔ 忽略明显的逻辑矛盾"""

    # 反模式预防
    anti_pattern = """
【投票时的常见错误】
⚠️ 不要因为某人"看起来像好人"就排除怀疑
⚠️ 不要因为某人攻击你就一定怀疑他（狼人也会攻击）
⚠️ 不要因为某人被多人攻击就盲目跟投（可能是狼踩狼）
⚠️ 不要忽略投票模式中的异常协调

【正确做法】
✓ 基于发言逻辑和投票模式做判断
✓ 关注谁在引导投票、谁在被保护
✓ 如果有明确证据（如预言家查验），优先相信证据
✓ 投票理由要简洁明确"""

    # 输出格式（强制 JSON）
    output_format = """
【输出格式】（必须输出合法 JSON）
{
    "思考": "<你的推理过程，200字以内，必须包含分析了哪些玩家、谁可疑及原因>",
    "投票": <玩家编号，只写一个数字>
}

示例：
{
    "思考": "3号玩家发言时回避了关键问题，5号玩家被多人攻击但理由不充分。综合来看，3号最可疑。",
    "投票": 3
}"""

    vote_requirement = f"""现在进行投票。请按以下步骤思考：

【分析步骤】
1. 逐一分析每个存活玩家的发言逻辑
2. 识别可疑点：发言矛盾、攻击性过强、回避问题、逻辑不清
3. 结合历史事件（死亡/放逐情况）
4. 观察投票模式（如果有人先投票，关注其理由）
5. 综合判断谁最可疑

{position_block}{position_advice}
{output_format}

如果解析失败，重试 1 次（最多 2 次）。"""

    return f"""我们正在玩狼人杀，你是 {player.player_id} 号玩家，你的角色是 {player.role}（{camp}阵营）。
{history_block}
以下是本轮大家的发言记录：
{speeches_block}
{wolf_strategy if is_wolf(player.role) else good_strategy}
{anti_pattern}

{vote_requirement}"""


def build_target_prompt(game, player, action: str) -> str:
    """构造夜晚行动 prompt。

    改进点：
    1. 针对不同行动类型给出决策逻辑引导
    2. 结合历史信息做决策
    3. 明确行动目标和限制
    """
    from ..game.roles import is_wolf
    
    camp = "狼人阵营" if is_wolf(player.role) else "好人阵营"
    alive = game.get_alive_except({player.player_id})
    alive_str = "、".join(f"{pid}号" for pid in alive)
    
    # 公开历史
    history = public_history(game)
    history_block = f"\n【此前发生的事】\n{history}\n" if history else ""
    
    # 行动特定的决策引导
    action_guidance = ""
    
    if action == "狼人提议":
        # 狼人杀人决策
        action_guidance = """【狼人决策逻辑】
1. 优先击杀威胁最大的神职：预言家 > 女巫 > 守卫
2. 分析哪些神职还存活，优先击杀活跃的神职
3. 避免击杀已经暴露身份的狼同伴
4. 如果无法判断，随机选择一名非狼同伴"""
    
    elif action == "预言家查验":
        # 预言家查验决策
        action_guidance = """【预言家决策逻辑】
1. 优先查验发言可疑的玩家
2. 查验还未被查验过的玩家
3. 如果怀疑某人是狼，优先查验确认
4. 也可以查验活跃发言的玩家，验证其身份"""
    
    elif action == "女巫救人":
        # 女巫救人决策
        action_guidance = f"""【女巫决策逻辑】
昨晚被狼人杀死的是：{game.dead_tonight[0] if game.dead_tonight else '无'}号玩家

决策要点：
1. 第一晚必须使用解药救人（除非有特殊理由）
2. 之后根据实际情况判断：是否救、救谁
3. 解药只能用一次，要慎重
4. 回答「救」或「不救」"""
    
    elif action == "女巫毒人":
        # 女巫毒人决策
        action_guidance = """【女巫毒人决策逻辑】
1. 只在有较高把握时才使用毒药
2. 优先毒杀发言可疑、逻辑矛盾的狼人
3. 不要随意毒杀好人
4. 毒药只能用一次，用完就没有了
5. 回答选择的玩家编号"""
    
    elif action == "守卫守护":
        # 守卫守护决策
        action_guidance = """【守卫决策逻辑】
1. 优先守护预言家、女巫等高价值神职
2. 避免连续两晚守护同一人（容易被狼识破）
3. 可以考虑守护自己认为发言好的玩家
4. 守护目标是存活且非自己的玩家
5. 回答选择的玩家编号"""
    
    elif action == "猎人开枪":
        # 猎人开枪决策
        action_guidance = """【猎人开枪决策逻辑】
你已被杀死，现在可以开枪带走一名玩家。

决策要点：
1. 根据白天的发言和投票，判断谁最可能是狼人
2. 优先带走发言可疑、逻辑矛盾的狼人
3. 不要带走有明显好人口碑的玩家
4. 回答选择的玩家编号"""
    
    # 输出格式
    output_format = """请先简述你的思考（为什么选这个人），然后在最后一行单独输出你选择的玩家编号（只写一个数字）。"""
    
    return f"""我们正在玩狼人杀，你是 {player.player_id} 号玩家，你的角色是 {player.role}（{camp}阵营）。
{history_block}
当前存活玩家：{alive_str}

现在是夜晚，你在执行「{action}」。
{action_guidance}

{output_format}"""


def build_witch_save_prompt(game, player) -> str:
    """女巫救人专用 prompt（简化版）。"""
    dead_id = game.dead_tonight[0] if game.dead_tonight else 0
    antidote = "未用" if not game.witch_used_antidote else "已用"

    prompt = f"""你是狼人杀里 {player.player_id} 号玩家，女巫。
昨晚 {dead_id}号被狼人杀死。
你的解药状态：{antidote}。

请根据以下逻辑决策：
1. 第一晚必须救人
2. 之后根据局势判断
3. 解药只能用一次

回答「救」或「不救」。"""

    return prompt


def build_daily_summary_prompt(game, player) -> str:
    """构造每日总结 prompt，让 AI 主动维护记忆。

    参考 werewolf-ai-party-game 的 BOT_DAY_SUMMARY_PROMPT 设计。
    """
    from ..game.roles import is_wolf

    camp = "狼人阵营" if is_wolf(player.role) else "好人阵营"

    # 今天发生的关键事件
    today_events = []
    for rec in game.full_record:
        if rec['day'] == game.day:
            t = rec['type']
            if t == 'death' and rec.get('died'):
                today_events.append(f"天亮：{('、'.join(str(x) + '号' for x in rec['died']))} 死亡")
            elif t == 'execution':
                today_events.append(f"{rec.get('executed')}号玩家被投票放逐")
            elif t == 'vote_round':
                v = rec.get('votes') or []
                vote_summary = "、".join(f"{x['voter']}号→{('0号(弃权)' if not x['target'] else x['target']+'号')}" for x in v)
                today_events.append(f"投票：{vote_summary}")

    events_block = "\n".join(f"- {e}" for e in today_events) if today_events else "- 今天没有发生关键事件"

    # 公开历史
    history = public_history(game)
    history_block = f"\n【完整历史】\n{history}\n" if history else ""

    prompt = f"""你是 {player.player_id} 号玩家，角色是 {player.role}（{camp}阵营）。

【任务】总结今天（第 {game.day} 天）的游戏事件，更新你的个人记忆。

【今天发生的关键事件】
{events_block}

【完整历史】
{history_block}

【请总结以下内容】
1. 今天的关键事件（死亡、投票、重要发言）
2. 你对其他玩家的信任度评估（谁可信、谁可疑）
3. 你的怀疑目标及原因
4. 明天的策略计划（投票给谁、保护谁、查验谁等）

【输出格式】
请以第一人称写一段日记（200-300字），涵盖以上内容。

示例：
今天第3天，2号玩家被投票放逐。从投票模式看，3号和5号玩家表现 suspicious，他们同时攻击2号但没有给出充分理由。我作为预言家，昨天查验了7号是好人，今天会继续查验4号。明天我建议重点关注3号和5号的发言。"""

    return prompt

