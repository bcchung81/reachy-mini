/* 교육자료 공연 모드 — 로봇 두 대(사회자·도슨트)가 소리 내 말하고, 화면은 소리 없이 그 발화를 따라간다(2026-11-12).
 *
 * 왜: 미리보기 HTML 은 큐 음성을 품고 스스로 재생한다. 실제 시연에서는 로봇이 말하므로 화면이 소리를 내면 겹치고,
 * 화면이 제 시계로 돌면 로봇과 어긋난다. 그래서 공연 모드에서는 **감독의 이벤트가 시계**다:
 *   say(대사를 보냄) → 큐 전환 · speaking_started(로봇이 말하기 시작) → 그 턴의 t0 에 앵커 · speaking_ended → 턴 끝(t1)에 맞춤.
 * 로봇은 PC 캐시 프록시에서 **HTML 빌더가 쓴 것과 같은 ElevenLabs 캐시 PCM** 을 튼다 — 턴 안의 문장·낱말 시각이 그대로 맞으므로
 * 발화마다 앵커만 다시 잡으면 된다(드리프트가 쌓이지 않는다).
 *
 * 쓰는 법(빌더가 HTML 에 인라인한다 — 외부 리소스 금지):
 *   var lf = LiveFollow.create({cues: CUES, level: '일반', onCue: function (i) {…}, onLevel: function (lv) {…}});
 *   (`level` 은 문자열 또는 함수 — 웹툰처럼 한 HTML 이 여러 수준을 담으면 지금 고른 수준을 돌려주는 함수를 준다.
 *    `onLevel(lv)` 은 감독 수준이 바뀔 때 불린다 — 그 수준을 담은 페이지는 스스로 바꾼다.)
 *   if (lf.enabled) { t = lf.time(); i = lf.cue(); lf.speaking(); lf.phase(); }
 * `?live` → ws://127.0.0.1:8778/ws/audience(감독 대시보드의 읽기 전용 관람객 소켓), `?live=ws://…` 로 바꾼다.
 * `?lat=0.3` — speaking_started 에서 실제 소리까지의 지연(로봇 프리버퍼 0.25초 + 캐시 적중 + 망, 추정 — 리허설에서 잰다).
 *
 * 규칙: 글자는 textContent 로만, 소켓으로 send 하지 않는다(읽기 전용), 끊기면 화면에 크게 알린다(조용히 어긋나지 않게).
 * 관람객 질문 흐름(ack·qa·reask)의 생성 답 글은 싣지 않는다(검수 전 글 — 2026-10-01 계획의 결정).
 */
