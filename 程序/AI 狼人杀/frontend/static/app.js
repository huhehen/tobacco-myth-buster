/* AI 狼人杀 — Claude 风格前端：Alpine.js + WebSocket + 暗色沉浸主题 */
function app() {
  return {
    // ===== 角色立绘映射 =====
    ROLE_IMAGES: {
      "狼人":   "/static/roles/werewolf.png",
      "预言家": "/static/roles/seer.png",
      "女巫":   "/static/roles/witch.png",
      "猎人":   "/static/roles/hunter.png",
      "村民":   "/static/roles/villager.png",
      "守卫":   "/static/roles/villager.png",
    },
    ROLE_DESCS: {
      "狼人":   "夜晚与同伴协商袭击一名玩家",
      "预言家": "每晚查验一名玩家是狼人还是好人",
      "女巫":   "拥有一瓶解药和一瓶毒药，各限一次",
      "猎人":   "被放逐或被狼杀时可开枪带走一名玩家",
      "守卫":   "每晚守护一名玩家，可抵挡狼人袭击",
      "村民":   "无特殊技能，用发言和推理找出狼人",
    },
    roleImage(role) {
      return this.ROLE_IMAGES[role] || "/static/roles/villager.png";
    },
    roleDesc(role) {
      return this.ROLE_DESCS[role] || "";
    },

    // ===== 首页状态 =====
    nickname: "",
    roomCode: "",
    playerCount: 9,
    connStatus: "未连接",
    ws: null,
    _pendingSend: null,
    audioReady: false,
    ttsEnabled: false,
    ttsStatus: "未启用",
    ttsErrorCount: 0,

    // ===== 房间状态 =====
    room: null,
    inRoom: false,
    isHost: false,
    roomMode: "open",
    myId: 0,

    // ===== 游戏状态 =====
    gameStarted: false,
    phase: "夜晚",
    game: { day: 1 },
    myRole: "",
    myCamp: "",
    paused: false,
    pausedReason: "",
    winnerText: "",
    speeches: [],
    speakingNow: 0,
    speechHistory: [],
    collapsedHistory: true,
    roleReveal: false,
    _submitting: false,
    _stickBottom: true,
    _dayNightClass: 'day', // 'day' | 'night'

    // ===== 行动状态 =====
    needAct: false,
    actType: "",
    actTitle: "",
    actAction: "",
    speechInput: "",
    currentSpeakerLabel: "",
    voteStatus: "",

    // ===== 私密信息 =====
    divineResults: [],
    wolfPartners: [],
    wolfTarget: 0,

    // ===== 内部状态 =====
    _deadIds: [],
    _rolesByPlayer: {},
    aliveSet: new Set(),
    fullRecord: [],
    showFinalRoles: false,

    cardX: 0,
    cardY: 0,

    get canCreate() {
      return this.nickname.trim().length > 0 && !this.ws;
    },
    get canJoin() {
      return this.nickname.trim().length > 0 && this.roomCode.trim().length > 0 && !this.ws;
    },

    // ---------- 昼夜模式切换 ----------
    updateDayNight() {
      const isNight = this.phase === '夜晚';
      document.body.classList.toggle('night-mode', isNight);
      this._dayNightClass = isNight ? 'night' : 'day';
    },

    // ---------- 连接 ----------
    connect() {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      this.ws = new WebSocket(`${proto}://${location.host}/ws`);
      this.ws.onopen = () => {
        this.connStatus = "已连接服务器";
        if (this._pendingSend) {
          this._pendingSend();
          this._pendingSend = null;
        }
      };
      this.ws.onclose = () => {
        this.connStatus = "连接已断开，请刷新页面重连";
        this.ws = null;
      };
      this.ws.onerror = () => {
        this.connStatus = "连接错误，请刷新页面重试";
      };
      this.ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        this.handleMsg(msg);
      };
    },

    send(data) {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify(data));
      }
    },

    // ---------- 房间操作 ----------
    createRoom() {
      this.initAudio();
      this.audioReady = true;
      this.connect();
      this._pendingSend = () => this.send({
        type: "create_room",
        nickname: this.nickname.trim(),
        player_count: parseInt(this.playerCount),
      });
    },
    setRoomMode(mode, approvedNicks) {
      this.send({ type: "set_room_mode", mode, approved_nicks: approvedNicks || [] });
    },
    togglePrivateMode(enable) {
      if (enable) {
        const nicks = prompt("请输入允许加入的昵称（逗号分隔）：").trim();
        if (nicks) {
          this.setRoomMode("private", nicks.split(",").map(n => n.trim()).filter(Boolean));
        }
      } else {
        this.setRoomMode("open", []);
      }
    },

    joinRoom() {
      this.initAudio();
      this.audioReady = true;
      this.connect();
      this._pendingSend = () => this.send({
        type: "join_room",
        nickname: this.nickname.trim(),
        room_code: this.roomCode.trim(),
      });
    },

    startGame() {
      this.send({ type: "start_game" });
    },

    playAgain() {
      this.send({ type: "play_again" });
      this.gameStarted = false;
      this.roleReveal = false;
      this.showFinalRoles = false;
      this.fullRecord = [];
      this.speeches = [];
      this.speechHistory = [];
      this.winnerText = "";
      this._deadIds = [];
      this._rolesByPlayer = {};
      this._stickBottom = true;
      this.phase = "夜晚";
      this.game.day = 1;
      this.updateDayNight();
    },

    resetGame() {
      location.reload();
    },

    // ---------- 身份卡片拖动 ----------
    cardDragStart(ev) {
      const card = ev.currentTarget;
      const startX = (ev.touches ? ev.touches[0].clientX : ev.clientX);
      const startY = (ev.touches ? ev.touches[0].clientY : ev.clientY);
      const origX = this.cardX || (window.innerWidth - 200);
      const origY = this.cardY || (window.innerHeight - 160);
      const origCardX = startX - origX;
      const origCardY = startY - origY;
      card.style.cursor = "grabbing";
      const onMove = (e) => {
        const cx = e.touches ? e.touches[0].clientX : e.clientX;
        const cy = e.touches ? e.touches[0].clientY : e.clientY;
        const nx = Math.max(0, Math.min(window.innerWidth - card.offsetWidth, cx - origCardX));
        const ny = Math.max(0, Math.min(window.innerHeight - card.offsetHeight, cy - origCardY));
        this.cardX = nx;
        this.cardY = ny;
        // 直接设置 style 避免 CSS transition 造成的拖动延迟
        card.style.left = nx + 'px';
        card.style.top = ny + 'px';
        card.style.right = 'auto';
        card.style.bottom = 'auto';
      };
      const onUp = () => {
        card.style.cursor = "grab";
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        window.removeEventListener("touchmove", onMove);
        window.removeEventListener("touchend", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
      window.addEventListener("touchmove", onMove);
      window.addEventListener("touchend", onUp);
      ev.preventDefault();
    },

    confirmRole() {
      this.roleReveal = false;
    },

    // ---------- 消息处理 ----------
    handleMsg(msg) {
      switch (msg.type) {
        case "room_joined": {
          this.room = msg.room;
          this.myId = msg.player_id;
          this.inRoom = true;
          this.isHost = msg.room.players.find(p => p.player_id === msg.player_id)?.is_host || false;
          this.roomMode = msg.room?.join_mode || "open";
          this.connStatus = `已加入房间 ${msg.room.code}`;
          this._recomputeAlive();
          if (msg.snapshot) {
            this.applySnapshot(msg.snapshot);
          }
          break;
        }
        case "room_players":
          this.room = msg.room;
          this.isHost = msg.room.players.find(p => p.player_id === this.myId)?.is_host || false;
          break;
        case "game_started":
          this.gameStarted = true;
          if (msg.players) {
            this.room = this.room || {};
            this.room.players = msg.players.map(p => ({ ...p, connected: true }));
            this.room.max_players = msg.players.length;
          }
          this.game.day = 1;
          this.phase = "夜晚";
          this.speeches = [];
          this.speechHistory = [];
          this.divineResults = [];
          this.wolfPartners = [];
          this.winnerText = "";
          this._deadIds = [];
          this._rolesByPlayer = {};
          this.speakingNow = 0;
          this.voteStatus = "";
          this._recomputeAlive();
          this._addHistory({ kind: "phase", phase: "夜晚", day: 1 });
          this.updateDayNight();
          break;
        case "your_role": {
          if (msg.player_id === this.myId) {
            this.myRole = msg.role;
            this.myCamp = msg.camp;
            this._rolesByPlayer[String(this.myId)] = msg.role;
            this.roleReveal = true;
          }
          break;
        }
        case "phase_changed":
          this.phase = msg.phase;
          if (msg.day) this.game.day = msg.day;
          this.speakingNow = 0;
          this.voteStatus = "";
          this._addHistory({ kind: "phase", phase: msg.phase, day: msg.day || this.game.day });
          this._scrollToBottom();
          this.updateDayNight();
          break;
        case "game_paused":
          this.paused = true;
          this.pausedReason = msg.reason;
          break;
        case "player_disconnected":
          if (this.gameStarted) {
            this.paused = true;
            this.pausedReason = `${msg.nickname} 已掉线，游戏暂停`;
          } else if (this.room && this.room.players) {
            const p = this.room.players.find(x => x.nickname === msg.nickname);
            if (p) p.connected = false;
          }
          break;
        case "wolf_partners":
          if (msg.player_id === this.myId) {
            this.wolfPartners = msg.partner_ids || [];
            for (const pid of this.wolfPartners) {
              this._rolesByPlayer[String(pid)] = "狼人";
            }
            const txt = this.wolfPartners.map(pid => `${pid}号玩家`).join("、");
            this._addHistory({
              kind: "private", day: this.game.day, phase: this.phase,
              text: `狼人同伴：${txt}`,
            });
          }
          break;
        case "game_resumed":
        case "player_reconnected":
          this.paused = false;
          this.pausedReason = "";
          break;
        case "narrator": {
          if (msg.private) {
            this._addHistory({ kind: "system", day: this.game.day, phase: this.phase, text: msg.text });
          } else {
            this.speeches.push({ nickname: "旁白", text: msg.text });
            this._addHistory({ kind: "system", day: this.game.day, phase: this.phase, text: msg.text });
            this._scrollToBottom();
          }
          break;
        }
        case "night_result": {
          const died = msg.died_names || [];
          this._addDead(msg.died_ids || []);
          this._recomputeAlive();
          this._scrollToBottom();
          break;
        }
        case "divine_result":
          if (msg.player_id === this.myId) {
            this.divineResults.push({ day: this.game.day, target_id: msg.target_id, camp: msg.camp });
            const text = `查验结果：${msg.target_id}号玩家是${msg.camp}`;
            this.speeches.push({ nickname: "旁白", text, private: true });
            this._addHistory({
              kind: "private", day: this.game.day, phase: this.phase,
              text: `查验 ${msg.target_id}号玩家 → ${msg.camp}`,
            });
          }
          break;
        case "guard_result":
          if (msg.player_id === this.myId) {
            const text = `你今晚守护了 ${msg.target_id}号玩家`;
            this.speeches.push({ nickname: "旁白", text, private: true });
            this._addHistory({
              kind: "private", day: this.game.day, phase: this.phase,
              text,
            });
          }
          break;
        case "witch_action":
          if (msg.player_id === this.myId) {
            const text = msg.action === "救人"
              ? "你使用了解药"
              : `你使用毒药毒杀了 ${msg.target_id}号玩家`;
            this.speeches.push({ nickname: "旁白", text, private: true });
            this._addHistory({
              kind: "private", day: this.game.day, phase: this.phase,
              text,
            });
          }
          break;
        case "hunter_shot": {
          if (msg.target_id) {
            this._addDead([msg.target_id]);
            this._recomputeAlive();
          }
          break;
        }
        case "speech_turn":
          this.speakingNow = msg.player_id;
          this.currentSpeakerLabel = `${msg.player_id}号玩家 正在发言…`;
          break;
        case "speech_delta": {
          const last = this.speeches[this.speeches.length - 1];
          const role = this._rolesByPlayer[String(msg.player_id)] || "";
          if (msg.replace) {
            if (last && last.player_id === msg.player_id) {
              last.text = msg.text || "";
              last.final = true;
            } else {
              this.speeches.push({
                player_id: msg.player_id,
                nickname: `${msg.player_id}号玩家`,
                text: msg.text || "",
                role,
                final: true,
              });
            }
            if (msg.text && msg.text.trim()) {
              this._addHistory({
                kind: "speech", day: this.game.day, phase: this.phase,
                player_id: msg.player_id,
                text: msg.text,
                role: role || last?.role,
              });
            }
            this.speakingNow = 0;
            this.currentSpeakerLabel = "";
            this._scrollToBottom();
            break;
          }
          if (last && last.player_id === msg.player_id && !last.final) {
            last.text += msg.text;
            if (msg.final) {
              last.final = true;
              if (last.text.trim()) {
                this._addHistory({
                  kind: "speech", day: this.game.day, phase: this.phase,
                  player_id: msg.player_id,
                  text: last.text,
                  role: last.role,
                });
              }
            }
          } else if (!msg.final || (msg.final && (!msg.text || msg.text.length > 0))) {
            if (msg.final && (!msg.text || msg.text.length === 0)) {
              if (last) last.final = true;
              break;
            }
            this.speeches.push({
              player_id: msg.player_id,
              nickname: `${msg.player_id}号玩家`,
              text: msg.text || "",
              role,
              final: msg.final,
            });
            if (msg.final && (msg.text || "").trim()) {
              const newLast = this.speeches[this.speeches.length - 1];
              this._addHistory({
                kind: "speech", day: this.game.day, phase: this.phase,
                player_id: msg.player_id,
                text: newLast.text,
                role: newLast.role,
              });
            }
          }
          this.speakingNow = 0;
          this.currentSpeakerLabel = "";
          this._scrollToBottom();
          break;
        }
        case "speech_end":
          this.speakingNow = 0;
          this.currentSpeakerLabel = "";
          break;
        case "vote_update": {
          this._addHistory({
            kind: "vote", day: this.game.day, phase: "投票",
            voter_id: msg.voter_id,
            voter_name: `${msg.voter_id}号玩家`,
            target_name: msg.target_id ? `${msg.target_id}号玩家` : "弃权",
          });
          const total = this.aliveSet.size;
          const done = this.speechHistory.filter(e => e.kind === "vote" && e.day === this.game.day).length;
          this.voteStatus = `投票中 ${done}/${total}`;
          this.speeches.push({
            nickname: "投票",
            text: `${msg.voter_id}号玩家 → ${msg.target_id ? msg.target_id + "号玩家" : "弃权"}`,
            private: true,
          });
          this._scrollToBottom();
          break;
        }
        case "human_action_req":
          if (msg.player_id !== this.myId) break;
          this.needAct = true;
          this.actAction = msg.action;
          this.actTitle = this.actionTitle(msg.action);
          if (msg.action === "发言") {
            this.actType = "speech";
            this.speechInput = "";
          } else if (msg.action === "女巫救人") {
            this.actType = "bool";
          } else {
            this.actType = "target";
          }
          break;
        case "action_invalid":
          if (msg.player_id === this.myId) {
            alert(msg.message || "操作无效，请重试");
          }
          break;
        case "vote_result": {
          const name = msg.eliminated_name;
          this._addHistory({
            kind: "vote_result", day: this.game.day, phase: "投票",
            eliminated_name: name || null,
          });
          if (msg.vote_breakdown) {
            this.speeches.push({
              nickname: "投票统计",
              text: msg.vote_breakdown,
              private: true,
            });
          }
          if (msg.eliminated_id) {
            this._addDead([msg.eliminated_id]);
            this._recomputeAlive();
          }
          this.needAct = false;
          this.voteStatus = "";
          this._scrollToBottom();
          break;
        }
        case "speech_audio":
          this.playAudio(msg.audio);
          this.ttsErrorCount = 0;
          if (this.ttsStatus === "未启用") {
            this.ttsStatus = "正在播报";
          }
          break;
        case "game_over":
          this.phase = "结束";
          this.winnerText = msg.winner;
          this.needAct = false;
          this.speakingNow = 0;
          this.currentSpeakerLabel = "";
          if (msg.roles) {
            this._rolesByPlayer = { ...msg.roles };
            this._rolesByPlayer[String(this.myId)] = this.myRole;
          }
          this.fullRecord = msg.full_record || [];
          this.showFinalRoles = true;
          this._addHistory({ kind: "over", day: this.game.day, winner: msg.winner });
          this.updateDayNight();
          break;
        case "room_mode_set":
          this.roomMode = msg.mode;
          break;

        case "error":
          if (msg.message?.includes("TTS") || msg.message?.includes("语音")) {
            this.ttsErrorCount++;
            if (this.ttsErrorCount >= 3) {
              this.ttsStatus = "语音服务暂时不可用";
            }
          }
          alert(msg.message);
          break;
      }
    },

    // ---------- 重连快照 ----------
    applySnapshot(snap) {
      if (!snap) return;
      this.gameStarted = true;
      this.game.day = snap.day || 1;
      this.phase = snap.phase || "夜晚";
      this.myRole = snap.role || "";
      this.myCamp = snap.role && snap.role.includes("狼人") ? "狼人阵营" : "好人阵营";
      this._deadIds = snap.dead_ids || [];
      this._rolesByPlayer = {};
      this._rolesByPlayer[String(this.myId)] = this.myRole;
      this.wolfPartners = snap.wolf_partners || [];
      for (const pid of this.wolfPartners) {
        this._rolesByPlayer[String(pid)] = "狼人";
      }
      this.divineResults = [];
      for (const [tid, camp] of Object.entries(snap.divine_results || {})) {
        this.divineResults.push({ day: snap.day, target_id: parseInt(tid), camp });
      }
      this.winnerText = snap.winner || "";
      this.speeches = [];
      this.speechHistory = [];
      this.speakingNow = 0;
      this.voteStatus = "";
      for (const s of snap.speeches || []) {
        this.speeches.push({
          player_id: s.player_id,
          nickname: `${s.player_id}号玩家`,
          text: s.text || "",
          role: "",
          final: true,
        });
      }
      this._addHistory({ kind: "phase", phase: snap.phase, day: snap.day });
      for (const line of snap.public_log || []) {
        this._addHistory({ kind: "system", day: snap.day, phase: snap.phase, text: line });
      }
      for (const s of snap.speeches || []) {
        this._addHistory({ kind: "speech", day: snap.day, phase: snap.phase, player_id: s.player_id, text: s.text });
      }
      this._recomputeAlive();
      if (snap.pending_action) {
        const msg = { player_id: this.myId, action: snap.pending_action };
        this.handleMsg({ type: "human_action_req", ...msg });
      }
      if (this.myRole && !snap.pending_action) {
        this.roleReveal = true;
      }
      this.needAct = false;
      this.updateDayNight();
    },

    // ---------- 行动 ----------
    actionTitle(action) {
      const titles = {
        "狼人提议": "狼人协商：选择今晚击杀目标",
        "预言家查验": "预言家：选择要查验的玩家",
        "女巫救人": "是否使用解药救人？",
        "女巫毒人": "女巫：选择毒药目标",
        "守卫守护": "守卫：选择今晚要守护的玩家",
        "猎人开枪": "猎人：选择开枪带走的人",
        "投票": "投票：选择你认为最可疑的玩家",
        "发言": "你的发言时间",
      };
      return titles[action] || action;
    },

    actTargets() {
      return this.sortedPlayers().filter(p =>
        p.player_id !== this.myId && this.aliveSet.has(p.player_id)
      );
    },

    submitAct(value) {
      if (this._submitting) return;
      this._submitting = true;
      const data = { target_id: value };
      if (this.actAction === "女巫救人") {
        this.send({ type: "human_action", action: this.actAction, data: { save: value } });
      } else {
        this.send({ type: "human_action", action: this.actAction, data });
      }
      this.needAct = false;
      setTimeout(() => { this._submitting = false; }, 300);
    },

    submitSpeech() {
      if (this._submitting) return;
      this._submitting = true;
      this.send({
        type: "human_action",
        action: "发言",
        data: { text: this.speechInput.trim() },
      });
      this.needAct = false;
      this.speechInput = "";
      setTimeout(() => { this._submitting = false; }, 300);
    },

    // ---------- 视图辅助 ----------
    phaseClass() {
      if (this.phase === "夜晚") return "night";
      if (this.phase === "结束") return "over";
      return "day";
    },

    speechClass(s) {
      if (s.nickname === "旁白") return s.private ? "private-note" : "system";
      if (s.role && s.role.includes("狼人")) return "wolf-camp";
      return "good-camp";
    },

    sortedPlayers() {
      if (!this.room || !this.room.players) return [];
      return [...this.room.players].sort((a, b) => a.player_id - b.player_id);
    },

    playerLabel(pid) {
      return `${pid}号玩家`;
    },

    canSeeRole(pid) {
      if (pid === this.myId) return true;
      if (this.phase === "结束" && this._rolesByPlayer[String(pid)]) return true;
      if (this.myRole === "狼人" && this.wolfPartners.includes(pid)) return true;
      return false;
    },

    deadRole(pid) {
      return this._rolesByPlayer[String(pid)] || "";
    },

    _mergeRevealedRoles(revealed) {
      for (const [pid, role] of Object.entries(revealed || {})) {
        this._rolesByPlayer[String(pid)] = role;
      }
    },

    // ---------- 历史侧栏 ----------
    _addHistory(ev) {
      this.speechHistory.push({ ...ev, ts: Date.now() });
    },

    historyGroups() {
      const map = new Map();
      for (const ev of this.speechHistory) {
        const d = ev.day || 0;
        if (!map.has(d)) map.set(d, { day: d, events: [] });
        map.get(d).events.push(ev);
      }
      const groups = [...map.values()];
      for (const g of groups) {
        let lastPhase = null;
        for (const ev of g.events) {
          if (ev.kind === "phase") {
            ev.showPhase = false;
          } else if (ev.kind === "over") {
            ev.showPhase = false;
          } else if (ev.kind === "vote" || ev.kind === "vote_result") {
            ev.showPhase = false;
          } else {
            const curPhase = ev.phase || "";
            ev.showPhase = curPhase && curPhase !== lastPhase;
            if (curPhase) lastPhase = curPhase;
          }
        }
      }
      return groups;
    },

    // ---------- 音频播放 ----------
    audioQueue: [],
    audioDecoded: [],
    audioCtx: null,
    audioScheduledUntil: 0,
    audioDecoding: 0,
    audioMaxConcurrent: 3,

    initAudio() {
      if (!this.audioCtx) {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (AC) this.audioCtx = new AC();
      }
      if (this.audioCtx && this.audioCtx.state === "suspended") {
        this.audioCtx.resume();
      }
    },

    playAudio(b64Chunk) {
      if (!this.ttsEnabled) return;
      if (this.audioQueue.length > 1000) return;
      this.audioQueue.push(b64Chunk);
      if (this.ttsStatus === "未启用") {
        this.ttsStatus = "正在播报";
      }
      this._pumpAudio();
    },

    _pumpAudio() {
      while (this.audioQueue.length > 0 && this.audioDecoding < this.audioMaxConcurrent) {
        const b64 = this.audioQueue.shift();
        this.audioDecoding++;
        this._decodeChunk(b64).finally(() => {
          this.audioDecoding--;
          this._pumpAudio();
        });
      }
      this._schedulePlayback();
    },

    async _decodeChunk(b64) {
      try {
        const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
        const buffer = await this.audioCtx.decodeAudioData(bytes.buffer);
        this.audioDecoded.push(buffer);
        this._schedulePlayback();
      } catch (e) {
        // 解码失败静默跳过
      }
    },

    _schedulePlayback() {
      const now = this.audioCtx.currentTime;
      let startAt = Math.max(now + 0.02, this.audioScheduledUntil);
      while (this.audioDecoded.length > 0) {
        const buffer = this.audioDecoded.shift();
        const source = this.audioCtx.createBufferSource();
        source.buffer = buffer;
        source.connect(this.audioCtx.destination);
        source.start(startAt);
        startAt += buffer.duration;
      }
      this.audioScheduledUntil = startAt;
    },

    // ---------- 辅助 ----------
    alivePlayers() {
      if (!this.room || !this.room.players) return [];
      return this.room.players.filter(p => this.aliveSet.has(p.player_id));
    },

    isDead(pid) {
      return this._deadIds.includes(pid);
    },

    _addDead(ids) {
      this._deadIds = this._deadIds || [];
      for (const id of ids) {
        if (!this._deadIds.includes(id)) this._deadIds.push(id);
      }
    },

    deadIds() {
      return this._deadIds || [];
    },

    _recomputeAlive() {
      if (!this.room || !this.room.players) {
        this.aliveSet = new Set();
        return;
      }
      const dead = new Set(this._deadIds || []);
      this.aliveSet = new Set(
        this.room.players.filter(p => !dead.has(p.player_id)).map(p => p.player_id)
      );
    },

    deadNames() {
      if (!this.room || !this.room.players) return [];
      return this._deadIds
        .map(pid => {
          const role = this._rolesByPlayer[String(pid)];
          return role ? `${pid}号玩家（${role}）` : `${pid}号玩家`;
        });
    },

    _scrollToBottom() {
      if (!this._stickBottom) return;
      this.$nextTick(() => {
        const el = this.$refs.speeches;
        if (el) el.scrollTop = el.scrollHeight;
      });
    },

    _onScroll() {
      const el = this.$refs.speeches;
      if (!el) return;
      this._stickBottom = (el.scrollTop + el.clientHeight) >= el.scrollHeight - 8;
    },
  };
}
