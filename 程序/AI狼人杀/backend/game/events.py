"""游戏事件与 WebSocket 消息协议定义。

服务端 → 客户端消息类型：
  game_started        游戏开始，分配角色（发给各玩家的 role 是私密的）
  phase_changed       阶段切换（夜晚/白天发言/投票/结束）
  night_phase         夜晚阶段详情（谁该行动）
  divine_result       预言家查验结果（私密）
  witch_antidote_used 女巫使用解药（私密确认）
  night_result        天亮公布死亡名单
  speech_turn         轮到谁发言
  speech_delta        发言文本增量（AI 流式）
  speech_end          发言结束（推进）
  human_action_req    请求人类玩家行动
  vote_req            请求人类玩家投票
  vote_update         投票进度更新
  vote_result         投票结果（谁被放逐）
  game_over           游戏结束（胜负）
  game_paused         游戏暂停（有人掉线）
  game_resumed        游戏恢复
"""