(function (root) {
  'use strict';

  var QA_TURNS = { ack: 1, qa: 1, reask: 1 };
  var LAT_DEFAULT = 0.3;
  // speaking_ended 가 아직 안 왔는데 장면이 턴 끝(t1)에 닿으면 여기서 멈춘다 — 로봇이 조금 느릴 때 다음 턴 그림이 먼저 나오지 않게.
  var OVERRUN = 0.25;

  // ── 순수 계산(브라우저 없이 node 로 시험한다) ─────────────────────────
  function core(cues, opt) {
    opt = opt || {};
    var lat = opt.lat == null ? LAT_DEFAULT : opt.lat;
    var byId = {};
    cues.forEach(function (c, i) { byId[c.id] = i; });
    var st = { cue: -1, anchorT: 0, anchorWall: 0, stopAt: 0, speaking: null, phase: 'idle', turn: null };

    function utts(ci) { return (cues[ci] && cues[ci].utt) || []; }
    function uttIndex(ci, turn) { var u = utts(ci); for (var k = 0; k < u.length; k++) if (u[k].turn === turn) return k; return -1; }
    function timeAt(wall) { return Math.max(0, Math.min(st.stopAt, st.anchorT + (wall - st.anchorWall))); }
    function hold(t, wall) { st.anchorT = t; st.anchorWall = wall; st.stopAt = t; }
    function setCue(ci, wall) {
      if (ci === st.cue) return false;
      st.cue = ci; st.speaking = null; st.turn = null;
      hold(0, wall);                                   // 새 큐 — 첫 장면에서 기다린다(여는 말이 시작되면 앵커)
      return true;
    }

    // 이벤트 하나를 먹인다. 반환: 큐가 바뀌었으면 true(페이지가 장면을 준비한다).
    function feed(m, wall, ageS) {
      if (!m || !m.kind) return false;
      if (m.kind === 'snapshot') {
        if (st.cue < 0 && m.cue_id != null && byId[m.cue_id] != null) return setCue(byId[m.cue_id], wall);
        // 공연이 안 돌면 '대기' — 단 로봇이 말하는 중이면 이벤트가 이긴다(운영자가 공연 시작 전에 대사를 내보낼 수 있고,
        // 스냅샷은 0.5초마다 와서 방금 들어온 발화 상태를 덮어 배지가 깜빡인다 — 통합 테스트에서 실제로 그랬다).
        if (m.show_running === false && !st.speaking && st.phase !== 'idle') st.phase = 'idle';
        return false;
      }
      if (m.kind !== 'say' && m.kind !== 'speaking_started' && m.kind !== 'speaking_ended') return false;
      var ci = m.cue != null && byId[m.cue] != null ? byId[m.cue] : null;
      if (m.turn && QA_TURNS[m.turn]) {
        // 관람객 질문 흐름 — 장면은 지금 자리에 멈추고, 누가 말하는지만 표시한다(생성 답의 글은 싣지 않는다).
        var changed = ci != null ? setCue(ci, wall) : false;
        hold(timeAt(wall), wall);
        st.phase = 'qa';
        st.speaking = m.kind === 'speaking_ended' ? null : { role: m.role, turn: m.turn };
        return changed;
      }
      if (ci == null) return false;                    // 모르는 라벨(단독 모드 등) — 장면은 그대로
      var changed2 = setCue(ci, wall);
      var k = uttIndex(ci, m.turn);
      st.phase = 'script';
      if (k < 0) return changed2;                      // 이 수준 화면에 없는 턴(예: 질문이 없는 대목) — 큐만 맞춘다
      var u = utts(ci)[k], next = utts(ci)[k + 1];
      if (m.kind === 'say') {
        // 대사가 나갔다 — 아직 소리는 없다. 앞 여백에 있으면 이 턴 바로 앞까지만 흘려 둔다.
        st.stopAt = Math.max(timeAt(wall), Math.min(st.stopAt, u.t0));
        return changed2;
      }
      if (m.kind === 'speaking_started') {
        st.anchorT = u.t0 - lat + (ageS || 0);
        st.anchorWall = wall;
        st.stopAt = u.t1 + OVERRUN;
        st.speaking = { role: m.role, turn: m.turn };
        st.turn = m.turn;
        return changed2;
      }
      // speaking_ended — 로봇이 이 턴을 다 말했다. 장면이 덜 왔으면 턴 끝으로 맞추고, 다음 턴 앞 여백까지 흘린 뒤 멈춘다.
      var t = Math.max(timeAt(wall), u.t1);
      st.anchorT = t; st.anchorWall = wall;
      // 다음 턴 앵커(next.t0 - lat) 바로 앞까지만 — 그 너머로 흘려 두면 다음 시작 때 장면이 뒤로 튄다.
      st.stopAt = next ? Math.max(t, next.t0 - lat - 0.05) : (cues[ci].dur || t);
      if (st.speaking && st.speaking.turn === m.turn) st.speaking = null;
      return changed2;
    }

    return {
      feed: feed,
      timeAt: timeAt,
      cue: function () { return st.cue; },
      speaking: function () { return st.speaking; },
      phase: function () { return st.phase; },
      state: function () { return st; },
    };
  }

  // ── 브라우저: 접속·재접속·상태 배지 ───────────────────────────────────
  function badge() {
    var el = document.createElement('div');
    el.setAttribute('data-live-badge', '');
    el.style.cssText = 'position:fixed;top:10px;right:12px;z-index:99;padding:6px 12px;border-radius:999px;' +
      'font:600 13px/1.2 -apple-system,"Apple SD Gothic Neo",sans-serif;color:#fff;background:#5b6472;' +
      'box-shadow:0 2px 8px rgba(0,0,0,.25);pointer-events:none';
    document.body.appendChild(el);
    return function (text, color) { el.textContent = text; el.style.background = color; el.setAttribute('data-state', text); };
  }

  function create(opts) {
    opts = opts || {};
    var q = new URLSearchParams(location.search);
    var raw = q.get('live');
    var off = {
      enabled: false, cue: function () { return -1; }, time: function () { return 0; },
      speaking: function () { return null; }, phase: function () { return 'idle'; },
    };
    // 감독 대시보드가 준 페이지(`/stage/…`)면 기본이 공연 모드다 — 운영자는 주소 하나만 연다. `?preview` 면 미리보기(자체 재생).
    var served = /^https?:$/.test(location.protocol) && location.pathname.indexOf('/stage/') === 0;
    if ((raw === null && !served) || q.get('preview') !== null) return off;
    // 같은 오리진의 관람객 소켓이 기본 — 대시보드의 Origin 검사를 통과하는 유일한 길이다(file:// 는 Origin: null 로 거절된다).
    var same = /^https?:$/.test(location.protocol) ? (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/audience' : null;
    var url = /^wss?:\/\//.test(raw || '') ? raw : (same || 'ws://127.0.0.1:8778/ws/audience');
    var lat = parseFloat(q.get('lat'));
    var c = core(opts.cues || [], { lat: isFinite(lat) ? lat : LAT_DEFAULT });
    var show = badge(), level = null, conn = 'connecting', delay = 1;
    var wall = function () { return performance.now() / 1000; };

    function paint() {
      if (conn === 'offline') return show('공연 신호 끊김 — 다시 연결하는 중…', '#c0392b');
      if (conn === 'connecting') return show('공연 신호에 연결하는 중…', '#5b6472');
      var mine = typeof opts.level === 'function' ? opts.level() : opts.level;
      if (mine && level && level !== mine) {
        return show('수준이 다르다 — 이 화면 ' + mine + ' · 공연 ' + level, '#b7791f');
      }
      var p = c.phase();
      show(p === 'qa' ? '관람객 질문에 답하는 중' : p === 'idle' ? '공연 대기' : '공연 따라가는 중', p === 'qa' ? '#2b6cb0' : '#2f855a');
    }

    function handle(m, ageS) {
      if (!m) return;
      if (m.kind === 'snapshot' && m.level && m.level !== level) {
        level = m.level;
        if (opts.onLevel) opts.onLevel(level);          // 감독 수준이 바뀌었다 — 그 수준을 담은 페이지는 따라 바꾼다
      }
      if (c.feed(m, wall(), ageS) && opts.onCue) opts.onCue(c.cue());
      paint();
    }

    function open() {
      conn = 'connecting'; paint();
      var ws;
      try { ws = new WebSocket(url); } catch (e) { conn = 'offline'; paint(); setTimeout(open, delay * 1000); return; }
      ws.onopen = function () { delay = 1; };
      ws.onmessage = function (ev) {
        var m;
        try { m = JSON.parse(ev.data); } catch (e) { return; }
        if (m.kind === 'hello') {
          conn = 'live';
          handle(m.snapshot ? Object.assign({ kind: 'snapshot' }, m.snapshot) : null);
          handle(m.say);
          if (m.started) handle(m.started, m.started.age_s || 0);   // 공연 도중에 붙었다 — 지금 발화가 몇 초째인지
          paint();
          return;
        }
        handle(m);
      };
      ws.onclose = function () {
        conn = 'offline'; paint();
        setTimeout(open, delay * 1000);
        delay = Math.min(5, delay * 2);
      };
    }
    open();

    return {
      enabled: true,
      url: url,
      cue: function () { return c.cue(); },
      time: function () { return c.timeAt(wall()); },
      speaking: function () { return c.speaking(); },
      phase: function () { return c.phase(); },
      level: function () { return level; },
    };
  }

  var api = { create: create, core: core, QA_TURNS: QA_TURNS, LAT_DEFAULT: LAT_DEFAULT };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.LiveFollow = api;
})(typeof window !== 'undefined' ? window : this);
