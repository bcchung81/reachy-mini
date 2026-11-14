  // ═════════════════════════════════════════════ 칸 그림 (빌더가 template.html 의 /*__SCENES__*/ 자리에 넣는다)
  // ART[이름](sc, pn, A) → { layers:[{f, paint(g), front?}], dyn(c, t, d, pn), labels:[…], gut:[…], from:[x,y], to:[x,y], brkAt }
  //   pn = 칸(스트립 좌표 bb·poly·t0·t1…), A = 그림 상자(말풍선 아래 — 주인공은 여기에). 층은 한 번 굽고 y − f·d 에 놓인다.
  // 글자 규칙: 이름표 글은 ① 그 수준의 검증된 카드(items[].t · visual 의 글 필드 — facts/from/to/label/low/high/formula 등) 그대로,
  //   ② sc.word('낱말') — 그 큐 대사에 실제로 나온 낱말, 둘 중 하나만. 그래서 같은 그림 함수가 초등·중고등을 모두 그린다(이름표만 그 수준 카드에서).
  // 시각 규칙: 움직이는 것은 칸의 말 시각(pn.t0·pn.t1) 또는 sc.w('낱말') 에 묶는다. 그림은 t 의 순수 함수.
  // 그림 문법: 가까운 층은 잉크 선(3px) + 평면 색, 먼 층은 선 없이 옅게 — 웹툰의 깊이 표현.
  const ART = {}, BRK = {};
  // 질문 띠(ART.ask)·마지막 칸(ART.finale)의 큐별 변형 — 번호 v 로 꽂는다(04 부터). v0~v4·finale v0~v2 는 함수 안에 그대로 있다.
  //   ASKV[v] = { paint(g, A, pn, sc), dyn(c, t, A, pn, sc) } · FINV[v] = (c, t, A, pn, sc, cx, y) => 로봇 위에 덧그림
  const ASKV = {}, FINV = {};
  const LW = 3;
  function inkS(g, w) { g.lineWidth = w || LW; g.strokeStyle = COL.ink; g.lineJoin = 'round'; g.lineCap = 'round'; g.stroke(); }
  function fs(g, fill, w) { if (fill) { g.fillStyle = fill; g.fill(); } if (w !== 0) inkS(g, w); }
  function rr(g, x, y, w, h, r) { g.beginPath(); g.roundRect(x, y, w, h, r || 0); }
  function circ(g, x, y, r) { g.beginPath(); g.arc(x, y, r, 0, TAU); }
  function poly(g, P) { path(g, P); }
  /** 칸 bbox 를 세로 그라디언트로 — 굽는 판의 여유(시차)까지 덮는다 */
  function bg(g, pn, c0, c1, y0, y1) { const b = pn.bb, gr = g.createLinearGradient(0, y0 == null ? b.y0 : y0, 0, y1 == null ? b.y1 : y1); gr.addColorStop(0, c0); gr.addColorStop(1, c1); g.fillStyle = gr; g.fillRect(b.x0 - 40, b.y0 - 1400, b.x1 - b.x0 + 80, b.y1 - b.y0 + 2800); }
  function cloud(g, x, y, s, col) { g.fillStyle = col || 'rgba(255,255,255,.9)'; for (const [dx, dy, r] of [[-34, 6, 20], [-10, -6, 26], [18, -2, 22], [38, 8, 16], [0, 10, 22]]) { circ(g, x + dx * s, y + dy * s, r * s); g.fill(); } }
  function hills(g, x0, x1, y, amp, col, seed, bottom) { const r = rand(seed); g.beginPath(); g.moveTo(x0, bottom); g.lineTo(x0, y); let x = x0; while (x < x1) { const w = 120 + 120 * r(), h = amp * (0.4 + 0.6 * r()); g.quadraticCurveTo(x + w / 2, y - h, x + w, y); x += w; } g.lineTo(x1 + 200, bottom); g.closePath(); g.fillStyle = col; g.fill(); }
  function person(g, x, y, s, shirt, o) {
    o = o || {};
    poly(g, [[x - 20 * s, y], [x + 20 * s, y], [x + 14 * s, y - 46 * s], [x - 14 * s, y - 46 * s]]); fs(g, shirt, 2.5);
    circ(g, x, y - 62 * s, 15 * s); fs(g, COL.skin, 2.5);
    g.beginPath(); g.arc(x, y - 64 * s, 15.5 * s, Math.PI * 1.05, Math.PI * 1.95); g.lineTo(x + 12 * s, y - 70 * s); g.closePath(); fs(g, o.hair || COL.hair, 0);
    if (o.coat) { g.beginPath(); g.moveTo(x, y - 46 * s); g.lineTo(x, y); inkS(g, 2); }
  }
  function robot(g, x, y, r, doc) {
    rr(g, x - r * 0.62, y + r * 0.78, r * 1.24, r * 0.78, 12); fs(g, '#F4F7F9', 3);
    circ(g, x, y, r); fs(g, doc ? COL.docbg : COL.mcbg, 4);
    g.drawImage(doc ? sc_iconFlip() : sc_icon(), x - r * 0.8, y - r * 0.8, r * 1.6, r * 1.6);
  }
  const sc_icon = () => iconImg, sc_iconFlip = () => iconFlip;
  function house(g, x, y, s, wall, roof) {
    rr(g, x - 34 * s, y - 46 * s, 68 * s, 46 * s, 2); fs(g, wall, 2.5);
    poly(g, [[x - 42 * s, y - 44 * s], [x + 42 * s, y - 44 * s], [x, y - 78 * s]]); fs(g, roof || COL.ink, 2.5);
    rr(g, x - 9 * s, y - 24 * s, 18 * s, 24 * s, 1); fs(g, COL.cream, 2);
  }
  function mast(g, x, ytop, ybot, w) { g.beginPath(); g.moveTo(x, ybot); g.lineTo(x, ytop); inkS(g, w || 5); circ(g, x, ytop - 4, 7); fs(g, COL.amber2, 2.5); }
  function lattice(g, x, base, h, w) {
    poly(g, [[x - w / 2, base], [x + w / 2, base], [x + 6, base - h], [x - 6, base - h]]); fs(g, null, 0);
    g.beginPath(); g.moveTo(x - w / 2, base); g.lineTo(x - 6, base - h); g.moveTo(x + w / 2, base); g.lineTo(x + 6, base - h);
    for (let k = 1; k < 6; k++) { const yy = base - h * k / 6, hw = lerp(w / 2, 6, k / 6), yn = base - h * (k - 1) / 6, hn = lerp(w / 2, 6, (k - 1) / 6); g.moveTo(x - hw, yy); g.lineTo(x + hw, yy); g.moveTo(x - hn, yn); g.lineTo(x + hw, yy); }
    inkS(g, 3.5); circ(g, x, base - h - 6, 9); fs(g, COL.amber2, 3);
  }
  function lens(g, x, y, r) { g.beginPath(); g.moveTo(x + r * 0.7, y + r * 0.7); g.lineTo(x + r * 1.55, y + r * 1.55); inkS(g, 12); g.strokeStyle = COL.amber; g.lineWidth = 6; g.stroke(); circ(g, x, y, r); inkS(g, 7); }
  /** 퍼지는 고리(눈에 안 보이던 전파가 보이게) — t 의 닫힌 식 */
  function rings(c, x, y, t, t0, o) {
    if (t < t0) return; o = o || {}; const n = o.n || 3, sp = o.speed || 0.55, a0 = (o.a0 == null ? -160 : o.a0) * DEG, a1 = (o.a1 == null ? -20 : o.a1) * DEG, fade = clamp((t - t0) / 0.4);
    c.strokeStyle = o.col || COL.sig; c.lineWidth = o.w || 4; c.lineCap = 'round'; if (o.dash) c.setLineDash(o.dash);
    for (let k = 0; k < n; k++) { const u = (((t - t0) * sp + k / n) % 1 + 1) % 1, r = lerp(o.r0 || 14, o.r1 || 120, u); c.globalAlpha = (o.al || 0.9) * fade * (1 - u) * smooth(u / 0.15); c.beginPath(); c.arc(x, y, r, a0, a1); c.stroke(); }
    c.setLineDash([]); c.globalAlpha = 1;
  }
  function sine(c, x0, x1, y, amp, wl, ph) { c.beginPath(); for (let x = x0; x <= x1 + 0.1; x += 4) { const yy = y + amp * Math.sin((x - x0) / wl * TAU + ph); if (x === x0) c.moveTo(x, yy); else c.lineTo(x, yy); } }
  const tagX = (x0, text) => x0 + 14 + (text.length * 20 + 40) / 2;           // 왼쪽에 붙이는 꼬리표의 가운데(글자 수로 어림)
  const itemTag = (sc, pn, A) => (pn.item == null || !sc.items[pn.item] ? [] : [{ t: sc.items[pn.item].t, x: tagX(A.x0, sc.items[pn.item].t), y: A.y0 + 26, c: 'tagt', at: pn.t0 + 0.3 }]);

  // ── 01 오프닝: 넓은 설정 칸 — 전파체험관
  ART.hall = function (sc, pn, A) {
    const cx = A.cx - 20, base = A.y1 - 46, tip = [cx + 62, base - 246], at = sc.w('전파체험관');
    return {
      layers: [
        { f: 0.16, paint(g) {                           // v 1 = 저녁(19 마무리 — 첫 큐와 같은 건물을 저녁 빛으로)
          if (pn.v === 1) { bg(g, pn, '#F2B98E', '#FCE6CC'); circ(g, A.x1 - 80, A.y0 + 74, 34); fs(g, '#FFD9A0', 0); cloud(g, A.x0 + 120, pn.bb.y0 + 70, 1.1, 'rgba(255,240,225,.8)'); cloud(g, A.x1 - 210, A.y0 + 10, 0.8, 'rgba(255,240,225,.8)'); return; }
          bg(g, pn, '#CBE6F4', '#F4F9FC'); circ(g, A.x1 - 80, A.y0 + 34, 32); fs(g, COL.amber3, 0); cloud(g, A.x0 + 120, pn.bb.y0 + 70, 1.1); cloud(g, A.x1 - 210, A.y0 + 10, 0.8); } },
        { f: 0.07, paint(g) { hills(g, pn.bb.x0 - 40, pn.bb.x1, A.y1 - 70, 80, '#A9CB9C', 11, A.y1 + 600); } },
        { f: 0, paint(g) {
          rr(g, pn.bb.x0 - 30, base, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, COL.land, 3);
          rr(g, cx - 132, base - 128, 264, 128, 0); fs(g, COL.sig, 3);
          poly(g, [[cx - 152, base - 126], [cx + 152, base - 126], [cx + 110, base - 172], [cx - 110, base - 172]]); fs(g, COL.ink, 3);
          for (const wx of [cx - 110, cx - 60, cx + 34, cx + 84]) { rr(g, wx, base - 100, 32, 38, 3); fs(g, COL.sig3, 2.5); }
          rr(g, cx - 22, base - 64, 44, 64, 3); fs(g, COL.cream, 2.5);
          mast(g, tip[0], tip[1] + 6, base - 172, 5);
        } },
        { f: -0.05, front: true, paint(g) {
          for (const [x, y, r] of [[pn.bb.x0 + 26, A.y1 - 18, 36], [pn.bb.x0 + 76, A.y1 - 10, 26], [pn.bb.x1 - 34, A.y1 - 16, 34], [pn.bb.x1 - 82, A.y1 - 8, 24]]) { circ(g, x, y, r); fs(g, COL.land2, 3); }
          person(g, A.x0 + 150, A.y1 - 8, 0.78, COL.teal2); person(g, A.x0 + 196, A.y1 - 6, 0.66, COL.amber2);
        } },
      ],
      dyn(c, t) { rings(c, tip[0], tip[1], t, at, { r1: 150, dash: [10, 9] }); },
      labels: [{ t: sc.word('전파체험관'), x: cx, y: base - 149, c: 'sign', at }],
    };
  };

  // ── 01 사회자가 도슨트에게 넘긴다
  ART.handover = function (sc, pn, A) {
    const y = A.y1 - 116, m = [A.x0 + 150, y], d = [A.x1 - 150, y], T = pn.t0 + 0.5;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#EEF6FA', '#D9EAF3'); g.strokeStyle = 'rgba(11,127,181,.12)'; g.lineWidth = 3; for (let r = 60; r < 420; r += 44) { circ(g, A.cx, A.y1 - 60, r); g.stroke(); } } },
        { f: 0, paint(g) { rr(g, pn.bb.x0 - 30, A.y1 - 38, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#CCDCE6', 3); robot(g, m[0], m[1], 62, false); robot(g, d[0], d[1], 62, true); } },
      ],
      dyn(c, t) {
        const p = outCubic((t - T) / 1.0); if (p <= 0) return;
        const P0 = [m[0] + 50, m[1] - 70], P2 = [d[0] - 50, d[1] - 70], P1 = [A.cx, A.y0 - 10], N = 40, k = Math.floor(N * p);
        c.beginPath(); for (let i = 0; i <= k; i++) { const u = i / N, x = (1 - u) * (1 - u) * P0[0] + 2 * (1 - u) * u * P1[0] + u * u * P2[0], yy = (1 - u) * (1 - u) * P0[1] + 2 * (1 - u) * u * P1[1] + u * u * P2[1]; if (i) c.lineTo(x, yy); else c.moveTo(x, yy); }
        c.setLineDash([14, 10]); c.lineDashOffset = -t * 40; c.strokeStyle = COL.teal; c.lineWidth = 6; c.lineCap = 'round'; c.stroke(); c.setLineDash([]);
        if (p >= 1) { poly(c, [[P2[0] + 6, P2[1] + 8], [P2[0] - 20, P2[1] - 6], [P2[0] - 2, P2[1] - 20]]); c.fillStyle = COL.teal; c.fill();
          const g = 0.5 + 0.5 * Math.sin((t - T) * 6); c.globalAlpha = 0.5 + 0.4 * g; circ(c, d[0], d[1], 78 + 4 * g); c.strokeStyle = COL.amber2; c.lineWidth = 6; c.stroke(); c.globalAlpha = 1; }
      },
    };
  };

  // ── 01 날마다 쓰는 전파(폰·라디오·공유기 둘레의 '안 보이는' 고리)
  ART.daily = function (sc, pn, A) {
    const top = A.y1 - 66, dev = [[A.x0 + 130, top - 100], [A.cx, top - 92], [A.x1 - 130, top - 86]];
    return {
      layers: [
        { f: 0.12, paint(g) { bg(g, pn, '#FFF6E6', '#F8E6CB'); rr(g, A.x1 - 190, pn.bb.y0 + 24, 150, 110, 6); fs(g, '#D7ECF6', 0); g.strokeStyle = 'rgba(14,36,51,.18)'; g.lineWidth = 6; g.stroke(); } },
        { f: 0.03, paint(g) { rr(g, A.x0 + 24, top, A.w - 48, 16, 4); fs(g, '#D9A86A', 3); for (const x of [A.x0 + 54, A.x1 - 70]) { rr(g, x, top + 16, 14, 200, 0); fs(g, '#C2894A', 3); } } },
        { f: 0, paint(g) {
          const [p, r, w] = dev;
          rr(g, p[0] - 27, top - 96, 54, 96, 9); fs(g, COL.ink, 3); rr(g, p[0] - 20, top - 86, 40, 66, 4); fs(g, COL.sig3, 0);
          g.beginPath(); g.moveTo(r[0] + 34, top - 74); g.lineTo(r[0] + 62, top - 136); inkS(g, 4);
          rr(g, r[0] - 62, top - 76, 124, 76, 10); fs(g, COL.amber2, 3); circ(g, r[0] - 26, top - 38, 22); fs(g, COL.cream, 3); for (const yy of [-52, -36, -20]) { rr(g, r[0] + 12, top + yy, 34, 6, 3); fs(g, COL.ink, 0); }
          for (const s of [-1, 1]) { g.beginPath(); g.moveTo(w[0] + s * 34, top - 34); g.lineTo(w[0] + s * 46, top - 92); inkS(g, 4.5); }
          rr(g, w[0] - 58, top - 36, 116, 36, 8); fs(g, COL.teal2, 3); for (const k of [0, 1, 2]) { circ(g, w[0] - 34 + k * 16, top - 18, 4); fs(g, COL.amber3, 0); }
        } },
      ],
      dyn(c, t) {
        const P = [[dev[0][0], top - 104], [dev[1][0] + 62, top - 140], [dev[2][0], top - 96]], C = [COL.sig, COL.amber, COL.teal];
        P.forEach((q, i) => rings(c, q[0], q[1], t, pn.t0 + 0.5 + i * 0.5, { col: C[i], r1: 96, dash: [8, 8], al: 0.75, a0: -170, a1: -10 }));
      },
    };
  };

  // ── 01 직접 보고 만져 보게: 안 보이던 파동이 보이고, 아이들 손이 닿는다
  ART.touch = function (sc, pn, A) {
    const y = A.y0 + A.h * 0.5, T = sc.w('직접', pn.t0 - 0.2);
    return {
      layers: [
        { f: 0.12, paint(g) { bg(g, pn, '#E6F4F7', '#C8E6EE'); } },
        { f: 0.05, paint(g) { for (const [x, w] of [[A.x0 + 40, 120], [A.x0 + 200, 150], [A.x1 - 170, 130]]) { rr(g, x, pn.bb.y0 + 30, w, 90, 6); fs(g, 'rgba(255,255,255,.55)', 0); } rr(g, pn.bb.x0 - 30, A.y1 - 34, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#B5D7E2', 0); } },
        { f: 0, front: true, paint(g) {
          for (const [x, s, sl] of [[A.x0 + 200, 1, COL.amber2], [A.x1 - 210, -1, COL.teal2]]) {
            poly(g, [[x - 26, A.y1 + 40], [x + 22, A.y1 + 40], [x + 20 + s * 14, A.y1 - 64], [x - 12 + s * 14, A.y1 - 68]]); fs(g, sl, 3);
            g.beginPath(); g.ellipse(x + 4 + s * 18, A.y1 - 86, 24, 30, s * 0.25, 0, TAU); fs(g, COL.skin, 3);
            for (let k = -1; k <= 2; k++) { rr(g, x - 10 + s * 18 + k * 11, A.y1 - 132 + Math.abs(k - 0.5) * 6, 10, 32, 5); fs(g, COL.skin, 2.5); }
          }
        } },
      ],
      dyn(c, t) {
        const on = smooth((t - T) / 0.5), ph = t * 2.2;
        c.globalAlpha = 0.5 * (1 - on); c.setLineDash([6, 10]); sine(c, A.x0 + 30, A.x1 - 30, y, 34, 160, ph); c.strokeStyle = COL.grey; c.lineWidth = 4; c.stroke(); c.setLineDash([]);
        if (on > 0) { c.globalAlpha = on; sine(c, A.x0 + 30, A.x1 - 30, y, 34, 160, ph); c.strokeStyle = COL.ink; c.lineWidth = 20; c.lineCap = 'round'; c.stroke(); c.strokeStyle = COL.sig2; c.lineWidth = 13; c.stroke(); c.strokeStyle = 'rgba(255,255,255,.6)'; c.lineWidth = 3; c.stroke(); }
        c.globalAlpha = 1;
      },
      labels: itemTag(sc, pn, A),
    };
  };

  // ── 사회자 질문: 가로 띠(말풍선은 왼쪽, 그림은 오른쪽 — 망점 바탕)
  ART.ask = function (sc, pn, A) {
    const v = pn.v || 0;
    return {
      layers: [
        { f: 0.06, paint(g) { bg(g, pn, '#E9F5F8', '#D6EDF2'); g.fillStyle = 'rgba(10,111,132,.2)'; for (let y = pn.bb.y0 - 200; y < pn.bb.y1 + 200; y += 13) for (let x = A.x0 - 20; x < pn.bb.x1 + 20; x += 13) { const r = 0.6 + 2.6 * clamp((x - A.x0 + 20) / (A.w + 40)); circ(g, x + ((y / 13) % 2) * 6.5, y, r); g.fill(); } } },
        { f: 0, paint(g) {
          if (v === 0) { const x = A.cx + 10, b = A.y1 - 22; rr(g, x - 70, b - 66, 140, 66, 0); fs(g, COL.sig2, 3); poly(g, [[x - 82, b - 64], [x + 82, b - 64], [x + 60, b - 92], [x - 60, b - 92]]); fs(g, COL.ink, 3); rr(g, x - 14, b - 40, 28, 40, 2); fs(g, COL.cream, 2.5); }
          if (v === 2) { const x = A.cx, b = A.y1 - 34; rr(g, A.x0 - 10, b, A.w + 40, 80, 0); fs(g, COL.sea, 0); poly(g, [[x - 64, b - 22], [x + 64, b - 22], [x + 46, b + 6], [x - 50, b + 6]]); fs(g, COL.ink2, 3); rr(g, x - 30, b - 48, 60, 26, 3); fs(g, COL.cream, 2.5); g.beginPath(); g.moveTo(x + 20, b - 48); g.lineTo(x + 20, b - 88); inkS(g, 4); }
          // 03 '파장은 뭐예요?' — 마루와 마루 사이를 재는 괄호(물결 하나의 길이)
          if (v === 4) { const y = A.y1 - 46, wl = 84, x0 = A.x0 + 12; sine(g, x0, A.x1 - 8, y, 16, wl, -Math.PI / 2); band2(g, COL.sig2, 5);
            const c0 = x0 + wl, c1 = c0 + wl; span(g, c0, c1, y + 34, COL.amber2); for (const x of [c0, c1]) { circ(g, x, y - 16, 6); fs(g, COL.amber2, 2.5); } }
          if (ASKV[v] && ASKV[v].paint) ASKV[v].paint(g, A, pn, sc);
        } },
      ],
      dyn(c, t) {
        if (v === 3) {                                   // 03 '주파수는 뭐예요?' — 다이얼을 돌리면 물결이 촘촘해졌다 성겨졌다
          const k = 0.5 + 0.5 * Math.sin((t - pn.t0) * 1.3), dx = A.x0 + 46, dy = A.y1 - 50;
          circ(c, dx, dy, 32); fs(c, COL.cream, 3.5);
          for (let j = 0; j <= 6; j++) { const a = (-210 + 40 * j) * DEG; c.beginPath(); c.moveTo(dx + Math.cos(a) * 38, dy + Math.sin(a) * 38); c.lineTo(dx + Math.cos(a) * 46, dy + Math.sin(a) * 46); inkS(c, 3); }
          const a = (-210 + 240 * k) * DEG; c.beginPath(); c.moveTo(dx, dy); c.lineTo(dx + Math.cos(a) * 24, dy + Math.sin(a) * 24); inkS(c, 6); circ(c, dx, dy, 6); fs(c, COL.amber2, 2.5);
          const wl = lerp(90, 26, k); sine(c, dx + 56, A.x1 - 10, dy, 14, wl, -t * 4 * 90 / wl); band2(c, COL.sig2, 4);
        }
        if (ASKV[v] && ASKV[v].dyn) ASKV[v].dyn(c, t, A, pn, sc);
        if (v !== 1) return;
        const y = A.y1 - 54; c.setLineDash([8, 9]); c.lineDashOffset = -t * 30; sine(c, A.x0 + 6, A.x1 - 6, y, 16, 90, t * 2); c.strokeStyle = COL.sig; c.lineWidth = 4; c.stroke(); c.setLineDash([]);
        lens(c, A.cx - 20, y - 8 + 4 * Math.sin(t * 2.4), 30);
      },
      labels: [{ t: sc.word('?'), x: A.cx + (v === 1 ? 50 : v >= 3 ? 66 : 4), y: A.y0 + 58, c: 'q', at: pn.t0 + 0.25, rot: 8 }],
    };
  };

  // ── 01 만든 곳: 한국방송통신전파진흥원
  ART.agency = function (sc, pn, A) {
    const cx = A.cx + 20, base = A.y1 - 38, top = base - 196, tip = [cx + 96, top - 64], name = sc.word('한국방송통신전파진흥원'), at = sc.w(name);
    return {
      layers: [
        { f: 0.14, paint(g) { bg(g, pn, '#D2E9F5', '#F3F9FC'); cloud(g, A.x0 + 90, A.y0 + 30, 0.8); } },
        { f: 0.06, paint(g) { const r = rand(77); let x = pn.bb.x0 - 20; g.fillStyle = '#C9D8E2'; while (x < pn.bb.x1 + 20) { const w = 40 + 50 * r(), h = 50 + 110 * r(); g.fillRect(x, base - h, w + 1, h + 400); x += w; } } },
        { f: 0, paint(g) {
          rr(g, pn.bb.x0 - 30, base, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#DCE6EB', 3);
          rr(g, cx - 160, top, 320, base - top, 0); fs(g, '#3F99A9', 3);
          for (let r = 0; r < 3; r++) for (let k = 0; k < 6; k++) { if (r === 0) continue; rr(g, cx - 136 + k * 46, top + 22 + r * 46, 30, 30, 2); fs(g, COL.sig3, 2); }
          rr(g, cx - 26, base - 52, 52, 52, 2); fs(g, COL.cream, 2.5);
          mast(g, tip[0], tip[1] + 6, top, 5);
          person(g, A.x0 + 70, base + 14, 0.62, COL.amber2); person(g, A.x0 + 108, base + 18, 0.56, COL.sig2);
        } },
      ],
      dyn(c, t) { rings(c, tip[0], tip[1], t, pn.t0 + 0.6, { r1: 110, dash: [9, 8] }); },
      labels: [{ t: name, x: cx, y: top + 34, c: 'sign', at }],
    };
  };

  // ── 01 도슨트 핵심(기울어진 칸): 함께 쓰는 전파 — 탑에서 나간 길들이 서로 겹치지 않게 나뉜다. 여기서 전파 띠가 칸을 깨고 나간다
  ART.share = function (sc, pn, A) {
    const tx = A.x0 + 150, base = A.y1 - 12, th = 196, tip = [tx, base - th - 6];
    const yb = (x) => pn.poly[3][1] + (pn.poly[2][1] - pn.poly[3][1]) * (x - XL) / (XR - XL);   // 기울어진 아랫변의 y
    const R = [[A.x0 + 268, yb(A.x0 + 268) - 22, 'house2'], [A.x1 - 196, A.y1 - 26, 'house'], [A.x1 - 86, yb(A.x1 - 86) - 34, 'ship']];
    const facts = (sc.visual && sc.visual.facts) || [];
    return {
      layers: [
        { f: 0.15, paint(g) { bg(g, pn, '#CFE8F5', '#F4F9FC'); } },
        { f: 0.06, paint(g) { hills(g, pn.bb.x0 - 40, pn.bb.x1, A.y1 - 30, 60, '#B3D2A6', 21, pn.bb.y1 + 900); } },
        { f: 0, paint(g) {
          g.beginPath(); g.moveTo(A.x1 - 330, pn.bb.y1 + 400); g.lineTo(A.x1 - 300, yb(A.x1 - 300) - 70); g.quadraticCurveTo(A.x1 - 160, yb(A.x1 - 160) - 96, pn.bb.x1 + 40, yb(pn.bb.x1) - 80); g.lineTo(pn.bb.x1 + 40, pn.bb.y1 + 400); g.closePath(); fs(g, COL.sea, 3);
          rr(g, pn.bb.x0 - 30, base, 420, 600, 0); fs(g, COL.land, 3);
          lattice(g, tx, base, th, 78);
          house(g, R[0][0], R[0][1], 0.8, COL.sig3, COL.amber);
          house(g, R[1][0], R[1][1], 0.9, COL.amber3, COL.teal);
          poly(g, [[R[2][0] - 56, R[2][1] - 16], [R[2][0] + 56, R[2][1] - 16], [R[2][0] + 40, R[2][1] + 10], [R[2][0] - 44, R[2][1] + 10]]); fs(g, COL.ink2, 3); rr(g, R[2][0] - 26, R[2][1] - 40, 52, 24, 3); fs(g, COL.cream, 2.5);
        } },
      ],
      dyn(c, t) {
        const C = [COL.amber2, COL.sig2, COL.teal2];
        R.forEach((r, i) => {
          const T = pn.t0 + 0.7 + i * 0.45, p = outCubic((t - T) / 0.7); if (p <= 0) return;
          const end = [r[0], r[1] - (r[2] === 'ship' ? 44 : 84)], mid = [(tip[0] + end[0]) / 2 + (i - 1) * 30, Math.min(tip[1], end[1]) - 40 - i * 18];
          c.beginPath(); const N = 30; for (let k = 0; k <= Math.floor(N * p); k++) { const u = k / N, x = (1 - u) * (1 - u) * tip[0] + 2 * (1 - u) * u * mid[0] + u * u * end[0], y = (1 - u) * (1 - u) * tip[1] + 2 * (1 - u) * u * mid[1] + u * u * end[1]; if (k) c.lineTo(x, y); else c.moveTo(x, y); }
          c.strokeStyle = COL.ink; c.lineWidth = 11; c.lineCap = 'round'; c.stroke(); c.strokeStyle = C[i]; c.lineWidth = 6; c.stroke();
          c.setLineDash([3, 14]); c.lineDashOffset = -t * 50; c.strokeStyle = '#fff'; c.lineWidth = 3; c.stroke(); c.setLineDash([]);
        });
      },
      labels: facts.slice(0, 2).map((f, i) => ({ t: f.big, sub: f.label, x: A.x1 - 158, y: A.y0 + 48 + i * 96, c: 'fact', at: pn.t0 + 0.5 + i * 1.6, rot: i ? 1.2 : -1.2 })),
      from: [tip[0] + 84, tip[1] - 14],
    };
  };

  // ── 01 침묵 칸: 함께 쓰는 마을 — 말도 움직임도 없다
  ART.town = function (sc, pn, A) {
    const b = pn.bb, base = b.y1 - 22, cx = (b.x0 + b.x1) / 2;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#A9D2E8', '#FBE8C8'); circ(g, b.x0 + 70, b.y0 + 64, 22); fs(g, '#FFF6DE', 0); } },
        { f: 0, paint(g) {
          hills(g, b.x0 - 40, b.x1, base - 18, 26, COL.land, 33, b.y1 + 400);
          [[b.x0 + 62, COL.sig3, COL.sig], [b.x0 + 140, COL.amber3, COL.teal], [b.x0 + 218, COL.teal3, COL.amber], [b.x0 + 296, '#F6D2C4', COL.ink2]].forEach(([x, w, r], i) => {
            house(g, x, base, 0.78, w, r); g.beginPath(); g.moveTo(x + 14, base - 58); g.lineTo(x + 14, base - 92); inkS(g, 3); circ(g, x + 14, base - 95, 5); fs(g, [COL.amber2, COL.sig2, COL.teal2, COL.amber2][i], 2);
          });
        } },
      ],
      to: [cx, b.y0 + 104],
    };
  };

  // ── 마지막(테두리 없는 칸): 두 로봇과 퍼지는 고리 — v1 은 '발견' 을 다시 짚는다
  ART.finale = function (sc, pn, A) {
    const v = pn.v || 0, y = A.y1 - 110, cx = SW / 2;
    const labels = [];
    if (v === 1) labels.push({ t: sc.word('발견'), x: cx, y: A.y0 + 40, c: 'tag', at: sc.w('발견', pn.t0 - 0.2) });
    return {
      layers: [
        { f: 0.12, paint(g) { bg(g, pn, '#E6F2F9', '#FFFFFF'); g.strokeStyle = 'rgba(11,127,181,.16)'; g.lineWidth = 4; g.setLineDash([12, 12]); for (let r = 120; r < 520; r += 70) { circ(g, cx, y + 20, r); g.stroke(); } g.setLineDash([]); } },
        { f: 0.04, paint(g) {
          if (v === 0) { const x = cx, b = A.y1 - 30; hills(g, -40, SW + 40, b, 26, '#C9DEC0', 7, A.y1 + 600); rr(g, x - 46, b - 64, 92, 64, 0); fs(g, '#8FC2DE', 0); poly(g, [[x - 56, b - 62], [x + 56, b - 62], [x + 38, b - 86], [x - 38, b - 86]]); fs(g, '#6F8A9C', 0); g.fillStyle = '#6F8A9C'; g.fillRect(x + 20, b - 128, 4, 44); circ(g, x + 22, b - 130, 6); fs(g, COL.amber2, 0); }
          else { rr(g, -40, A.y1 - 70, SW + 80, 600, 0); fs(g, '#BFE0EF', 0); hills(g, -40, 150, A.y1 - 70, 30, '#B6D2A9', 5, A.y1); hills(g, 500, SW + 40, A.y1 - 70, 30, '#B6D2A9', 6, A.y1); }
        } },
        { f: 0, paint(g) { rr(g, -40, A.y1 - 30, SW + 80, 600, 0); fs(g, '#DDE8EE', 3); robot(g, cx - 110, y, 54, false); robot(g, cx + 110, y, 54, true); if (v === 1) lens(g, cx, A.y0 + 104, 30); } },
      ],
      dyn(c, t) {
        rings(c, cx, y - 60, t, pn.t0 + 0.3, { a0: -170, a1: -10, r0: 30, r1: 200, col: COL.sig2, speed: 0.35, al: 0.6 });
        if (v === 2) {                                   // 03: '보이지 않는 것을 풀어 주시니' — 흐린 점선 물결이 왼쪽부터 또렷해진다
          const T = sc.w('풀어', pn.t0 - 0.2), wy = A.y0 + 54, x0 = 60, x1 = SW - 60, p = smooth((t - T) / 1.1), xe = lerp(x0, x1, p), ph = -t * 2.2;
          c.setLineDash([8, 10]); sine(c, x0, x1, wy, 18, 110, ph); c.strokeStyle = COL.grey; c.lineWidth = 4; c.globalAlpha = 0.6; c.stroke(); c.setLineDash([]); c.globalAlpha = 1;
          if (p > 0) { sine(c, x0, xe, wy, 18, 110, ph); band2(c, COL.sig2, 6); }
        }
        if (FINV[v]) FINV[v](c, t, A, pn, sc, cx, y);
      },
      labels,
    };
  };

  // ── 02 오프닝: 넓은 바다를 사이에 둔 두 해안, 하늘엔 아직 아무도 모르는 파동
  ART.world = function (sc, pn, A) {
    const hz = A.y1 - 120;
    return {
      layers: [
        { f: 0.16, paint(g) { bg(g, pn, '#C8E3F2', '#F5F9FC'); circ(g, A.x0 + 86, A.y0 + 30, 30); fs(g, COL.amber3, 0); cloud(g, A.cx + 40, pn.bb.y0 + 60, 1); cloud(g, A.x1 - 90, A.y0 + 40, 0.7); } },
        { f: 0.08, paint(g) {
          rr(g, pn.bb.x0 - 40, hz, pn.bb.x1 - pn.bb.x0 + 80, 800, 0); fs(g, COL.sea, 0);
          hills(g, pn.bb.x0 - 40, A.x0 + 120, hz + 4, 50, '#9FC293', 41, hz + 30); hills(g, A.x1 - 130, pn.bb.x1 + 40, hz + 4, 46, '#9FC293', 42, hz + 30);
          g.fillStyle = '#7E95A5'; g.fillRect(A.x0 + 40, hz - 44, 3, 44); g.fillRect(A.x1 - 70, hz - 40, 3, 40);
          g.strokeStyle = 'rgba(255,255,255,.55)'; g.lineWidth = 3; for (let k = 0; k < 9; k++) { const x = A.x0 + 60 + k * 62, yy = hz + 26 + (k % 3) * 22; g.beginPath(); g.moveTo(x, yy); g.lineTo(x + 26, yy); g.stroke(); }
        } },
        { f: 0, paint(g) {
          const x = A.cx + 40, y = hz + 52; poly(g, [[x - 50, y], [x + 50, y], [x + 36, y + 20], [x - 40, y + 20]]); fs(g, COL.ink2, 3);
          g.beginPath(); g.moveTo(x, y); g.lineTo(x, y - 74); inkS(g, 3.5); poly(g, [[x + 3, y - 70], [x + 3, y - 8], [x + 44, y - 12]]); fs(g, COL.cream, 3);
          rr(g, pn.bb.x0 - 30, A.y1 - 22, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#EBD8A8', 3);
        } },
      ],
      dyn(c, t) {
        c.setLineDash([7, 11]); c.strokeStyle = COL.sig; c.lineWidth = 3; c.globalAlpha = 0.35;
        for (let k = 0; k < 3; k++) { sine(c, pn.bb.x0, pn.bb.x1, A.y0 + 18 + k * 34, 10, 120 + k * 30, t * (1 + k * 0.3) + k); c.stroke(); }
        c.setLineDash([]); c.globalAlpha = 1;
      },
    };
  };

  // ── 02 원래 우리 주변에 있었다: 돋보기 속에서만 보이는 파동
  ART.hidden = function (sc, pn, A) {
    const base = A.y1 - 20, T = pn.t0 + 0.6;
    const lines = (c, solid) => { const C = [COL.sig2, COL.teal2, COL.amber2, COL.sig]; for (let k = 0; k < 4; k++) { sine(c, A.x0 - 10, A.x1 + 10, A.y0 + 30 + k * 40, 12, 110 + 20 * k, k * 1.3 + c.__t * 1.4); c.strokeStyle = solid ? C[k] : COL.grey; c.lineWidth = solid ? 7 : 3; if (!solid) c.setLineDash([5, 10]); c.stroke(); c.setLineDash([]); } };
    return {
      layers: [
        { f: 0.12, paint(g) { bg(g, pn, '#D6ECF6', '#F6FAFC'); } },
        { f: 0.05, paint(g) { hills(g, pn.bb.x0 - 40, pn.bb.x1, base - 40, 30, '#C7DDB9', 51, pn.bb.y1 + 600); house(g, A.x0 + 90, base - 30, 0.7, COL.amber3, COL.ink2); house(g, A.x1 - 110, base - 34, 0.8, COL.sig3, COL.teal); circ(g, A.x1 - 190, base - 70, 26); fs(g, COL.land2, 2.5); } },
        { f: 0, paint(g) { rr(g, pn.bb.x0 - 30, base, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, COL.land, 3); person(g, A.x0 + 200, base + 4, 0.8, COL.teal2); person(g, A.x0 + 250, base + 6, 0.62, COL.amber2); person(g, A.x1 - 230, base + 4, 0.78, COL.sig2, { hair: '#6B4A33' }); } },
      ],
      dyn(c, t) {
        c.__t = t; c.globalAlpha = 0.55; lines(c, false); c.globalAlpha = 1;
        const p = smooth((t - T) / Math.max(1, pn.t1 - T)); if (t < T) return;
        const lx = lerp(A.x0 + 130, A.x1 - 170, p), ly = A.y0 + 82, r = 62, k = outBack((t - T) / 0.4, 1.6);
        c.save(); circ(c, lx, ly, r * k); c.clip(); c.fillStyle = 'rgba(255,255,255,.75)'; c.fillRect(lx - r, ly - r, 2 * r, 2 * r); lines(c, true); c.restore();
        c.save(); c.translate(lx, ly); c.scale(k, k); lens(c, 0, 0, r); c.restore();
      },
    };
  };

  // ── 02 발명 vs 발견(중고등) — 왼쪽은 부품이 모여 새 물건이 되고, 오른쪽은 돋보기가 이미 있던 파동을 찾는다
  ART.versus = function (sc, pn, A) {
    const mid = A.cx, base = A.y1 - 30, T1 = sc.w('발명', pn.t0 - 0.2), T2 = sc.w('발견', pn.t0 - 0.2);
    const dev = [mid / 2 + A.x0 / 2 + 10, base - 70];
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#FFF1DC', '#FBE5C3'); g.fillStyle = '#E0F1F8'; g.fillRect(mid, pn.bb.y0 - 1400, pn.bb.x1 - mid + 40, pn.bb.y1 - pn.bb.y0 + 2800); } },
        { f: 0, paint(g) {
          rr(g, pn.bb.x0 - 30, base, mid - pn.bb.x0 + 30, 600, 0); fs(g, '#D9A86A', 3);
          hills(g, mid, pn.bb.x1 + 40, base, 50, COL.land, 61, pn.bb.y1 + 600);
          g.beginPath(); g.moveTo(mid, pn.bb.y0 - 10); for (let k = 0; k < 14; k++) g.lineTo(mid + (k % 2 ? 9 : -9), pn.bb.y0 + (pn.bb.y1 - pn.bb.y0) * (k + 1) / 14); inkS(g, 4);
        } },
      ],
      dyn(c, t) {
        // 왼쪽: 흩어진 부품 → 한 물건
        const p = smooth((t - T1) / 0.7), parts = [[-130, -90, 'g'], [110, -110, 'b'], [-90, 40, 'r'], [120, 30, 'g2']];
        for (const [dx, dy, kind] of parts) {
          const x = dev[0] + dx * (1 - p) + (kind === 'b' ? 0 : kind === 'g' ? -26 : kind === 'g2' ? 26 : 0) * p, y = dev[1] + dy * (1 - p) + (kind === 'b' ? -46 : 6) * p;
          if (kind === 'b') { circ(c, x, y, 18); fs(c, COL.amber3, 3); rr(c, x - 9, y + 14, 18, 12, 2); fs(c, COL.grey, 2.5); }
          else if (kind === 'r') { rr(c, x - 44, y - 22, 88, 44, 6); fs(c, COL.amber2, 3); }
          else { c.save(); c.translate(x, y); c.rotate(t * (1 - p) * 2); for (let k = 0; k < 8; k++) { c.rotate(TAU / 8); c.fillStyle = COL.ink2; c.fillRect(-5, -26, 10, 10); } circ(c, 0, 0, 19); fs(c, COL.grey, 3); circ(c, 0, 0, 6); fs(c, COL.ink, 0); c.restore(); }
        }
        if (p >= 1) { const s = 0.5 + 0.5 * Math.sin((t - T1) * 7); c.globalAlpha = 0.5 + 0.5 * s; c.strokeStyle = COL.amber2; c.lineWidth = 4; for (let k = 0; k < 8; k++) { const a = k * TAU / 8; c.beginPath(); c.moveTo(dev[0] + Math.cos(a) * 30, dev[1] - 46 + Math.sin(a) * 30); c.lineTo(dev[0] + Math.cos(a) * 42, dev[1] - 46 + Math.sin(a) * 42); c.stroke(); } c.globalAlpha = 1; }
        // 오른쪽: 원래 있던 파동(흐리게) — 돋보기 안에서 또렷하게
        const wy = A.y0 + 96, x0 = mid + 24, x1 = pn.bb.x1 - 20;
        c.setLineDash([5, 9]); sine(c, x0, x1, wy, 14, 90, t * 1.5); c.strokeStyle = COL.grey; c.lineWidth = 3; c.globalAlpha = 0.7; c.stroke(); c.setLineDash([]); c.globalAlpha = 1;
        if (t >= T2) { const k = outBack((t - T2) / 0.4, 1.6), lx = (x0 + x1) / 2, r = 56;
          c.save(); circ(c, lx, wy, r * k); c.clip(); c.fillStyle = 'rgba(255,255,255,.8)'; c.fillRect(lx - r, wy - r, 2 * r, 2 * r); sine(c, x0, x1, wy, 14, 90, t * 1.5); c.strokeStyle = COL.sig; c.lineWidth = 7; c.stroke(); c.restore();
          c.save(); c.translate(lx, wy); c.scale(k, k); lens(c, 0, 0, r); c.restore(); }
      },
      labels: [{ t: sc.word('발명'), x: (A.x0 + mid) / 2, y: A.y0 + 28, c: 'tag', at: T1 }, { t: sc.word('발견'), x: (mid + A.x1) / 2, y: A.y0 + 28, c: 'tagt', at: T2 }],
    };
  };

  // ── 02 계산으로 알아냄(초등 '계산' / 중고등 '맥스웰 · 예언') — 이름표는 그 수준 카드에서
  ART.calc = function (sc, pn, A) {
    const desk = A.y1 - 64, sx = A.x0 + 170, T = sc.w('있을 거', pn.t0 - 0.2), cl = [A.x1 - 150, A.y0 + 78];
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#FFF4E1', '#F4DFBE'); } },
        { f: 0.05, paint(g) { for (let k = 0; k < 3; k++) { rr(g, A.x0 + 10, pn.bb.y0 + 40 + k * 70, 140, 10, 2); fs(g, '#C99A5E', 0); for (let j = 0; j < 6; j++) { g.fillStyle = [COL.sig2, COL.amber2, COL.teal2, COL.red][(j + k) % 4]; g.fillRect(A.x0 + 18 + j * 21, pn.bb.y0 + 6 + k * 70, 15, 34); } } } },
        { f: 0, paint(g) {
          person(g, sx - 10, desk + 30, 1.7, '#F5F5F2', { coat: 1, hair: '#8A8F96' });
          rr(g, pn.bb.x0 - 30, desk, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#C68C4E', 3);
          for (const [x, rot] of [[sx + 70, -0.06], [sx + 190, 0.05]]) { g.save(); g.translate(x, desk - 4); g.rotate(rot); rr(g, -56, -10, 112, 14, 1); fs(g, '#FFFFFF', 2.5); g.restore(); }
          g.beginPath(); g.moveTo(A.x1 - 70, desk); g.lineTo(A.x1 - 70, desk - 70); g.lineTo(A.x1 - 100, desk - 96); inkS(g, 4); poly(g, [[A.x1 - 128, desk - 92], [A.x1 - 84, desk - 110], [A.x1 - 96, desk - 82]]); fs(g, COL.amber2, 3);
        } },
      ],
      dyn(c, t) {
        // 종이 위 끄적임(수식처럼 보이는 획 — 글자가 아니다)이 말하는 동안 늘어난다
        const n = Math.floor(clamp((t - pn.t0) / Math.max(1, pn.t1 - pn.t0)) * 6);
        c.strokeStyle = COL.ink; c.lineWidth = 2; for (let k = 0; k < n; k++) { const x = sx + 26 + (k % 2) * 120, y = desk - 2; c.beginPath(); for (let j = 0; j < 7; j++) c.lineTo(x + j * 8, y - 5 + (j % 2 ? -3 : 3) + (k >> 1) * 0); c.stroke(); }
        // 생각 구름: 계산이 내다본 파동(점선 → 실선)
        const s = outBack((t - pn.t0 - 0.4) / 0.4, 1.4); if (s <= 0) return;
        c.save(); c.translate(cl[0], cl[1]); c.scale(s, s);
        for (const [dx, dy, rr2] of [[-70, 0, 34], [-30, -22, 40], [20, -18, 40], [62, 2, 32], [0, 18, 40], [-46, 20, 30], [44, 22, 30]]) { circ(c, dx, dy, rr2); fs(c, '#fff', 0); }
        for (const [dx, dy] of [[-120, 60], [-138, 82]]) { circ(c, dx, dy, dx === -120 ? 10 : 6); fs(c, '#fff', 2.5); }
        const on = smooth((t - T) / 0.5); sine(c, -84, 84, 2, 14, 56, t * 2.4);
        if (on < 1) { c.setLineDash([5, 7]); c.strokeStyle = COL.grey; c.lineWidth = 3; c.globalAlpha = 1 - on; c.stroke(); c.setLineDash([]); }
        c.globalAlpha = on; c.strokeStyle = COL.sig; c.lineWidth = 6; c.stroke(); c.globalAlpha = 1;
        c.restore();
      },
      labels: itemTag(sc, pn, A),
    };
  };

  // ── 02 실험으로 보여 줌(초등 '실험' / 중고등 '헤르츠 · 증명') — 보내는 쪽 불꽃이 튀면 떨어진 고리에도 불꽃
  ART.spark = function (sc, pn, A) {
    const tbl = A.y1 - 56, gx = A.x0 + 190, gy = tbl - 120, rx = A.x1 - 200, ry = tbl - 112, T = sc.w('실험', pn.t0 - 0.2);
    const bolt = (c, x, y, s, seed, col) => { const r = rand(seed); c.beginPath(); c.moveTo(x - 14 * s, y); for (let k = 1; k < 5; k++) c.lineTo(x - 14 * s + 28 * s * k / 5, y + (r() - 0.5) * 16 * s); c.lineTo(x + 14 * s, y); c.strokeStyle = COL.ink; c.lineWidth = 7; c.stroke(); c.strokeStyle = col; c.lineWidth = 3.5; c.stroke(); };
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#E9F2F7', '#D2E2EC'); } },
        { f: 0.04, paint(g) { rr(g, A.x0 + 20, pn.bb.y0 + 70, A.w - 40, 10, 2); fs(g, '#B8C8D2', 0); for (let k = 0; k < 7; k++) { rr(g, A.x0 + 40 + k * 76, pn.bb.y0 + 36, 22, 34, 6); fs(g, ['#BFE0EE', '#F6D7A6', '#CDEBD9'][k % 3], 0); } } },
        { f: 0, paint(g) {
          rr(g, pn.bb.x0 - 30, tbl, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#9AA9B3', 3);
          rr(g, gx - 70, tbl - 50, 140, 50, 6); fs(g, COL.amber2, 3); for (let k = 0; k < 7; k++) { g.beginPath(); g.moveTo(gx - 50 + k * 16, tbl - 50); g.lineTo(gx - 50 + k * 16, tbl); inkS(g, 2); }
          for (const s of [-1, 1]) { g.beginPath(); g.moveTo(gx + s * 50, tbl - 50); g.lineTo(gx + s * 50, gy); g.lineTo(gx + s * 18, gy); inkS(g, 5); circ(g, gx + s * 14, gy, 10); fs(g, '#C9D3D9', 3); }
          g.beginPath(); g.moveTo(rx, tbl); g.lineTo(rx, ry + 52); inkS(g, 6);
          g.beginPath(); g.arc(rx, ry, 52, -Math.PI / 2 + 0.18, Math.PI * 1.5 - 0.18); g.strokeStyle = COL.ink; g.lineWidth = 12; g.stroke(); g.strokeStyle = '#C07A3A'; g.lineWidth = 6; g.stroke();
          for (const s of [-1, 1]) { circ(g, rx + s * 9, ry - 52, 6); fs(g, '#C9D3D9', 2.5); }
          person(g, A.x1 - 66, tbl + 2, 0.92, '#F5F5F2', { coat: 1, hair: '#4A3426' });
        } },
      ],
      dyn(c, t) {
        if (t < T) return;
        const st = Math.floor((t - T) * 14);
        if (st % 3 !== 2) bolt(c, gx, gy, 1, st, COL.amber3);
        rings(c, gx, gy, t, T + 0.1, { a0: -40, a1: 40, r0: 30, r1: rx - gx - 60, col: COL.sig2, speed: 0.8, n: 3, w: 4, dash: [8, 8] });
        if (t >= T + 0.6 && st % 4 !== 1) bolt(c, rx, ry - 52, 0.7, st + 99, COL.amber3);
      },
      labels: itemTag(sc, pn, A),
    };
  };

  // ── 02 신호를 실어 보냄(초등 '신호 보내기' / 중고등 '마르코니 · 실용화') — 전건을 두드리면 안테나에서 점·선이 올라간다
  const MORSE = [1, 0, 3, 0, 1, 0, 1, 0, 0, 3, 0, 1, 0, 3, 0, 0, 0];          // 켜짐 길이(1 = 점, 3 = 선) · 0 = 쉼 — 한 칸 0.12초
  ART.key = function (sc, pn, A) {
    const desk = A.y1 - 58, kx = A.x0 + 190, win = [A.x1 - 230, A.y0 + 4, 210, A.h - 74], mx = win[0] + 46, mtop = win[1] + 40, T = sc.w('신호', pn.t0 - 0.2);
    const PER = MORSE.reduce((a, m) => a + (m || 1), 0);
    const on = (t) => { if (t < T) return 0; let u = ((t - T) / 0.12) % PER; for (const m of MORSE) { const len = m || 1; if (u < len) return m ? 1 : 0; u -= len; } return 0; };
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#F6EAD3', '#EAD3AE'); rr(g, win[0], win[1], win[2], win[3], 4); fs(g, '#D2EAF6', 0); g.strokeStyle = '#8B6B45'; g.lineWidth = 8; g.stroke(); g.beginPath(); g.moveTo(win[0], win[1] + win[3] - 30); g.lineTo(win[0] + win[2], win[1] + win[3] - 30); g.lineTo(win[0] + win[2], win[1] + win[3]); g.lineTo(win[0], win[1] + win[3]); g.fillStyle = COL.land; g.fill(); g.beginPath(); g.moveTo(mx, win[1] + win[3] - 30); g.lineTo(mx, mtop); g.strokeStyle = COL.ink2; g.lineWidth = 4; g.stroke(); } },
        { f: 0, paint(g) {
          rr(g, pn.bb.x0 - 30, desk, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#B57B43', 3);
          rr(g, kx - 90, desk - 20, 180, 20, 4); fs(g, '#6E4A2B', 3);
          rr(g, kx + 120, desk - 64, 50, 64, 6); fs(g, COL.sig3, 3); rr(g, kx + 132, desk - 74, 26, 12, 2); fs(g, COL.ink2, 2);
          g.beginPath(); g.moveTo(kx + 170, desk - 40); g.bezierCurveTo(kx + 260, desk - 40, win[0] - 30, desk - 140, win[0] + 20, win[1] + win[3] - 30); inkS(g, 3);
        } },
      ],
      dyn(c, t) {
        const down = on(t);
        c.save(); c.translate(kx - 40, desk - 26); c.rotate(down ? 0.06 : -0.04); rr(c, 0, -8, 120, 12, 4); fs(c, COL.amber2, 3); circ(c, 118, -6 + (down ? 6 : 0), 15); fs(c, COL.ink, 0); c.restore();
        rr(c, kx - 50, desk - 34, 18, 14, 3); fs(c, '#4D3420', 2);
        // 두드린 점·선이 창 밖 안테나 끝에서 차례로 날아간다(창 안으로만 잘라 그린다)
        if (t < T) return;
        const now = (t - T) / 0.12, base = Math.floor(now / PER);
        c.save(); rr(c, win[0], win[1], win[2], win[3], 4); c.clip();
        for (let rep = Math.max(0, base - 1); rep <= base; rep++) { let u = rep * PER; for (const m of MORSE) { const len = m || 1; if (m) { const age = (now - u) * 0.12; if (age > 0 && age < 1.8) { const x = mx + 16 + age * 86, y = mtop - 4 - age * 14, a = 1 - smooth((age - 1.2) / 0.6); c.globalAlpha = a; rr(c, x, y - 6, m === 3 ? 30 : 12, 12, 6); fs(c, COL.amber2, 2.5); c.globalAlpha = 1; } } u += len; } }
        c.restore();
      },
      labels: itemTag(sc, pn, A),
    };
  };

  // ── 02 도슨트 핵심(기울어진 칸): 송신 해안과 큰 안테나 — 여기서 모스 신호가 칸을 깨고 여백(바다)을 건넌다
  ART.send = function (sc, pn, A) {
    const land = A.y1 - 52, mx = A.x0 + 96, tip = [mx, A.y0 + 22], hut = [A.x0 + 200, land];
    const yb = (x) => pn.poly[3][1] + (pn.poly[2][1] - pn.poly[3][1]) * (x - XL) / (XR - XL);
    const mv = sc.moves[pn.i], V = sc.visual || {}, labels = [], gut = [];
    if (V.from) labels.push({ t: V.from, x: hut[0] + 10, y: land - 118, c: 'tagt', at: pn.t0 + 0.4 });
    if (sc.has('1901년')) labels.push({ t: sc.word('1901년'), x: A.x1 - 150, y: A.y0 + 40, c: 'big', at: sc.w('1901년'), rot: -4 });
    const G = pn.gutBelow;
    if (G && V.label) gut.push({ t: V.label, x: 170, y: G.y0 + (G.y1 - G.y0) * 0.42, c: 'gut', at: mv.t0 + 0.3, rot: -2 });
    if (G && V.to) gut.push({ t: V.to, x: SIL[1] - 40, y: G.y1 - 30, c: 'tagt', at: mv.t1 - 0.25 });
    return {
      layers: [
        { f: 0.15, paint(g) { bg(g, pn, '#C6E1F0', '#F2F8FB'); cloud(g, A.cx + 60, pn.bb.y0 + 60, 0.9); } },
        { f: 0.06, paint(g) { const hz = A.y0 + A.h * 0.42; rr(g, pn.bb.x0 - 40, hz, pn.bb.x1 - pn.bb.x0 + 80, pn.bb.y1 - hz + 900, 0); fs(g, COL.sea, 0); g.strokeStyle = 'rgba(255,255,255,.6)'; g.lineWidth = 3; for (let k = 0; k < 12; k++) { const x = A.x0 + 200 + (k % 4) * 100 + (k >> 2) * 30, y = hz + 30 + (k >> 2) * 46; g.beginPath(); g.moveTo(x, y); g.lineTo(x + 30, y); g.stroke(); } } },
        { f: 0, paint(g) {
          g.beginPath(); g.moveTo(pn.bb.x0 - 30, land - 6); g.lineTo(A.x0 + 250, land - 10); g.quadraticCurveTo(A.x0 + 300, land + 10, A.x0 + 290, yb(A.x0 + 290) + 40); g.lineTo(pn.bb.x0 - 30, pn.bb.y1 + 600); g.closePath(); fs(g, COL.land, 3);
          for (const s of [-1, 1]) { g.beginPath(); g.moveTo(mx, tip[1] + 30); g.lineTo(mx + s * 54, land - 4); inkS(g, 1.8); }
          mast(g, mx, tip[1] + 6, land - 4, 6);
          rr(g, hut[0] - 46, land - 64, 92, 64, 2); fs(g, COL.cream, 3); poly(g, [[hut[0] - 56, land - 62], [hut[0] + 56, land - 62], [hut[0], land - 98]]); fs(g, COL.ink2, 3); rr(g, hut[0] - 12, land - 34, 24, 34, 1); fs(g, COL.amber3, 2.5);
          g.beginPath(); g.moveTo(mx, land - 30); g.lineTo(hut[0] - 46, land - 40); inkS(g, 2);
        } },
      ],
      dyn(c, t) { rings(c, tip[0], tip[1], t, pn.t0 + 0.5, { a0: -100, a1: 40, r1: 120, dash: [9, 8], col: COL.sig }); },
      labels, gut, from: [tip[0] + 86, tip[1] - 12],
    };
  };

  // ── 02 침묵 칸: 건너편 해안의 수신 안테나 — 신호가 닿아 멈춘다(말도 움직임도 없다)
  ART.receive = function (sc, pn, A) {
    const b = pn.bb, land = b.y1 - 46, mx = b.x1 - 86, tip = [mx, b.y0 + 104];
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#BFDFF0', '#E8F4FA', b.y0, b.y0 + 60); rr(g, b.x0 - 40, b.y0 + 56, b.x1 - b.x0 + 80, 900, 0); fs(g, COL.sea, 0); g.strokeStyle = 'rgba(255,255,255,.6)'; g.lineWidth = 3; for (let k = 0; k < 6; k++) { const x = b.x0 + 30 + (k % 3) * 90, y = b.y0 + 96 + (k >> 1) * 40; g.beginPath(); g.moveTo(x, y); g.lineTo(x + 28, y); g.stroke(); } } },
        { f: 0, paint(g) {
          g.beginPath(); g.moveTo(b.x1 + 30, land - 10); g.lineTo(b.x0 + 170, land - 6); g.quadraticCurveTo(b.x0 + 120, land + 20, b.x0 + 110, b.y1 + 300); g.lineTo(b.x1 + 30, b.y1 + 300); g.closePath(); fs(g, COL.land, 3);
          for (const s of [-1, 1]) { g.beginPath(); g.moveTo(mx, tip[1] + 30); g.lineTo(mx + s * 40, land - 4); inkS(g, 1.8); }
          mast(g, mx, tip[1] + 6, land - 4, 6);
          const hx = b.x0 + 230; rr(g, hx - 36, land - 52, 72, 52, 2); fs(g, COL.cream, 3); poly(g, [[hx - 44, land - 50], [hx + 44, land - 50], [hx, land - 80]]); fs(g, COL.ink2, 3); rr(g, hx - 10, land - 28, 20, 28, 1); fs(g, COL.amber2, 2.5);
        } },
      ],
      to: [tip[0] - 70, tip[1] - 6],
    };
  };

  // ═════════════════════════════════════════════ 03 전파 이론 — 보이지 않는 물결 · 주파수 · 파장
  // 물결은 모두 '오른쪽으로 같은 빠르기로 흐르는' 식(y = −a·sin(2π(x−x0)/λ − ωt))으로 그린다. 그래서 파장이 짧은 물결일수록
  // 한자리에서 더 자주 출렁인다 — 주파수 칸(bob·fastslow)과 파장 칸(ruler·squeeze)이 같은 물리를 보여 준다(그림이 대사를 거스르지 않게).
  const WAVE_V = 69;                                 // 화면 물결의 흐름 빠르기(px/초) — 칸 깨기 물체(BRK.packet, λ 48 · ω 9)와 같은 값
  /** 지금 경로를 잉크 테두리 + 색 심으로(물결 띠) */
  function band2(c, col, w) { c.lineCap = 'round'; c.lineJoin = 'round'; c.strokeStyle = COL.ink; c.lineWidth = w + 6; c.stroke(); c.strokeStyle = col; c.lineWidth = w; c.stroke(); }
  /** 오른쪽으로 흐르는 물결 경로: x0 에서 위상 0(오르막 시작), 파장 wl, 시각 t */
  function flow(c, x0, x1, y, amp, wl, t, xr) { const k = TAU / wl, w = k * WAVE_V, r = xr == null ? x0 : xr; c.beginPath(); for (let x = x0; x <= x1 + 0.1; x += 3) { const yy = y - amp * Math.sin(k * (x - r) - w * t); if (x === x0) c.moveTo(x, yy); else c.lineTo(x, yy); } }
  /** 길이 괄호 ├──┤ — 물결 하나의 길이를 잴 때 */
  function span(c, x0, x1, y, col) { c.beginPath(); c.moveTo(x0, y - 11); c.lineTo(x0, y + 11); c.moveTo(x1, y - 11); c.lineTo(x1, y + 11); c.moveTo(x0, y); c.lineTo(x1, y); c.lineCap = 'round'; c.strokeStyle = COL.ink; c.lineWidth = 8; c.stroke(); c.strokeStyle = col; c.lineWidth = 3.5; c.stroke(); }
  /** 물에 뜬 부표(출렁임 표지) */
  function buoy(c, x, y, s, col) {
    c.save(); c.translate(x, y); c.scale(s, s);
    c.beginPath(); c.moveTo(0, -10); c.lineTo(0, -38); inkS(c, 3); poly(c, [[1, -38], [1, -26], [17, -32]]); fs(c, col, 2.5);
    c.beginPath(); c.ellipse(0, 0, 18, 13, 0, 0, TAU); fs(c, COL.white, 0); c.beginPath(); c.ellipse(0, 0, 18, 13, 0, Math.PI, TAU); c.closePath(); fs(c, col, 0);
    c.beginPath(); c.ellipse(0, 0, 18, 13, 0, 0, TAU); inkS(c, 3); c.restore();
  }
  /** 대사에서 kw 가 [from, to] 사이에 처음 나오는 때 — 없으면 null(경고 없음). 수준마다 낱말이 다른 칸에서 시각만 고를 때 쓴다.
   *  이름표 글에는 쓰지 않는다(글은 sc.word·카드만 — 대사에 없는 낱말 경고를 건너뛰면 안 된다) */
  function sayAt(sc, kw, from, to) { for (const u of sc.cue.utt) for (const s of u.s) { const k = s.x.indexOf(kw); if (k < 0) continue; const t = s.t0 + (s.t1 - s.t0) * k / s.x.length - 0.12; if (t >= from - 0.01 && t <= to) return Math.max(0, t); } return null; }
  const firstAt = (sc, kws, from, to) => { for (const kw of kws) { const t = sayAt(sc, kw, from, to); if (t != null) return t; } return null; };

  // ── 03 오프닝(넓은 칸): 원리로 들어가 본다 — 칠판에 분필 물결이 그려져 나가고, '도대체 뭐예요?' 에 큰 물음표
  ART.lab = function (sc, pn, A) {
    const bx0 = A.x0 + 64, bx1 = A.x1 - 64, by0 = A.y0 + 18, by1 = A.y1 - 78, mid = (by0 + by1) / 2, T = pn.t0 + 0.5;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#EDF3F7', '#DCE7EE'); g.strokeStyle = 'rgba(14,36,51,.06)'; g.lineWidth = 2; for (let y = pn.bb.y0 - 400; y < pn.bb.y1 + 400; y += 36) { g.beginPath(); g.moveTo(pn.bb.x0 - 40, y); g.lineTo(pn.bb.x1 + 40, y); g.stroke(); } } },
        { f: 0, paint(g) {
          rr(g, pn.bb.x0 - 30, A.y1 - 44, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#C9D7E0', 3);
          rr(g, bx0 - 14, by0 - 14, bx1 - bx0 + 28, by1 - by0 + 28, 8); fs(g, '#9A7449', 3);
          rr(g, bx0, by0, bx1 - bx0, by1 - by0, 3); fs(g, '#1A3D55', 3);
          g.strokeStyle = 'rgba(255,255,255,.07)'; g.lineWidth = 1.5;
          for (let x = bx0 + 22; x < bx1; x += 22) { g.beginPath(); g.moveTo(x, by0 + 2); g.lineTo(x, by1 - 2); g.stroke(); }
          for (let y = by0 + 22; y < by1; y += 22) { g.beginPath(); g.moveTo(bx0 + 2, y); g.lineTo(bx1 - 2, y); g.stroke(); }
          g.strokeStyle = 'rgba(255,255,255,.3)'; g.lineWidth = 2; g.beginPath(); g.moveTo(bx0 + 18, mid); g.lineTo(bx1 - 18, mid); g.stroke();
          rr(g, bx0 - 22, by1 + 14, bx1 - bx0 + 44, 10, 3); fs(g, '#A27B4F', 2.5);
          for (const [x, col] of [[bx0 + 30, '#F4F1E6'], [bx0 + 52, '#F6D79A']]) { rr(g, x, by1 + 6, 16, 8, 3); fs(g, col, 2); }
        } },
        { f: -0.05, front: true, paint(g) { person(g, A.x0 + 120, A.y1 + 4, 1.0, COL.teal2); person(g, A.x0 + 168, A.y1 + 8, 0.82, COL.amber2, { hair: '#6B4A33' }); person(g, A.x1 - 120, A.y1 + 4, 0.94, COL.sig2); } },
      ],
      dyn(c, t) {
        // 분필 물결: 말하는 동안 왼쪽부터 그려지고, 다 그리면 흐른다. 물음표 자리(오른쪽)는 비워 둔다
        const x0 = bx0 + 26, x1 = bx1 - 132, p = smooth((t - T) / 2.4); if (p <= 0) return;
        const xe = lerp(x0, x1, p), tt = Math.max(0, t - T - 2.4);
        flow(c, x0, xe, mid, (by1 - by0) * 0.27, 128, tt);
        c.strokeStyle = '#F4F1E6'; c.lineWidth = 5; c.lineCap = 'round'; c.lineJoin = 'round'; c.stroke();
        if (p < 1) { const k = TAU / 128; circ(c, xe, mid - (by1 - by0) * 0.27 * Math.sin(k * (xe - x0)), 7); fs(c, '#F6D79A', 0); }
      },
      labels: [{ t: sc.word('원리'), x: bx1 - 58, y: by0 + 6, c: 'sign', at: sc.w('원리') },
        { t: sc.word('?'), x: bx1 - 62, y: mid + 18, c: 'q', at: sc.w('도대체', pn.t0 - 0.2), rot: 8 }],
    };
  };

  // ── 03 초등: 보이지도 만져지지도 않는 물결 — 흐린 물결이 내민 손을 그냥 지나가고, 손을 쥐어도 잡히지 않는다
  ART.ghost = function (sc, pn, A) {
    const base = A.y1 + 6, px = A.cx - 70, s = 1.6, hand = [A.cx + 70, A.y0 + A.h * 0.42];
    const Tsee = sc.w('보이지도', pn.t0 - 0.2), Tgrab = sc.w('만져지지도', pn.t0 - 0.2), eye = [px - 84, base - 62 * s - 8];
    return {
      layers: [
        { f: 0.12, paint(g) { bg(g, pn, '#EAF5F0', '#D6ECE3'); cloud(g, A.x1 - 120, pn.bb.y0 + 50, 0.9); } },
        { f: 0.05, paint(g) { hills(g, pn.bb.x0 - 40, pn.bb.x1, A.y1 - 40, 46, '#BDD9B0', 91, pn.bb.y1 + 700); for (const [x, r] of [[A.x1 - 70, 34], [A.x1 - 128, 24]]) { g.fillStyle = '#7E9F74'; g.fillRect(x - 4, A.y1 - 70, 8, 40); circ(g, x, A.y1 - 82, r); g.fillStyle = '#9CC28E'; g.fill(); } } },
        { f: 0, paint(g) {
          rr(g, pn.bb.x0 - 30, A.y1 - 18, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, COL.land, 3);
          const sh = [px + 13 * s, base - 40 * s], wr = [hand[0] - 20, hand[1] + 4];
          g.beginPath(); g.moveTo(sh[0], sh[1]); g.quadraticCurveTo((sh[0] + wr[0]) / 2, sh[1] - 10, wr[0], wr[1]); g.strokeStyle = COL.ink; g.lineWidth = 21; g.lineCap = 'round'; g.stroke(); g.strokeStyle = COL.teal2; g.lineWidth = 14; g.stroke();
          person(g, px, base, s, COL.teal2);
        } },
      ],
      dyn(c, t) {
        // 손: 펴 있다가 '만져지지도' 에서 쥔다(손가락 길이만 줄어든다 — 식)
        const k = 1 - smooth((t - Tgrab - 0.1) / 0.3), [hx, hy] = hand;
        for (let j = 0; j < 4; j++) { rr(c, hx + 6, hy - 17 + j * 9, lerp(9, 26, k), 9, 4.5); fs(c, COL.skin, 2.5); }
        rr(c, hx - 5, hy - 22 - 12 * k, 10, 14 + 12 * k, 5); fs(c, COL.skin, 2.5);
        circ(c, hx, hy, 17); fs(c, COL.skin, 2.5);
        // 물결: 손 위로 그냥 지나간다(손 뒤가 아니라 위에 흐리게 — 손이 막지 못한다)
        flow(c, A.x0 - 10, A.x1 + 10, hy, 24, 136, t);
        c.setLineDash([12, 10]); c.lineDashOffset = -t * WAVE_V; c.globalAlpha = 0.6; c.strokeStyle = COL.sig2; c.lineWidth = 7; c.lineCap = 'round'; c.stroke(); c.setLineDash([]); c.globalAlpha = 1;
        // 눈 표지(보이지 않아요): 눈 모양 + 빗금
        const e = pop(t, Tsee, 0.3, 2) * 1.3; if (e > 0) {
          c.save(); c.translate(eye[0], eye[1]); c.scale(e, e);
          c.beginPath(); c.moveTo(-26, 0); c.quadraticCurveTo(0, -24, 26, 0); c.quadraticCurveTo(0, 24, -26, 0); c.closePath(); fs(c, COL.white, 3);
          circ(c, 0, 0, 8); fs(c, COL.ink, 0);
          c.beginPath(); c.moveTo(-24, 18); c.lineTo(24, -18); c.strokeStyle = COL.ink; c.lineWidth = 9; c.lineCap = 'round'; c.stroke(); c.strokeStyle = COL.red; c.lineWidth = 4.5; c.stroke();
          c.restore();
        }
      },
    };
  };

  // ── 03 초등: 연못의 물결처럼 퍼진다 — 물결은 연못 가장자리에서 멈추고, 전파는 물이 없는 텅 빈 곳도 지나간다
  ART.pond = function (sc, pn, A) {
    const pc = [A.x0 + 156, A.y1 - 62], rx = 132, ry = 38, vx0 = A.x0 + 330, mx = vx0 - 14, tip = [mx, A.y0 + 78];
    const T0 = pn.t0 + 0.3, T1 = sc.w('텅 빈', pn.t0 - 0.2);
    const stars = (() => { const r = rand(303), out = []; for (let k = 0; k < 26; k++) out.push([vx0 + 14 + r() * (A.x1 - vx0 - 28), pn.bb.y0 + 10 + r() * (A.y1 - pn.bb.y0 - 30), 1 + 2.2 * r()]); return out; })();
    return {
      layers: [
        { f: 0.12, paint(g) { bg(g, pn, '#DCEFF7', '#F2F9FC'); } },
        { f: 0, paint(g) {
          rr(g, pn.bb.x0 - 30, A.y1 - 104, vx0 - pn.bb.x0 + 30, 700, 0); fs(g, COL.land, 3);
          g.beginPath(); g.ellipse(pc[0], pc[1], rx + 10, ry + 6, 0, 0, TAU); fs(g, '#9C8A6A', 0);
          g.beginPath(); g.ellipse(pc[0], pc[1], rx, ry, 0, 0, TAU); fs(g, COL.sea, 3);
          for (const [x, y, r] of [[pc[0] - rx - 6, pc[1] - 26, 18], [pc[0] + rx - 4, pc[1] - 30, 14]]) { circ(g, x, y, r); fs(g, COL.land2, 2.5); }
          // 텅 빈 곳: 땅도 물도 없는 밤하늘 창(별만)
          rr(g, vx0, pn.bb.y0 - 400, pn.bb.x1 - vx0 + 40, pn.bb.y1 - pn.bb.y0 + 1200, 0); fs(g, COL.night, 3);
          for (const [x, y, r] of stars) { circ(g, x, y, r); g.fillStyle = 'rgba(255,255,255,.8)'; g.fill(); }
          mast(g, mx, tip[1] + 6, A.y1 - 104, 5);
        } },
      ],
      dyn(c, t) {
        // 조약돌이 떨어지면 연못에 동심 물결 — 연못 안으로만 잘라 그린다(가장자리에서 멈춘다)
        const drop = clamp((t - T0) / 0.35);
        if (t < T0 + 0.35) { circ(c, pc[0], lerp(A.y0 + 10, pc[1], drop * drop), 7); fs(c, '#7D8B94', 2.5); }
        if (t >= T0 + 0.35) {
          c.save(); c.beginPath(); c.ellipse(pc[0], pc[1], rx - 2, ry - 2, 0, 0, TAU); c.clip();
          for (let k = 0; k < 4; k++) { const u = (((t - T0 - 0.35) * 0.45 + k / 4) % 1 + 1) % 1; c.globalAlpha = (1 - u) * smooth(u / 0.12); c.beginPath(); c.ellipse(pc[0], pc[1], 10 + u * rx, 3 + u * ry, 0, 0, TAU); c.strokeStyle = COL.white; c.lineWidth = 4; c.stroke(); }
          c.restore(); c.globalAlpha = 1;
        }
        // 전파: 안테나에서 오른쪽 텅 빈 곳으로 줄지 않고 퍼져 간다
        rings(c, tip[0], tip[1], t, T1, { a0: -55, a1: 55, r0: 20, r1: A.x1 - mx - 10, col: COL.sig3, speed: 0.5, n: 4, w: 5, dash: [10, 8], al: 1 });
      },
      labels: itemTag(sc, pn, A).concat([{ t: sc.word('텅 빈 곳'), x: (vx0 + A.x1) / 2 + 10, y: A.y1 - 28, c: 'tagt', at: T1 }]),
    };
  };

  // ── 03 중고등: 전기와 자기가 서로를 밀어 주며 퍼져 나간다 — 세로 물결(전기)과 비스듬히 누운 물결(자기)이 함께 흐른다
  ART.emwave = function (sc, pn, A) {
    const ay = A.y0 + A.h * 0.5 + 6, x0 = A.x0 + 70, x1 = A.x1 - 40, wl = 168, Te = sc.w('전기', pn.t0 - 0.2), Tb = sc.w('자기', pn.t0 - 0.2);
    const ox = 0.42, oy = 0.36;                      // 자기 물결의 깊이 방향(화면에 비스듬히 눕힌다)
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#EEF4F8', '#DAE7EF'); g.strokeStyle = 'rgba(11,127,181,.08)'; g.lineWidth = 1.5; for (let x = pn.bb.x0; x < pn.bb.x1; x += 28) { g.beginPath(); g.moveTo(x, pn.bb.y0 - 400); g.lineTo(x, pn.bb.y1 + 400); g.stroke(); } } },
        { f: 0, paint(g) {
          g.beginPath(); g.moveTo(x0 - 30, ay); g.lineTo(x1 + 10, ay); inkS(g, 3);
          poly(g, [[x1 + 22, ay], [x1 + 4, ay - 9], [x1 + 4, ay + 9]]); fs(g, COL.ink, 0);
          rr(g, x0 - 44, ay - 40, 12, 80, 4); fs(g, COL.grey, 3); circ(g, x0 - 38, ay - 46, 7); fs(g, COL.amber2, 2.5); circ(g, x0 - 38, ay + 46, 7); fs(g, COL.sig2, 2.5);
        } },
      ],
      dyn(c, t) {
        const k = TAU / wl, w = k * WAVE_V, E = 70 * smooth((t - Te) / 0.5), Bm = 64 * smooth((t - Tb) / 0.5);
        const ph = (x) => Math.sin(k * (x - x0) - w * t);
        // 화살(성분) 먼저, 곡선은 그 위에
        for (let x = x0; x <= x1; x += 14) {
          const v = ph(x);
          if (Bm > 0) { c.beginPath(); c.moveTo(x, ay); c.lineTo(x + ox * Bm * v, ay + oy * Bm * v); c.strokeStyle = 'rgba(10,111,132,.55)'; c.lineWidth = 2.5; c.stroke(); }
          if (E > 0) { c.beginPath(); c.moveTo(x, ay); c.lineTo(x, ay - E * v); c.strokeStyle = 'rgba(185,111,0,.55)'; c.lineWidth = 2.5; c.stroke(); }
        }
        if (Bm > 0) { c.beginPath(); for (let x = x0; x <= x1; x += 3) { const v = ph(x), X = x + ox * Bm * v, Y = ay + oy * Bm * v; if (x === x0) c.moveTo(X, Y); else c.lineTo(X, Y); } band2(c, COL.teal2, 5); }
        if (E > 0) { c.beginPath(); for (let x = x0; x <= x1; x += 3) { const Y = ay - E * ph(x); if (x === x0) c.moveTo(x, Y); else c.lineTo(x, Y); } band2(c, COL.amber2, 5); }
      },
      labels: itemTag(sc, pn, A).concat([
        { t: sc.word('전기'), x: A.x1 - 70, y: A.y0 + 30, c: 'tag', at: Te },
        { t: sc.word('자기'), x: A.x1 - 70, y: A.y1 - 22, c: 'tagt', at: Tb }]),
    };
  };

  // ── 03 중고등: 소리는 공기가 없으면 못 간다 / 전파는 텅 빈 우주 공간에서도 — 왼쪽 공기를 뺀 유리 종 · 오른쪽 우주
  ART.vacuum = function (sc, pn, A) {
    const mid = A.cx + 6, jar = [A.x0 + 150, A.y1 - 52], Ts = sc.w('소리', pn.t0 - 0.2), Tx = sc.w('못 가', pn.t0 - 0.2), Tu = sc.w('우주', pn.t0 - 0.2);
    const sat = [mid + 80, A.y0 + 70], earth = [A.x1 - 70, A.y1 - 30];
    const stars = (() => { const r = rand(404), out = []; for (let k = 0; k < 24; k++) out.push([mid + 10 + r() * (A.x1 - mid - 10), pn.bb.y0 + 10 + r() * (pn.bb.y1 - pn.bb.y0 - 20), 1 + 2 * r()]); return out; })();
    return {
      layers: [
        { f: 0.1, paint(g) {
          bg(g, pn, '#F4EFE6', '#E8DDCB');
          g.fillStyle = COL.night; g.fillRect(mid, pn.bb.y0 - 1400, pn.bb.x1 - mid + 40, pn.bb.y1 - pn.bb.y0 + 2800);
          for (const [x, y, r] of stars) { circ(g, x, y, r); g.fillStyle = 'rgba(255,255,255,.8)'; g.fill(); }
        } },
        { f: 0, paint(g) {
          rr(g, pn.bb.x0 - 30, A.y1 - 22, mid - pn.bb.x0 + 30, 600, 0); fs(g, '#C49A66', 3);
          rr(g, jar[0] - 92, jar[1] + 4, 184, 26, 4); fs(g, '#6F7F8B', 3);
          g.beginPath(); g.moveTo(jar[0] + 92, jar[1] + 16); g.lineTo(jar[0] + 128, jar[1] + 16); g.lineTo(jar[0] + 128, A.y1 - 22); inkS(g, 5);
          // 지구와 위성
          circ(g, earth[0], earth[1], 74); fs(g, '#4F9EC4', 3);
          for (const [dx, dy, r] of [[-30, -30, 22], [10, -46, 14], [-44, 10, 16]]) { circ(g, earth[0] + dx, earth[1] + dy, r); fs(g, '#8DB27F', 0); }
          circ(g, earth[0], earth[1], 74); inkS(g, 3);
          rr(g, sat[0] - 14, sat[1] - 12, 28, 24, 3); fs(g, COL.grey2, 3);
          for (const s of [-1, 1]) { rr(g, sat[0] + s * 18 - (s < 0 ? 40 : 0), sat[1] - 8, 40, 16, 2); fs(g, COL.sig, 2.5); }
          g.beginPath(); g.moveTo(sat[0], sat[1] + 12); g.lineTo(sat[0] + 8, sat[1] + 24); inkS(g, 3);
          g.beginPath(); g.moveTo(mid, pn.bb.y0 - 10); for (let k = 0; k < 14; k++) g.lineTo(mid + (k % 2 ? 8 : -8), pn.bb.y0 + (pn.bb.y1 - pn.bb.y0) * (k + 1) / 14); inkS(g, 4);
        } },
      ],
      dyn(c, t) {
        // 종: '소리' 에서 흔들리고, 소리 고리는 유리 안에서 곧 사라진다(공기가 없다) — '못 가' 에 빨간 X
        const sw = t < Ts ? 0 : Math.sin((t - Ts) * 16) * 0.35 * Math.exp(-Math.max(0, t - Ts - 2.4) * 2), bx = jar[0], by = jar[1] - 70;
        g_bell(c, bx, by, sw);
        rings(c, bx, by - 6, t, Ts, { a0: -180, a1: 0, r0: 30, r1: 62, col: COL.grey, speed: 1.1, n: 3, w: 4, al: 0.75 });
        c.beginPath(); c.moveTo(jar[0] - 80, jar[1] + 4); c.lineTo(jar[0] - 80, jar[1] - 80); c.bezierCurveTo(jar[0] - 80, jar[1] - 156, jar[0] + 80, jar[1] - 156, jar[0] + 80, jar[1] - 80); c.lineTo(jar[0] + 80, jar[1] + 4);
        c.fillStyle = 'rgba(214,236,246,.35)'; c.fill(); inkS(c, 3);
        c.beginPath(); c.moveTo(jar[0] - 58, jar[1] - 92); c.quadraticCurveTo(jar[0] - 50, jar[1] - 126, jar[0] - 22, jar[1] - 136); c.strokeStyle = 'rgba(255,255,255,.85)'; c.lineWidth = 5; c.stroke();
        const x = pop(t, Tx, 0.3, 2); if (x > 0) { c.save(); c.translate(jar[0] + 96, jar[1] - 120); c.scale(x, x); c.beginPath(); c.moveTo(-14, -14); c.lineTo(14, 14); c.moveTo(14, -14); c.lineTo(-14, 14); c.strokeStyle = COL.ink; c.lineWidth = 11; c.lineCap = 'round'; c.stroke(); c.strokeStyle = COL.red; c.lineWidth = 6; c.stroke(); c.restore(); }
        // 우주: 위성에서 지구로 전파가 줄지 않고 간다
        rings(c, sat[0] + 8, sat[1] + 24, t, Tu, { a0: 20, a1: 80, r0: 18, r1: 150, col: COL.sig3, speed: 0.6, n: 4, w: 5, dash: [10, 8], al: 1 });
      },
      labels: [{ t: sc.word('소리'), x: jar[0] - 106, y: A.y0 + 30, c: 'tag', at: Ts }, { t: sc.word('우주'), x: A.x1 - 60, y: A.y0 + 30, c: 'tagt', at: Tu }],
    };
  };
  function g_bell(c, x, y, a) {
    c.save(); c.translate(x, y - 22); c.rotate(a);
    c.beginPath(); c.moveTo(0, 0); c.lineTo(0, 8); inkS(c, 4);
    c.beginPath(); c.moveTo(-26, 52); c.quadraticCurveTo(-26, 8, 0, 8); c.quadraticCurveTo(26, 8, 26, 52); c.lineTo(32, 60); c.lineTo(-32, 60); c.closePath(); fs(c, COL.amber2, 3);
    circ(c, 0, 64, 7); fs(c, COL.ink2, 2.5); c.restore();
    c.beginPath(); c.moveTo(x, y - 22); c.lineTo(x, y - 46); inkS(c, 4); rr(c, x - 40, y - 52, 80, 8, 3); fs(c, COL.ink2, 2.5);
  }

  // ── 03 주파수(초등 '주파수' / 중고등 '주파수 (Hz)'): 물에 뜬 부표가 얼마나 자주 출렁이나 — 초시계 한 바퀴 동안 마루를 센다
  ART.bob = function (sc, pn, A) {
    const sea = A.y1 - 78, wl = 120, V = 150, bx = A.x0 + 214, sw = [A.x1 - 96, A.y0 + 86], T = pn.t0 + 0.45, per = wl / V, REV = 3 * per;
    // 바다는 이 칸만의 빠르기(V)로 흐른다 — 마루가 0.8초마다 부표를 지나 초시계 한 바퀴(2.4초)에 정확히 세 번. 세는 눈금은 이 식에서 나온다
    const has1 = sc.has('1초');
    return {
      layers: [
        { f: 0.12, paint(g) { bg(g, pn, '#E1F0F8', '#F4F9FC'); cloud(g, A.x0 + 120, pn.bb.y0 + 40, 0.8); } },
        { f: 0, paint(g) {
          circ(g, sw[0], sw[1], 52); fs(g, COL.white, 4);
          rr(g, sw[0] - 9, sw[1] - 70, 18, 14, 3); fs(g, COL.ink2, 2.5); rr(g, sw[0] - 4, sw[1] - 58, 8, 6, 1); fs(g, COL.ink2, 0);
          for (let j = 0; j < 12; j++) { const a = j * TAU / 12; g.beginPath(); g.moveTo(sw[0] + Math.cos(a) * 40, sw[1] + Math.sin(a) * 40); g.lineTo(sw[0] + Math.cos(a) * 47, sw[1] + Math.sin(a) * 47); inkS(g, j % 3 ? 2 : 3.5); }
        } },
      ],
      dyn(c, t) {
        // 바다(물결 식 그대로 흐른다)와 부표 — 부표는 제자리에서 위아래로만
        const k = TAU / wl, amp = 26, yAt = (x) => sea - amp * Math.sin(k * (x - bx) - k * V * (t - T) + Math.PI / 2);
        c.beginPath(); c.moveTo(pn.bb.x0 - 10, pn.bb.y1 + 400); for (let x = pn.bb.x0 - 10; x <= pn.bb.x1 + 10; x += 4) c.lineTo(x, yAt(x)); c.lineTo(pn.bb.x1 + 10, pn.bb.y1 + 400); c.closePath(); fs(c, COL.sea, 3);
        buoy(c, bx, yAt(bx) - 4, 1.3, COL.red);
        // 초시계: T 부터 한 바퀴 돌고 멈춘다. 부표가 마루에 오를 때마다 눈금 하나(첫 마루 = T)
        const u = clamp((t - T) / REV), a = -Math.PI / 2 + u * TAU;
        if (t >= T) { c.beginPath(); c.moveTo(sw[0], sw[1]); c.arc(sw[0], sw[1], 36, -Math.PI / 2, a); c.closePath(); c.fillStyle = 'rgba(89,174,214,.35)'; c.fill(); }
        c.beginPath(); c.moveTo(sw[0], sw[1]); c.lineTo(sw[0] + Math.cos(a) * 38, sw[1] + Math.sin(a) * 38); inkS(c, 4); circ(c, sw[0], sw[1], 5); fs(c, COL.red, 2);
        const cnt = t < T ? 0 : Math.floor((Math.min(t, T + REV - 0.01) - T) / per) + 1;   // [T, T+REV) 안의 마루 수 — 한 바퀴 뒤엔 그대로
        for (let j = 0; j < cnt; j++) { rr(c, sw[0] - 150 + j * 22, A.y0 + (has1 ? 92 : 60), 9, 34, 4); fs(c, COL.amber2, 2.5); }
        if (u >= 1) { const f = 0.5 + 0.5 * Math.sin((t - T - REV) * 6); c.globalAlpha = 0.4 + 0.5 * f; circ(c, sw[0], sw[1], 60 + 3 * f); c.strokeStyle = COL.amber2; c.lineWidth = 5; c.stroke(); c.globalAlpha = 1; }
      },
      labels: itemTag(sc, pn, A).concat(has1 ? [{ t: sc.word('1초'), x: sw[0] - 118, y: A.y0 + 46, c: 'tag', at: sc.w('1초', pn.t0 - 0.2) }] : []),
    };
  };

  // ── 03 초등: 아주 빠르게 · 천천히 출렁이는 전파 — 두 줄 물결, 같은 빠르기로 흐르니 빠르게 출렁이는 쪽 물결이 촘촘하다
  ART.fastslow = function (sc, pn, A) {
    const y1 = A.y0 + 64, y2 = A.y0 + 168, xs = A.x0 + 138, xe = A.x1 - 24, Tf = sc.w('빠르게', pn.t0 - 0.2), Ts = sc.w('천천히', pn.t0 - 0.2);
    const lanes = [[y1, 46, 18, Tf, COL.amber2], [y2, 190, 28, Ts, COL.teal2]];
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#F2F7FA', '#E2EEF4'); } },
        { f: 0, paint(g) { for (const [y] of lanes) { rr(g, xs - 10, y - 46, xe - xs + 20, 92, 10); fs(g, 'rgba(255,255,255,.7)', 2); } } },
      ],
      dyn(c, t) {
        for (const [y, wl, amp, T, col] of lanes) {
          const on = smooth((t - T) / 0.4);
          flow(c, xs, xe, y, amp, wl, t);
          if (on < 1) { c.setLineDash([6, 9]); c.strokeStyle = COL.grey; c.lineWidth = 3; c.globalAlpha = 1 - on; c.stroke(); c.setLineDash([]); c.globalAlpha = 1; }
          if (on > 0) { c.globalAlpha = on; band2(c, col, 5); c.globalAlpha = 1; }
          // 줄 끝의 구슬: 제자리에서 위아래로 — 빠른 줄이 더 자주 오르내린다
          const k = TAU / wl, bx = xe - 40, by = y - amp * Math.sin(k * (bx - xs) - k * WAVE_V * t);
          if (on > 0) { c.globalAlpha = on; circ(c, bx, by, 10); fs(c, COL.white, 3.5); circ(c, bx, by, 4); fs(c, col, 0); c.globalAlpha = 1; }
        }
      },
      labels: [{ t: sc.word('빠르게'), x: A.x0 + 72, y: y1, c: 'tag', at: Tf }, { t: sc.word('천천히'), x: A.x0 + 72, y: y2, c: 'tagt', at: Ts }],
    };
  };

  // ── 03 중고등: 단위 이름은 전파를 처음 증명한 헤르츠에서 — 왼쪽 초상과 이름판, 오른쪽 02 의 불꽃 실험(증명)
  ART.hertz = function (sc, pn, A) {
    const fx = A.x0 + 40, fy = A.y0 + 12, fw = 150, fh = 170, tbl = A.y1 - 40, gx = A.cx + 40, gy = tbl - 96, rx = A.x1 - 96, ry = tbl - 92;
    const Tn = sc.w('헤르츠', pn.t0 - 0.2), Tp = sc.w('증명', pn.t0 - 0.2);
    const bolt = (c, x, y, s, seed) => { const r = rand(seed); c.beginPath(); c.moveTo(x - 12 * s, y); for (let k = 1; k < 5; k++) c.lineTo(x - 12 * s + 24 * s * k / 5, y + (r() - 0.5) * 14 * s); c.lineTo(x + 12 * s, y); c.strokeStyle = COL.ink; c.lineWidth = 7; c.stroke(); c.strokeStyle = COL.amber3; c.lineWidth = 3.5; c.stroke(); };
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#F6EEDD', '#EADBBE'); } },
        { f: 0, paint(g) {
          rr(g, pn.bb.x0 - 30, tbl, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#9AA9B3', 3);
          rr(g, fx - 10, fy - 10, fw + 20, fh + 20, 4); fs(g, '#8B6B45', 3); rr(g, fx, fy, fw, fh, 2); fs(g, '#E9DCC0', 3);
          g.save(); rr(g, fx, fy, fw, fh, 2); g.clip(); person(g, fx + fw / 2, fy + fh + 30, 2.1, '#3E4E5C', { hair: '#4A3426' }); g.restore();
          rr(g, fx, fy, fw, fh, 2); inkS(g, 3);
          rr(g, gx - 56, tbl - 42, 112, 42, 6); fs(g, COL.amber2, 3); for (let k = 0; k < 6; k++) { g.beginPath(); g.moveTo(gx - 40 + k * 16, tbl - 42); g.lineTo(gx - 40 + k * 16, tbl); inkS(g, 2); }
          for (const s of [-1, 1]) { g.beginPath(); g.moveTo(gx + s * 40, tbl - 42); g.lineTo(gx + s * 40, gy); g.lineTo(gx + s * 16, gy); inkS(g, 5); circ(g, gx + s * 12, gy, 9); fs(g, '#C9D3D9', 3); }
          g.beginPath(); g.moveTo(rx, tbl); g.lineTo(rx, ry + 44); inkS(g, 6);
          g.beginPath(); g.arc(rx, ry, 44, -Math.PI / 2 + 0.2, Math.PI * 1.5 - 0.2); g.strokeStyle = COL.ink; g.lineWidth = 11; g.stroke(); g.strokeStyle = '#C07A3A'; g.lineWidth = 5.5; g.stroke();
          for (const s of [-1, 1]) { circ(g, rx + s * 9, ry - 44, 5); fs(g, '#C9D3D9', 2.5); }
        } },
      ],
      dyn(c, t) {
        if (t < Tp) return;
        const st = Math.floor((t - Tp) * 14);
        if (st % 3 !== 2) bolt(c, gx, gy, 1, st);
        rings(c, gx, gy, t, Tp + 0.1, { a0: -40, a1: 40, r0: 26, r1: rx - gx - 50, col: COL.sig2, speed: 0.8, n: 3, w: 4, dash: [8, 8] });
        if (t >= Tp + 0.6 && st % 4 !== 1) bolt(c, rx, ry - 44, 0.6, st + 99);
      },
      labels: [{ t: sc.word('헤르츠'), x: fx + fw / 2, y: fy + fh + 2, c: 'sign', at: Tn }, { t: sc.word('증명'), x: (gx + rx) / 2, y: A.y0 + 26, c: 'tagt', at: Tp }],
    };
  };

  // ── 03 파장(item): 물결 하나의 길이 / 한 번 출렁이는 동안 나아간 거리 — 마루에서 다음 마루까지 괄호가 자라고 점 하나가 그 길을 간다
  ART.ruler = function (sc, pn, A) {
    const wl = 224, amp = 44, cy = A.y0 + 122, c0 = A.x0 + 150, c1 = c0 + wl, x0 = A.x0 + 18, x1 = A.x1 - 18;
    const T = pn.t0 + 0.5, D = clamp(pn.t1 - pn.t0 - 1.1, 0.8, 1.6);   // 이 칸은 같은 발화의 다음 칸으로 곧 넘어간다 — 낱말('길이')을 기다리면 다 자라기 전에 화면이 떠난다
    const yAt = (x) => cy - amp * Math.cos(TAU * (x - c0) / wl);   // c0·c1 이 마루(멈춘 물결 — 길이를 재는 순간)
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#EAF4F9', '#F7FBFD'); } },
        { f: 0, paint(g) {
          g.beginPath(); for (let x = x0; x <= x1 + 0.1; x += 3) { if (x === x0) g.moveTo(x, yAt(x)); else g.lineTo(x, yAt(x)); } band2(g, COL.sig2, 5);
          rr(g, x0, A.y1 - 46, x1 - x0, 30, 4); fs(g, '#E8C88E', 3);
          for (let x = x0 + 12, j = 0; x < x1 - 4; x += 12, j++) { g.beginPath(); g.moveTo(x, A.y1 - 46); g.lineTo(x, A.y1 - 46 + (j % 5 === 4 ? 16 : 9)); inkS(g, 2); }
        } },
      ],
      dyn(c, t) {
        const p = smooth((t - T) / D); if (t < T - 0.4) return;
        // 한 파장 구간을 호박색으로 덧칠(앞에서부터) · 마루 표지 · 괄호 · 그 길을 가는 점
        const xe = lerp(c0, c1, p);
        if (p > 0) { c.beginPath(); for (let x = c0; x <= xe + 0.1; x += 3) { if (x === c0) c.moveTo(x, yAt(x)); else c.lineTo(x, yAt(x)); } band2(c, COL.amber2, 7); }
        for (const [x, at] of [[c0, T - 0.4], [c1, T + D - 0.2]]) { const k = pop(t, at, 0.3, 2.2); if (k > 0) { circ(c, x, cy - amp, 9 * k); fs(c, COL.amber, 3); c.beginPath(); c.moveTo(x, cy - amp + 12); c.lineTo(x, A.y1 - 46); c.setLineDash([5, 7]); c.strokeStyle = COL.ink2; c.lineWidth = 2; c.stroke(); c.setLineDash([]); } }
        if (p > 0) { span(c, c0, xe, cy - amp - 34, COL.amber2); circ(c, xe, yAt(xe), 11); fs(c, COL.white, 3.5); }
      },
      labels: itemTag(sc, pn, A),
    };
  };

  // ── 03 도슨트 핵심(기울어진 칸): 빠르게 출렁일수록 물결 하나가 짧다 — 두 줄을 같은 빠르기로 흘리고, 짧은 물결의 끝 한 묶음이 칸을 깨고 나간다
  // 줄 이름표는 그 수준 카드의 visual.low / visual.high 그대로(검증된 카드 글). 중고등의 반비례 식(visual.formula)은 여백 왼쪽에 띄운다
  // (묶음은 오른쪽 아래에서 떠나 침묵 칸 가운데로 내려온다 — 오른쪽에 두면 날아가는 묶음 위에 글이 덮였다).
  const SQ = { wlL: 210, wlS: 48 };
  ART.squeeze = function (sc, pn, A) {
    const V = sc.visual || {}, yL = A.y0 + 98, yS = A.y0 + 220, xs = A.x0 + 18, xe = A.x1 - 26, mv = sc.moves[pn.i], show = mv.t0 - 0.35;
    const Tlow = sayAt(sc, '천천히', pn.t0 - 0.2, pn.t1) ?? pn.t0 + 0.3, Thigh = firstAt(sc, ['빠르게', '빨리'], pn.t0 - 0.2, pn.t1) ?? pn.t0 + 0.3;
    const from = [A.x1 - 96, yS], labels = [], gut = [];
    if (V.low) labels.push({ t: V.low, x: tagX(A.x0, V.low), y: A.y0 + 42, c: 'tagt', at: Tlow });
    if (V.high) labels.push({ t: V.high, x: tagX(A.x0, V.high), y: A.y0 + 168, c: 'tag', at: Thigh });
    const G = pn.gutBelow;
    if (G && V.formula) gut.push({ t: V.formula, x: 160, y: G.y0 + (G.y1 - G.y0) * 0.45, c: 'gut', at: sayAt(sc, '반비례', pn.t0, pn.t1 + 0.2) ?? mv.t0 + 0.3, rot: -2 });
    return {
      layers: [
        { f: 0.12, paint(g) { bg(g, pn, '#E6F1F8', '#F6FAFC'); } },
        { f: 0, paint(g) { for (const y of [yL, yS]) { rr(g, xs - 6, y - 34, xe - xs + 12, 68, 10); fs(g, 'rgba(255,255,255,.75)', 2); } } },
      ],
      dyn(c, t) {
        // 짧은 물결은 깨고 나갈 묶음의 왼쪽 끝(from − 72)과 위상이 이어지게 기준을 잡는다 — 묶음(BRK.packet)이 떨어져 나가도 이음매가 맞다
        const lanes = [[yL, SQ.wlL, 24, Tlow, COL.amber2, xe, xs], [yS, SQ.wlS, 12, Thigh, COL.sig2, t >= show ? from[0] - 72 : xe, from[0] - 72]];
        for (const [y, wl, amp, T, col, x1, ref] of lanes) {
          const on = smooth((t - T) / 0.4);
          flow(c, xs, x1, y, amp, wl, t, ref);
          if (on < 1) { c.setLineDash([6, 9]); c.strokeStyle = COL.grey; c.lineWidth = 3; c.globalAlpha = 1 - on; c.stroke(); c.setLineDash([]); c.globalAlpha = 1; }
          if (on > 0) { c.globalAlpha = on; band2(c, col, wl > 100 ? 6 : 5); c.globalAlpha = 1; }
          if (on > 0) { c.globalAlpha = on; span(c, xs + 30, xs + 30 + wl, y + amp + 18, col); c.globalAlpha = 1; }
        }
      },
      labels, gut, from,
    };
  };

  // ── 03 침묵 칸: 비교 자 — 긴 물결 하나(위)와 빈 자리(아래). 깨고 나온 짧은 물결 묶음이 아래 자리에 와서 눕는다(말도 움직임도 없다)
  ART.compare = function (sc, pn, A) {
    const b = pn.bb, cx = (b.x0 + b.x1) / 2, yL = b.y0 + 92, yS = b.y0 + 208, wl = SQ.wlL;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#F7F1E3', '#EEE3CA'); } },
        { f: 0, paint(g) {
          rr(g, b.x0 + 16, b.y0 + 30, b.x1 - b.x0 - 32, 112, 8); fs(g, 'rgba(255,255,255,.75)', 2);
          g.beginPath(); for (let x = b.x0 + 34; x <= b.x1 - 34; x += 3) { const yy = yL - 24 * Math.sin(TAU * (x - b.x0 - 34) / wl); if (x === b.x0 + 34) g.moveTo(x, yy); else g.lineTo(x, yy); } band2(g, COL.amber2, 6);
          span(g, b.x0 + 34, b.x0 + 34 + wl, yL + 42, COL.amber2);
          rr(g, cx - 92, yS - 34, 184, 68, 10); g.setLineDash([8, 8]); g.fillStyle = 'rgba(255,255,255,.6)'; g.fill(); g.strokeStyle = COL.ink2; g.lineWidth = 2.5; g.stroke(); g.setLineDash([]);
          rr(g, b.x0 + 16, b.y1 - 40, b.x1 - b.x0 - 32, 22, 3); fs(g, '#E8C88E', 2.5);
          for (let x = b.x0 + 28, j = 0; x < b.x1 - 20; x += 12, j++) { g.beginPath(); g.moveTo(x, b.y1 - 40); g.lineTo(x, b.y1 - 40 + (j % 5 === 4 ? 12 : 7)); inkS(g, 1.8); }
        } },
      ],
      to: [cx, yS],
    };
  };

  // ═════════════════════════════════════════════ 04 전파이야기 체험 — 모스 부호 · 헤르츠 실험 · 라이덴 병
  /** 이 칸에서 말한 낱말 중 처음 것(수준마다 대사가 다를 때 이름표 고르기) — 없으면 null. 글은 sc.word 를 거쳐 쓴다 */
  const wordIn = (sc, pn, kws) => { for (const kw of kws) if (sayAt(sc, kw, pn.t0 - 0.2, pn.t1 + 0.05) != null) return kw; return null; };
  const M_UNIT = 0.12, M_PER = MORSE.reduce((a, m) => a + (m || 1), 0);
  /** 모스 박자: T 부터 MORSE 를 되풀이할 때 t 에 눌려 있나(1) — 식 */
  function morseOn(t, T) { if (t < T) return 0; let u = ((t - T) / M_UNIT) % M_PER; for (const m of MORSE) { const len = m || 1; if (u < len) return m ? 1 : 0; u -= len; } return 0; }
  /** 켜짐 구간들 [시작, 끝](박자 칸) — reps 번 되풀이까지 */
  function morseSegs(reps) { const out = []; let u = 0; for (let r = 0; r < reps; r++) for (const m of MORSE) { const len = m || 1; if (m) out.push([u, u + len]); u += len; } return out; }
  /** 전건(모스 키) — y = 책상 윗면. 손잡이 끝(knob)의 자리를 돌려준다 */
  function tkey(c, x, y, s, down) {
    c.save(); c.translate(x, y); c.scale(s, s);
    rr(c, -74, -16, 148, 16, 4); fs(c, '#6E4A2B', 3); rr(c, 44, -34, 18, 18, 3); fs(c, COL.grey, 2.5); rr(c, -54, -32, 18, 16, 3); fs(c, '#4D3420', 2.5);
    c.save(); c.translate(-44, -28); c.rotate(down ? 0.07 : -0.03); rr(c, 0, -6, 108, 11, 4); fs(c, COL.amber2, 3); circ(c, 104, -8, 14); fs(c, COL.ink, 0); c.restore();
    c.restore();
    const a = down ? 0.07 : -0.03; return [x + (-44 + 104 * Math.cos(a)) * s, y + (-28 - 8 + 104 * Math.sin(a)) * s];
  }
  /** 위에서 누르는 손(소매가 오른쪽 위로 빠진다) */
  function pressHand(c, x, y, s) {
    c.save(); c.translate(x, y); c.scale(s, s);
    c.beginPath(); c.moveTo(-6, -40); c.quadraticCurveTo(-40, -80, -96, -150); c.strokeStyle = COL.ink; c.lineWidth = 34; c.lineCap = 'round'; c.stroke(); c.strokeStyle = COL.teal2; c.lineWidth = 27; c.stroke();
    c.beginPath(); c.ellipse(8, -34, 24, 19, -0.3, 0, TAU); fs(c, COL.skin, 3); rr(c, -6, -26, 12, 26, 6); fs(c, COL.skin, 2.5);
    c.restore();
  }
  /** 라이덴 병(전기를 담는 병): 유리 병 · 아래쪽 금속박 · 마개와 막대 끝 공 — base = 바닥 */
  function leyden(g, x, base, s) {
    g.save(); g.translate(x, base); g.scale(s, s);
    rr(g, -34, -118, 68, 118, 10); fs(g, 'rgba(214,236,246,.85)', 3); rr(g, -34, -74, 68, 74, 10); fs(g, '#AEB9C1', 3);
    rr(g, -38, -128, 76, 14, 4); fs(g, '#8B6B45', 3); g.beginPath(); g.moveTo(0, -128); g.lineTo(0, -168); inkS(g, 5); circ(g, 0, -174, 9); fs(g, COL.grey2, 3);
    g.beginPath(); g.moveTo(-22, -104); g.lineTo(-22, -84); g.strokeStyle = 'rgba(255,255,255,.9)'; g.lineWidth = 5; g.stroke();
    g.restore();
  }
  /** 불꽃 틈(두 막대 끝 공) + 아래 유도 코일 상자 — gx·gy = 틈 가운데. 막대 공은 ±r */
  function sparkGap(g, gx, gy, base, w) {
    rr(g, gx - w, base - 44, 2 * w, 44, 6); fs(g, COL.amber2, 3); for (let k = 0; k < 6; k++) { g.beginPath(); g.moveTo(gx - w + 16 + k * (2 * w - 32) / 5, base - 44); g.lineTo(gx - w + 16 + k * (2 * w - 32) / 5, base); inkS(g, 2); }
    for (const s of [-1, 1]) { g.beginPath(); g.moveTo(gx + s * (w - 16), base - 44); g.lineTo(gx + s * (w - 16), gy); g.lineTo(gx + s * 16, gy); inkS(g, 5); circ(g, gx + s * 12, gy, 9); fs(g, '#C9D3D9', 3); }
  }
  function boltAt(c, x, y, s, seed) { const r = rand(seed); c.beginPath(); c.moveTo(x - 12 * s, y); for (let k = 1; k < 5; k++) c.lineTo(x - 12 * s + 24 * s * k / 5, y + (r() - 0.5) * 14 * s); c.lineTo(x + 12 * s, y); c.strokeStyle = COL.ink; c.lineWidth = 7; c.stroke(); c.strokeStyle = COL.amber3; c.lineWidth = 3.5; c.stroke(); }
  /** 글자 대신 그리는 획(수식·글자처럼 보이지만 글자가 아니다 — 글은 DOM 으로만) */
  function glyph(c, x, y, s, seed) { const r = rand(seed); c.beginPath(); c.moveTo(x - 8 * s + r() * 4, y - 9 * s); for (let k = 0; k < 4; k++) c.lineTo(x + (r() - 0.5) * 18 * s, y + (r() - 0.5) * 18 * s); inkS(c, 3); }

  // ── 04 오프닝(넓은 칸): 전파이야기 체험존 — 전건 책상 · 불꽃 실험대 · 라이덴 병, 그리고 아이들
  ART.zone = function (sc, pn, A) {
    const base = A.y1 - 40, k1 = A.x0 + 120, g1 = A.cx + 4, j1 = A.x1 - 110, gy = base - 158, T = pn.t0 + 0.6;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#F3ECDD', '#E9DCC3'); for (const x of [A.x0 + 40, A.x1 - 150]) { rr(g, x, pn.bb.y0 + 20, 110, 70, 6); fs(g, '#D7ECF6', 0); g.strokeStyle = 'rgba(14,36,51,.15)'; g.lineWidth = 5; g.stroke(); } } },
        { f: 0, paint(g) {
          rr(g, pn.bb.x0 - 30, base, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#C8B08A', 3);
          for (const [x, w] of [[k1, 170], [g1, 190], [j1, 130]]) { rr(g, x - w / 2, base - 62, w, 14, 3); fs(g, '#A07A4C', 3); for (const s of [-1, 1]) { rr(g, x + s * (w / 2 - 16) - 5, base - 48, 10, 48, 0); fs(g, '#8B6B45', 2.5); } }
          sparkGap(g, g1, gy, base - 62, 60); leyden(g, j1, base - 62, 0.62);
          g.beginPath(); g.moveTo(j1, base - 62 - 0.62 * 174); g.quadraticCurveTo((j1 + g1) / 2, gy - 60, g1 + 21, gy); g.strokeStyle = COL.ink2; g.lineWidth = 2.5; g.stroke();
        } },
        { f: -0.05, front: true, paint(g) { person(g, A.x0 + 60, A.y1 + 6, 0.92, COL.teal2); person(g, g1 - 98, A.y1 + 8, 0.8, COL.amber2, { hair: '#6B4A33' }); person(g, j1 + 78, A.y1 + 6, 0.86, COL.sig2); } },
      ],
      dyn(c, t) {
        tkey(c, k1, base - 62, 0.8, morseOn(t, T));
        const st = Math.floor((t - T) * 10); if (t >= T && st % 5 < 2) boltAt(c, g1, gy, 0.9, st);
      },
      labels: [{ t: sc.word('전파이야기 체험존'), x: A.cx, y: A.y0 + 26, c: 'sign', at: sc.w('체험존') }],
    };
  };

  // ── 04 모스 부호를 손으로 쳐 본다(초등 item 0 / 중고등은 '손으로 하나씩') — 누를 때마다 종이띠에 점·선이 찍혀 나간다
  ART.tap = function (sc, pn, A) {
    const desk = A.y1 - 52, kx = A.x0 + 170, tapeY = A.y0 + 70, head = kx + 150, V = 110, T = pn.t0 + 0.4;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#F6EAD3', '#EAD3AE'); } },
        { f: 0, paint(g) {
          rr(g, pn.bb.x0 - 30, desk, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#B57B43', 3);
          rr(g, head - 34, tapeY - 26, 52, 52, 6); fs(g, COL.grey2, 3); circ(g, head - 8, tapeY, 10); fs(g, COL.ink2, 2.5);
          g.beginPath(); g.moveTo(kx + 74, desk - 20); g.bezierCurveTo(kx + 120, desk - 30, head - 40, desk - 60, head - 14, tapeY + 26); inkS(g, 3);
          rr(g, head, tapeY - 13, A.x1 - head + 40, 26, 2); fs(g, '#FFF9EC', 2.5);
        } },
      ],
      dyn(c, t) {
        const down = morseOn(t, T), kn = tkey(c, kx, desk, 1.15, down);
        pressHand(c, kn[0] + 2, kn[1] - 12, 0.9);
        if (t < T) return;
        const now = (t - T) / M_UNIT, reps = Math.floor(now / M_PER) + 1;
        c.save(); rr(c, head, tapeY - 13, A.x1 - head + 40, 26, 2); c.clip();
        for (const [u0, u1] of morseSegs(reps)) {
          if (u0 > now) break;
          const xa = head + (now - Math.min(u1, now)) * M_UNIT * V, xb = head + (now - u0) * M_UNIT * V;
          if (xa > A.x1 + 40) continue; rr(c, xa, tapeY - 6, Math.max(8, xb - xa), 12, 6); fs(c, COL.ink, 0);
        }
        c.restore();
      },
      labels: itemTag(sc, pn, A),
    };
  };

  // ── 04 초등: 짧게 똑, 길게 뚜우 — 두 소리만으로 편지를 쓴다
  ART.dotdash = function (sc, pn, A) {
    const Td = sc.w('짧게 똑', pn.t0 - 0.2), Tl = sc.w('길게 뚜우', pn.t0 - 0.2), Te = sc.w('편지', pn.t0 - 0.2), cy = A.y0 + 128, dx = A.x0 + 100, lx = A.x0 + 300, ex = A.x1 - 104;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#FFF4E1', '#F5E4C6'); } },
        { f: 0, paint(g) { rr(g, pn.bb.x0 - 30, A.y1 - 30, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#E2C08C', 3); } },
      ],
      dyn(c, t) {
        const a = pop(t, Td, 0.3, 2); if (a > 0) { c.save(); c.translate(dx, cy); c.scale(a, a); circ(c, 0, 0, 22); fs(c, COL.amber2, 3.5); c.restore(); rings(c, dx + 18, cy, t, Td, { a0: -40, a1: 40, r0: 30, r1: 60, n: 2, speed: 1.4, col: COL.amber, w: 4 }); }
        const b = pop(t, Tl, 0.3, 2); if (b > 0) { c.save(); c.translate(lx, cy); c.scale(b, b); rr(c, -70, -18, 140, 36, 18); fs(c, COL.teal2, 3.5); c.restore(); rings(c, lx + 74, cy, t, Tl, { a0: -40, a1: 40, r0: 20, r1: 74, n: 3, speed: 0.5, col: COL.teal, w: 4 }); }
        // 편지: 봉투가 열리고 점·선 줄이 접혀 들어간다
        const e = pop(t, Te, 0.35, 1.8); if (e <= 0) return;
        c.save(); c.translate(ex, cy + 10); c.scale(e, e);
        rr(c, -78, -50, 156, 100, 6); fs(c, COL.white, 3.5);
        c.beginPath(); c.moveTo(-78, -50); c.lineTo(0, 8); c.lineTo(78, -50); inkS(c, 3);
        let x = -60; for (const m of [1, 3, 1, 1, 3, 3, 1]) { const w = m === 3 ? 22 : 8; rr(c, x, 22, w, 8, 4); fs(c, COL.ink, 0); x += w + 6; }
        c.restore();
      },
      labels: [{ t: sc.word('짧게 똑'), x: dx + 10, y: A.y0 + 40, c: 'tag', at: Td }, { t: sc.word('길게 뚜우'), x: lx, y: A.y0 + 40, c: 'tagt', at: Tl }],
    };
  };

  // ── 04 중고등: 체험 세 가지 — 모스 부호 · 헤르츠의 전파 실험 · 라이덴 병이 말에 맞춰 차례로 놓인다
  ART.three = function (sc, pn, A) {
    const base = A.y1 - 48, xs = [A.x0 + 120, A.cx + 10, A.x1 - 104], kw = ['모스 부호', '헤르츠', '라이덴 병'], T = kw.map((w) => sc.w(w, pn.t0 - 0.2));
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#F2ECE0', '#E6DAC4'); } },
        { f: 0, paint(g) { rr(g, pn.bb.x0 - 30, base, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#C8B08A', 3); for (const x of xs) { g.beginPath(); g.ellipse(x, base + 4, 76, 12, 0, 0, TAU); fs(g, 'rgba(14,36,51,.12)', 0); } } },
      ],
      dyn(c, t) {
        const k = T.map((t0) => pop(t, t0, 0.35, 1.9));
        if (k[0] > 0) { c.save(); c.translate(xs[0], base); c.scale(k[0], k[0]); tkey(c, 0, 0, 0.82, morseOn(t, T[0] + 0.3)); c.restore(); }
        if (k[1] > 0) { c.save(); c.translate(xs[1], base); c.scale(k[1], k[1]); sparkGap(c, 0, -96, 0, 52); c.restore(); const st = Math.floor((t - T[1]) * 10); if (st > 3 && st % 5 < 2) boltAt(c, xs[1], base - 96 * k[1], 0.8, st); }
        if (k[2] > 0) { c.save(); c.translate(xs[2], base); c.scale(k[2], k[2]); leyden(c, 0, 0, 0.72); c.restore(); }
      },
      labels: itemTag(sc, pn, A).concat(kw.map((w, i) => ({ t: sc.word(w), x: xs[i], y: A.y1 - 22, c: i === 1 ? 'tagt' : 'tag', at: T[i] }))),
    };
  };

  // ── 04 초등: 글자마다 약속 — 공책에 글자 칸과 점·선 묶음이 한 줄씩 적힌다(글자 모양은 그림 획)
  ART.codebook = function (sc, pn, A) {
    const x0 = A.x0 + 90, x1 = A.x1 - 90, y0 = A.y0 + 16, y1 = A.y1 - 22, T = pn.t0 + 0.4, rows = [[1, 3], [3, 1, 1, 1], [3, 1, 3, 1], [1], [1, 1, 3, 1], [3, 3, 1]];
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#EEF4F0', '#DCE9E0'); } },
        { f: 0, paint(g) {
          rr(g, x0 - 8, y0 + 6, x1 - x0 + 16, y1 - y0, 8); fs(g, '#8B6B45', 3);
          for (const s of [0, 1]) { rr(g, s ? (x0 + x1) / 2 + 2 : x0, y0, (x1 - x0) / 2 - 2, y1 - y0 - 6, 4); fs(g, '#FFFDF5', 3); }
          g.strokeStyle = 'rgba(11,127,181,.18)'; g.lineWidth = 2; for (let y = y0 + 34; y < y1 - 12; y += 32) { g.beginPath(); g.moveTo(x0 + 10, y); g.lineTo(x1 - 10, y); g.stroke(); }
        } },
      ],
      dyn(c, t) {
        const n = Math.floor(clamp((t - T) / Math.max(1, pn.t1 - T - 0.6)) * rows.length + 1e-6);
        rows.slice(0, n).forEach((r, i) => {
          const col = i % 2, row = i >> 1, bx = (col ? (x0 + x1) / 2 + 24 : x0 + 22), by = y0 + 30 + row * 64;
          rr(c, bx, by - 18, 36, 36, 6); fs(c, COL.amber3, 2.5); glyph(c, bx + 18, by, 1, 50 + i);
          let x = bx + 52; for (const m of r) { const w = m === 3 ? 24 : 9; rr(c, x, by - 5, w, 10, 5); fs(c, COL.ink, 0); x += w + 6; }
        });
      },
      labels: itemTag(sc, pn, A),
    };
  };

  // ── 04 자주 쓰는 글자일수록 짧은 신호(부호) — 높이 쌓인 글자 칸 옆엔 점 하나, 낮은 더미 옆엔 긴 묶음
  ART.frequent = function (sc, pn, A) {
    const base = A.y1 - 52, hx = A.x0 + 250, lx = A.x1 - 214, Tf = sc.w('자주 쓰는 글자', pn.t0 - 0.2), sw = wordIn(sc, pn, ['짧은 신호', '짧은 부호']), Ts = sw ? sc.w(sw, pn.t0 - 0.2) : Tf + 0.6;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#EEF6FA', '#DCEBF3'); } },
        { f: 0, paint(g) { rr(g, pn.bb.x0 - 30, base, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#C9D9E2', 3); } },
      ],
      dyn(c, t) {
        // 더미는 말하는 동안 쌓인다(높은 더미 = 자주 쓰는 글자)
        const p = smooth((t - pn.t0 - 0.2) / 1.2), hn = Math.round(6 * p), ln = Math.round(2 * p);
        for (let k = 0; k < hn; k++) { rr(c, hx - 26, base - 26 - k * 25, 52, 24, 4); fs(c, COL.amber3, 2.5); glyph(c, hx, base - 14 - k * 25, 0.6, 7); }
        for (let k = 0; k < ln; k++) { rr(c, lx - 26, base - 26 - k * 25, 52, 24, 4); fs(c, COL.teal3, 2.5); glyph(c, lx, base - 14 - k * 25, 0.6, 9); }
        const a = pop(t, Ts, 0.3, 2.4); if (a > 0) { circ(c, hx + 74, base - 120, 16 * a); fs(c, COL.amber2, 3.5); }
        const b = pop(t, Ts + 0.3, 0.3, 2); if (b > 0) { let x = lx + 46; c.save(); c.globalAlpha = clamp(b); for (const m of [3, 1, 3, 3]) { const w = m === 3 ? 30 : 11; rr(c, x, base - 66, w, 13, 6); fs(c, COL.teal2, 3); x += w + 7; } c.restore(); }
      },
      labels: itemTag(sc, pn, A).concat([{ t: sc.word('자주 쓰는 글자'), x: hx, y: A.y1 - 24, c: 'tag', at: Tf }]).concat(sw ? [{ t: sc.word(sw), x: hx + 74, y: base - 166, c: 'tagt', at: Ts }] : []),
    };
  };

  // ── 04 중고등: 두 사실 — 영어에서 가장 흔한 E 는 점 하나 · 한글 전신 부호를 만든 김학우(카드 visual.facts 그대로)
  ART.factpair = function (sc, pn, A) {
    const F = (sc.visual && sc.visual.facts) || [], T0 = firstAt(sc, ['점 하나'], pn.t0 - 0.2, pn.t1) ?? pn.t0 + 0.4, T1 = firstAt(sc, ['김학우'], pn.t0 - 0.2, pn.t1) ?? pn.t1 - 2, base = A.y1 - 24;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#F4EFE6', '#E8DECD'); g.fillStyle = '#E3EEF4'; g.fillRect(A.cx, pn.bb.y0 - 1400, pn.bb.x1 - A.cx + 40, pn.bb.y1 - pn.bb.y0 + 2800); } },
        { f: 0, paint(g) { g.beginPath(); g.moveTo(A.cx, pn.bb.y0 - 10); for (let k = 0; k < 12; k++) g.lineTo(A.cx + (k % 2 ? 8 : -8), pn.bb.y0 + (pn.bb.y1 - pn.bb.y0) * (k + 1) / 12); inkS(g, 4); } },
      ],
      dyn(c, t) {
        const a = pop(t, T0, 0.35, 2.4); if (a > 0) { circ(c, A.x0 + 150, base - 46, 26 * a); fs(c, COL.amber2, 4); rings(c, A.x0 + 176, base - 46, t, T0, { a0: -40, a1: 40, r0: 34, r1: 80, n: 2, speed: 1.2, col: COL.amber, w: 4 }); }
        const b = pop(t, T1, 0.35, 1.8); if (b > 0) { c.save(); c.translate(A.x1 - 150, base); c.scale(b, b);
          rr(c, -70, -76, 140, 76, 6); fs(c, '#FFFDF5', 3); c.beginPath(); c.moveTo(0, -76); c.lineTo(0, 0); inkS(c, 2.5);
          for (let r = 0; r < 3; r++) for (const s of [-1, 1]) { glyph(c, s * 52 - (s > 0 ? 18 : -2), -58 + r * 22, 0.55, 30 + r * 2 + s); let x = s < 0 ? -40 : 22; for (const m of [r % 2 ? 3 : 1, 1, 3]) { const w = m === 3 ? 12 : 5; rr(c, x, -61 + r * 22, w, 5, 2.5); fs(c, COL.ink, 0); x += w + 4; } }
          c.restore(); }
      },
      labels: F.slice(0, 2).map((f, i) => ({ t: f.big, sub: f.label, x: i ? A.x1 - 150 : A.x0 + 150, y: A.y0 + 58, c: 'fact', at: i ? T1 : T0, rot: i ? 1.2 : -1.2 })),
    };
  };

  // ── 04 질문 띠 변형: v5 '모스 부호는 어떻게?' 점·선 줄이 흐른다 · v6 '헤르츠 실험은?' 작은 불꽃 틈
  ASKV[5] = { dyn(c, t, A) { const y = A.y1 - 46, now = t / M_UNIT; let x = A.x0 + 8 - ((now * 9) % 187) - 187; /* 187 = 아래 묶음 한 벌의 폭 */ c.save(); c.beginPath(); c.rect(A.x0, y - 20, A.w, 40); c.clip(); for (let r = 0; r < 4; r++) for (const m of [1, 3, 1, 1, 3, 1, 3]) { const w = m === 3 ? 28 : 10; rr(c, x, y - 6, w, 12, 6); fs(c, COL.amber2, 2.5); x += w + 9; } c.restore(); } };
  ASKV[6] = {
    paint(g, A) { sparkGap(g, A.cx - 40, A.y1 - 86, A.y1 - 16, 44); },
    dyn(c, t, A, pn) { const st = Math.floor((t - pn.t0) * 10); if (st >= 0 && st % 4 < 2) boltAt(c, A.cx - 40, A.y1 - 86, 0.7, st); },
  };

  // ── 04 도슨트 핵심(기울어진 칸): 헤르츠 실험 — 라이덴 병이 담은 전기로 틈에 불꽃이 튀고, 거기서 나온 전파 한 덩이가 칸을 깨고 나간다
  ART.hertzlab = function (sc, pn, A) {
    const base = A.y1 - 18, gx = A.cx - 30, gy = A.y0 + 128, jx = A.x1 - 116, Tf = sc.w('불꽃', pn.t0 - 0.2), Tj = sc.w('라이덴 병', pn.t0 - 0.2), mv = sc.moves[pn.i];
    return {
      layers: [
        { f: 0.12, paint(g) { bg(g, pn, '#EFE6D3', '#E2D2B3'); } },
        { f: 0, paint(g) {
          rr(g, pn.bb.x0 - 30, base, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#9AA9B3', 3);
          sparkGap(g, gx, gy, base, 70); leyden(g, jx, base, 0.9);
          g.beginPath(); g.moveTo(jx, base - 0.9 * 174); g.bezierCurveTo(jx - 40, gy - 90, gx + 120, gy - 80, gx + 54, gy - 2); g.strokeStyle = COL.ink2; g.lineWidth = 3; g.stroke();
        } },
      ],
      dyn(c, t) {
        // 불꽃: '불꽃' 에서 튀기 시작해 칸을 떠날 때까지 깜빡인다. 고리는 그 틈에서 오른쪽으로
        if (t < Tf) return;
        const st = Math.floor((t - Tf) * 12); if (st % 3 !== 2 && t < mv.t0 - 0.35) boltAt(c, gx, gy, 1.1, st);
        rings(c, gx + 16, gy, t, Tf + 0.1, { a0: -50, a1: 50, r0: 28, r1: 200, col: COL.sig2, speed: 0.7, n: 3, w: 4, dash: [8, 8] });
        const j = pop(t, Tj, 0.3, 2); if (j > 0) { c.globalAlpha = 0.35 + 0.35 * Math.sin((t - Tj) * 5) ** 2; rr(c, jx - 36, base - 0.9 * 80, 72, 0.9 * 80, 10); c.strokeStyle = COL.amber2; c.lineWidth = 6; c.stroke(); c.globalAlpha = 1; }
      },
      labels: itemTag(sc, pn, A).concat([{ t: sc.word('라이덴 병'), x: jx, y: A.y0 + 40, c: 'tagt', at: Tj }]),
      from: [gx + 36, gy],
    };
  };

  // ── 04 침묵 칸: 떨어진 곳의 고리(받는 쪽) — 날아온 전파 덩이가 고리의 틈 앞에 와서 멈춘다
  ART.ring = function (sc, pn, A) {
    const b = pn.bb, tbl = b.y1 - 46, rx = b.x1 - 120, ry = tbl - 112;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#EAF1F5', '#D7E3EA'); rr(g, b.x0 + 30, b.y0 + 30, 100, 80, 4); fs(g, '#D2EAF6', 0); g.strokeStyle = 'rgba(14,36,51,.18)'; g.lineWidth = 5; g.stroke(); } },
        { f: 0, paint(g) {
          rr(g, b.x0 - 30, tbl, b.x1 - b.x0 + 60, 600, 0); fs(g, '#9AA9B3', 3);
          g.beginPath(); g.moveTo(rx, tbl); g.lineTo(rx, ry + 60); inkS(g, 6);
          g.beginPath(); g.arc(rx, ry, 60, -Math.PI / 2 + 0.16, Math.PI * 1.5 - 0.16); g.strokeStyle = COL.ink; g.lineWidth = 13; g.stroke(); g.strokeStyle = '#C07A3A'; g.lineWidth = 6.5; g.stroke();
          for (const s of [-1, 1]) { circ(g, rx + s * 10, ry - 60, 6); fs(g, '#C9D3D9', 2.5); }
        } },
      ],
      to: [rx - 92, ry - 64],
    };
  };

  // ── 04 마지막 칸 변형: 두 로봇 위로 점·선 줄이 흘러간다
  const M_W = MORSE.reduce((a, m) => a + (m || 1) * 12 + 6, 0);            // 점·선 줄 한 벌의 폭 — 흐름을 이 폭으로 되풀이해야 이음매가 안 튄다
  FINV[3] = function (c, t, A) { const y = A.y0 + 54, V = 90; let x = 60 - ((t * V) % M_W) - M_W; c.save(); c.beginPath(); c.rect(40, y - 20, SW - 80, 40); c.clip(); for (let r = 0; r < 4; r++) for (const m of MORSE) { const w = (m || 1) * 12; if (m) { rr(c, x, y - 7, w, 14, 7); fs(c, COL.amber2, 2.5); } x += w + 6; } c.restore(); };

  // ═════════════════════════════════════════════ 07 해상무선통신 — 구조 신호 · 밤낮 듣기 · 자동 장치
  // 조사 자료(07-maritime, A 등급): 구조선은 배가 가라앉은 **뒤** 구명정의 사람들을 건졌다 — 그래서 구조 칸에는 가라앉는 배를 그리지 않는다.
  /** 1912년의 큰 여객선(검은 선체·흰 윗부분·담황색 굴뚝 넷, 뱃머리 오른쪽). wl = 물 높이. 돛대 사이 안테나 줄 가운데 = (x, wl − 128s) */
  function liner(g, x, wl, s, lit) {
    g.save(); g.translate(x, wl); g.scale(s, s);
    g.beginPath(); g.moveTo(-128, -128); g.lineTo(128, -128); g.strokeStyle = COL.ink2; g.lineWidth = 1.5; g.stroke();
    for (const m of [-128, 128]) { g.beginPath(); g.moveTo(m * 1.02, -52); g.lineTo(m, -132); inkS(g, 3); }
    for (const fx of [-74, -30, 14, 58]) { g.beginPath(); g.moveTo(fx - 9, -62); g.lineTo(fx - 4, -106); g.lineTo(fx + 14, -106); g.lineTo(fx + 9, -62); g.closePath(); fs(g, '#E0B868', 2.5); g.beginPath(); g.moveTo(fx - 4.5, -102); g.lineTo(fx - 4, -106); g.lineTo(fx + 14, -106); g.lineTo(fx + 13.5, -98); g.lineTo(fx - 5.2, -98); g.closePath(); fs(g, COL.ink, 0); }
    rr(g, -112, -64, 196, 13, 2); fs(g, '#F4F1E6', 2.5); rr(g, -142, -52, 276, 18, 2); fs(g, '#F4F1E6', 3);
    g.beginPath(); g.moveTo(-164, -36); g.lineTo(176, -36); g.lineTo(154, 8); g.lineTo(-150, 8); g.closePath(); fs(g, '#22313C', 3);
    for (let k = 0; k < 16; k++) { circ(g, -128 + k * 17, -22, 3); g.fillStyle = lit ? COL.amber3 : '#8FA2AE'; g.fill(); }
    g.restore();
  }
  /** 작은 배(구조선·이웃 배, 뱃머리 오른쪽) — 돛대 끝 = (x + 40s, wl − 96s) */
  function freighter(g, x, wl, s, hull) {
    g.save(); g.translate(x, wl); g.scale(s, s);
    g.beginPath(); g.moveTo(40, -26); g.lineTo(40, -96); inkS(g, 3); circ(g, 40, -98, 4); fs(g, COL.amber2, 2);
    rr(g, -36, -80, 16, 28, 2); fs(g, COL.ink2, 2.5); rr(g, -62, -54, 74, 28, 3); fs(g, '#F4F1E6', 3); for (let k = 0; k < 4; k++) { rr(g, -54 + k * 16, -46, 9, 9, 2); fs(g, COL.sig3, 1.5); }
    g.beginPath(); g.moveTo(-92, -28); g.lineTo(98, -28); g.lineTo(82, 6); g.lineTo(-80, 6); g.closePath(); fs(g, hull || '#A8432F', 3);
    g.restore();
  }
  /** 구명정(사람 머리 몇) */
  function lifeboat(c, x, y, s, n) {
    c.save(); c.translate(x, y); c.scale(s, s);
    for (let k = 0; k < n; k++) { circ(c, -24 + k * 16, -14, 7); fs(c, COL.skin, 2); }
    c.beginPath(); c.moveTo(-44, -8); c.lineTo(44, -8); c.quadraticCurveTo(40, 10, 24, 12); c.lineTo(-24, 12); c.quadraticCurveTo(-40, 10, -44, -8); c.closePath(); fs(c, '#F4F1E6', 3);
    c.restore();
  }
  /** 물결 지는 바다(앞 경계가 출렁인다) — 아래는 칸 밖까지 채운다 */
  function seaFill(c, x0, x1, y, t, col, amp, wl) { sine(c, x0, x1, y, amp || 6, wl || 70, -t * 1.6); c.lineTo(x1, y + 900); c.lineTo(x0, y + 900); c.closePath(); c.fillStyle = col; c.fill(); }

  // ── 07 오프닝(넓은 칸): 저녁 바다를 가는 큰 여객선 — 이름표 '타이타닉호'
  ART.sea = function (sc, pn, A) {
    const wl = A.y1 - 70, x = A.cx + 10;
    return {
      layers: [
        { f: 0.14, paint(g) { bg(g, pn, '#F6C995', '#FCE9D2'); circ(g, A.x0 + 90, wl - 40, 34); fs(g, '#FFE2A8', 0); cloud(g, A.x1 - 140, A.y0 + 30, 0.9, 'rgba(255,255,255,.7)'); } },
        { f: 0.06, paint(g) { rr(g, pn.bb.x0 - 40, wl - 4, pn.bb.x1 - pn.bb.x0 + 80, 900, 0); fs(g, '#5E9CBF', 0); } },
      ],
      dyn(c, t) {
        const bob = 2 * Math.sin(t * 1.4);
        for (const [k, fx] of [[0, -74], [1, -30], [2, 14]]) for (let j = 0; j < 3; j++) { const u = ((t * 0.45 + j / 3 + k * 0.21) % 1 + 1) % 1; c.globalAlpha = 0.55 * (1 - u); circ(c, x + fx * 1.05 + 4 - u * 40, wl - 116 - u * 26, 7 + u * 9); c.fillStyle = '#EDE6DA'; c.fill(); } c.globalAlpha = 1;   // 앞 세 굴뚝 연기가 뒤로 흩어진다
        liner(c, x, wl + bob, 1.05, false);
        seaFill(c, pn.bb.x0 - 40, pn.bb.x1 + 40, wl + 2, t, '#4F8FB4', 5, 60);
        c.strokeStyle = 'rgba(255,255,255,.6)'; c.lineWidth = 3; for (let k = 0; k < 8; k++) { const xx = ((A.x0 + k * 84 - t * 24) % (A.w + 80) + A.w + 80) % (A.w + 80) + A.x0 - 40, yy = wl + 24 + (k % 3) * 14; c.beginPath(); c.moveTo(xx, yy); c.lineTo(xx + 26, yy); c.stroke(); }
      },
      labels: [{ t: sc.word('타이타닉호'), x: A.cx, y: A.y0 + 26, c: 'sign', at: sc.w('타이타닉호') }],
    };
  };

  // ── 07 구조 신호(item): 밤바다에서 기우는 배 — 무선실 창에 불이 켜져 있고 안테나 줄에서 구조 신호 고리가 끝까지 나간다
  ART.sos = function (sc, pn, A) {
    const wl = A.y1 - 54, x = A.cx + 70, ang = 0.13, T = pn.t0 + 0.5;
    const stars = (() => { const r = rand(707), out = []; for (let k = 0; k < 30; k++) out.push([pn.bb.x0 + r() * (pn.bb.x1 - pn.bb.x0), pn.bb.y0 - 200 + r() * (wl - pn.bb.y0 + 160), 1 + 1.8 * r()]); return out; })();
    const r0 = 128 * 0.92 - 10, tip = [x + r0 * Math.sin(ang), wl - r0 * Math.cos(ang)];   // 안테나 줄 가운데를 배와 같이 기울인 자리
    return {
      layers: [
        { f: 0.12, paint(g) { bg(g, pn, '#0F2436', '#1D3B55'); for (const [sx, sy, r] of stars) { circ(g, sx, sy, r); g.fillStyle = 'rgba(255,255,255,.8)'; g.fill(); } } },
      ],
      dyn(c, t) {
        c.save(); c.translate(x, wl); c.rotate(ang); c.translate(-x, -wl); liner(c, x, wl + 10, 0.92, true);
        const on = morseOn(t, T); if (on) { circ(c, x - 40, wl - 52, 6); fs(c, COL.amber3, 0); }
        c.restore();
        rings(c, tip[0], tip[1], t, T, { a0: -170, a1: -10, r0: 20, r1: 210, col: COL.amber3, speed: 0.5, n: 4, w: 4, dash: [9, 8], al: 1 });
        seaFill(c, pn.bb.x0 - 40, pn.bb.x1 + 40, wl, t, '#123049', 6, 60);
        c.strokeStyle = 'rgba(255,255,255,.35)'; c.lineWidth = 3; for (let k = 0; k < 6; k++) { const xx = A.x0 + 30 + k * 96, yy = wl + 20 + (k % 2) * 14; c.beginPath(); c.moveTo(xx, yy); c.lineTo(xx + 24, yy); c.stroke(); }
      },
      labels: itemTag(sc, pn, A),
    };
  };

  // ── 07 그 신호를 들은 다른 배가 달려와 구명정의 사람들을 구한다(새벽) — 가라앉는 배는 없다(구조는 침몰 뒤)
  ART.rescue = function (sc, pn, A) {
    const wl = A.y1 - 60, T = pn.t0 + 0.2, D = Math.max(1.5, pn.t1 - pn.t0 - 0.6), lw = wordIn(sc, pn, ['구명정']);
    return {
      layers: [
        { f: 0.12, paint(g) { bg(g, pn, '#F5D7B8', '#DDEAF2', pn.bb.y0, wl); circ(g, A.x1 - 90, wl - 8, 40); fs(g, '#FFE7B5', 0); } },
        { f: 0.05, paint(g) { rr(g, pn.bb.x0 - 40, wl - 4, pn.bb.x1 - pn.bb.x0 + 80, 900, 0); fs(g, '#6FA8C8', 0); } },
      ],
      dyn(c, t) {
        const p = smooth((t - T) / D), sx = lerp(A.x0 + 60, A.cx - 80, p);
        freighter(c, sx, wl + 4, 1.05);
        if (p > 0.05 && p < 1) { c.strokeStyle = 'rgba(255,255,255,.8)'; c.lineWidth = 3; for (let k = 0; k < 3; k++) { c.beginPath(); c.moveTo(sx - 110 - k * 26, wl + 6 + k * 4); c.lineTo(sx - 96 - k * 26 - 20, wl + 6 + k * 4); c.stroke(); } }
        [[A.x1 - 210, 0], [A.x1 - 120, 1.4], [A.x1 - 60, 2.6]].forEach(([bx, ph], i) => lifeboat(c, bx, wl + 2 + 2 * Math.sin(t * 1.6 + ph), 0.82, 3 + (i % 2)));
        seaFill(c, pn.bb.x0 - 40, pn.bb.x1 + 40, wl + 8, t, '#5D98BA', 4, 56);
      },
      labels: lw ? [{ t: sc.word(lw), x: A.x1 - 120, y: A.y0 + 30, c: 'tagt', at: sc.w(lw, pn.t0 - 0.2) }] : [],
    };
  };

  // ── 07 질문 띠 변형: v7 '무엇이 달라졌나요?' 물 위에 뜬 구명 튜브 · v8 '지금은 어떤 규칙?' 깜빡이는 자동 장치를 단 배
  ASKV[7] = { dyn(c, t, A) {
    const y = A.y1 - 52 + 4 * Math.sin(t * 1.8), x = A.cx - 36;
    seaFill(c, A.x0 - 6, A.x1 + 6, A.y1 - 40, t, '#8CC8E2', 4, 50);
    for (let k = 0; k < 8; k++) { c.beginPath(); c.arc(x, y, 30, k * TAU / 8, (k + 1) * TAU / 8); c.strokeStyle = k % 2 ? COL.white : COL.red; c.lineWidth = 14; c.stroke(); }
    circ(c, x, y, 37); inkS(c, 3); circ(c, x, y, 23); inkS(c, 3);
  } };
  ASKV[8] = {
    paint(g, A) { rr(g, A.x0 - 6, A.y1 - 40, A.w + 12, 60, 0); fs(g, '#8CC8E2', 0); freighter(g, A.cx - 30, A.y1 - 38, 0.8, '#2F5D7C'); },
    dyn(c, t, A) { const x = A.cx - 30 + 70 * 0.8, y = A.y1 - 38 - 26 * 0.8 - 12; rr(c, x - 7, y - 8, 14, 18, 4); fs(c, '#F08A24', 2.5); if (Math.floor(t * 2.5) % 2) { circ(c, x, y - 12, 6); fs(c, COL.red, 2); } rings(c, x, y - 12, t, 0, { a0: -150, a1: -30, r0: 12, r1: 40, n: 2, speed: 0.9, col: COL.red, w: 3 }); },
  };

  // ── 07 밤낮 끊기지 않게 듣는다(item): 배의 무선실 — 헤드폰을 쓴 무선사, 둥근 창 밖은 해와 달이 번갈아 지나간다
  ART.watch = function (sc, pn, A) {
    const desk = A.y1 - 58, px = A.x0 + 150, po = [A.x1 - 116, A.y0 + 96], lw = wordIn(sc, pn, ['밤낮', '언제나']);
    return {
      layers: [
        { f: 0.08, paint(g) { bg(g, pn, '#E8DDCB', '#D9C9AE'); for (let x = pn.bb.x0; x < pn.bb.x1; x += 46) { g.fillStyle = 'rgba(14,36,51,.05)'; g.fillRect(x, pn.bb.y0 - 400, 3, pn.bb.y1 - pn.bb.y0 + 800); } } },
        { f: 0, paint(g) {
          person(g, px, desk + 34, 1.45, '#3E5A70');
          g.beginPath(); g.arc(px, desk + 34 - 62 * 1.45, 25, Math.PI * 1.1, Math.PI * 1.9); inkS(g, 6); for (const s of [-1, 1]) { rr(g, px + s * 24 - 7, desk + 34 - 62 * 1.45 - 10, 14, 22, 5); fs(g, COL.ink2, 2.5); }
          rr(g, pn.bb.x0 - 30, desk, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#8B6B45', 3);
          rr(g, A.cx - 50, desk - 70, 140, 70, 6); fs(g, '#5C6B75', 3); for (const k of [0, 1, 2]) { circ(g, A.cx - 22 + k * 40, desk - 40, 11); fs(g, COL.cream, 2.5); }
          circ(g, po[0], po[1], 64); fs(g, '#B9A27A', 4);
        } },
      ],
      dyn(c, t) {
        // 둥근 창: 하늘판이 돌며 낮(해)과 밤(달)이 번갈아 — 무선은 그동안 끊기지 않는다(무선기 불빛은 늘 켜짐)
        const a = (t - pn.t0) * 1.3, day = 0.5 + 0.5 * Math.cos(a);
        c.save(); circ(c, po[0], po[1], 52); c.clip();
        c.fillStyle = 'rgb(' + Math.round(lerp(28, 170, day)) + ',' + Math.round(lerp(52, 214, day)) + ',' + Math.round(lerp(84, 236, day)) + ')'; c.fillRect(po[0] - 60, po[1] - 60, 120, 120);
        for (const [k, col] of [[0, '#FFD66B'], [Math.PI, '#F4F1E6']]) { const b = a + k; circ(c, po[0] + 40 * Math.sin(b), po[1] + 34 - 50 * Math.cos(b) * 0.9, 13); fs(c, col, 2.5); }
        c.fillStyle = '#4F8FB4'; c.fillRect(po[0] - 60, po[1] + 22, 120, 40);
        c.restore(); circ(c, po[0], po[1], 52); inkS(c, 4);
        circ(c, A.cx + 76, desk - 56, 6); fs(c, COL.red, 2);
        rings(c, A.cx + 20, desk - 74, t, pn.t0 + 0.4, { a0: -150, a1: -30, r0: 14, r1: 52, n: 2, speed: 0.8, col: COL.teal, w: 3 });
      },
      labels: itemTag(sc, pn, A).concat(lw ? [{ t: sc.word(lw), x: A.x1 - 260, y: A.y0 + 40, c: 'tag', at: sc.w(lw, pn.t0 - 0.2) }] : []),
    };
  };

  // ── 07 초등: 누가 도움을 부르면 가까운 배가 달려간다 — 부르는 작은 배와 멀고 가까운 배들, 가장 가까운 배가 뱃머리를 돌린다
  ART.nearby = function (sc, pn, A) {
    const wl = A.y1 - 64, bx = A.x0 + 120, T = sc.w('가까운 배', pn.t0 - 0.2);
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#D6ECF6', '#F2F9FC'); rr(g, pn.bb.x0 - 40, wl - 30, pn.bb.x1 - pn.bb.x0 + 80, 900, 0); fs(g, '#7DB7D3', 0); } },
        { f: 0.04, paint(g) { freighter(g, A.x1 - 70, wl - 36, 0.42, '#6F8796'); freighter(g, A.cx + 40, wl - 30, 0.5, '#7F8F99'); } },
      ],
      dyn(c, t) {
        c.save(); c.translate(bx, wl); c.scale(0.7, 0.7); c.beginPath(); c.moveTo(-50, -14); c.lineTo(50, -14); c.lineTo(38, 8); c.lineTo(-40, 8); c.closePath(); fs(c, '#F4F1E6', 3); c.beginPath(); c.moveTo(0, -14); c.lineTo(0, -64); inkS(c, 3); poly(c, [[2, -62], [2, -24], [34, -30]]); fs(c, COL.red, 2.5); c.restore();
        rings(c, bx, wl - 50, t, pn.t0 + 0.2, { a0: -170, a1: -10, r0: 16, r1: 120, col: COL.red, speed: 0.7, n: 3, w: 4, dash: [8, 7] });
        const p = smooth((t - T) / 1.6), x = lerp(A.x1 - 150, A.cx + 70, p);
        c.save(); c.translate(x, wl + 10); c.scale(-1, 1); freighter(c, 0, 0, 0.82, '#A8432F'); c.restore();
        if (p > 0.05 && p < 1) { c.strokeStyle = 'rgba(255,255,255,.85)'; c.lineWidth = 3; for (let k = 0; k < 3; k++) { c.beginPath(); c.moveTo(x + 84 + k * 22, wl + 12 + k * 3); c.lineTo(x + 104 + k * 22, wl + 12 + k * 3); c.stroke(); } }
        seaFill(c, pn.bb.x0 - 40, pn.bb.x1 + 40, wl + 14, t, '#6AA9C9', 4, 56);
      },
      labels: [{ t: sc.word('가까운 배'), x: A.x1 - 150, y: A.y0 + 30, c: 'tag', at: T }],
    };
  };

  // ── 07 중고등: 사고가 사람이 아니라 규칙을 바꿨다 — 기운 배 그림 → 화살 → 규칙 책에 도장이 찍힌다
  ART.rulebook = function (sc, pn, A) {
    const T = sc.w('국제 규칙', pn.t0 - 0.2), bk = [A.x1 - 170, A.y0 + 120];
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#EEF2F5', '#DCE5EB'); } },
        { f: 0, paint(g) {
          rr(g, A.x0 + 40, A.y0 + 60, 170, 120, 8); fs(g, '#1D3B55', 3);
          g.save(); g.beginPath(); g.rect(A.x0 + 40, A.y0 + 60, 170, 120); g.clip(); g.translate(A.x0 + 125, A.y0 + 150); g.rotate(0.13); liner(g, 0, 0, 0.42, true); g.restore();
          g.fillStyle = '#123049'; g.fillRect(A.x0 + 43, A.y0 + 152, 164, 25); rr(g, A.x0 + 40, A.y0 + 60, 170, 120, 8); inkS(g, 3);
          rr(g, bk[0] - 104, bk[1] - 74, 208, 150, 6); fs(g, '#FFFDF5', 3.5); g.beginPath(); g.moveTo(bk[0], bk[1] - 74); g.lineTo(bk[0], bk[1] + 76); inkS(g, 2.5);
          for (let r = 0; r < 5; r++) for (const s of [-1, 1]) { g.strokeStyle = 'rgba(14,36,51,.35)'; g.lineWidth = 3; g.beginPath(); g.moveTo(bk[0] + s * 14 + (s < 0 ? -76 : 0), bk[1] - 50 + r * 22); g.lineTo(bk[0] + s * 14 + (s < 0 ? 0 : 76) - (r % 2) * 18, bk[1] - 50 + r * 22); g.stroke(); }
        } },
      ],
      dyn(c, t) {
        const p = smooth((t - pn.t0 - 0.4) / 0.8); if (p > 0) { const x0 = A.x0 + 226, x1 = lerp(x0, bk[0] - 120, p); c.beginPath(); c.moveTo(x0, A.y0 + 120); c.lineTo(x1, A.y0 + 120); c.strokeStyle = COL.ink; c.lineWidth = 9; c.lineCap = 'round'; c.stroke(); if (p > 0.9) { poly(c, [[x1 + 14, A.y0 + 120], [x1 - 4, A.y0 + 106], [x1 - 4, A.y0 + 134]]); fs(c, COL.ink, 0); } }
        const s = t < T ? 0 : outBack(clamp((t - T) / 0.25), 2.2); if (s > 0) { const k = 1.6 - 0.6 * s; c.save(); c.translate(bk[0] + 52, bk[1] + 30); c.rotate(-0.25); c.scale(k, k); c.globalAlpha = clamp(s); circ(c, 0, 0, 30); c.strokeStyle = COL.red; c.lineWidth = 6; c.stroke(); circ(c, 0, 0, 20); c.lineWidth = 3; c.stroke(); c.restore(); c.globalAlpha = 1; }
      },
      labels: [{ t: sc.word('국제 규칙'), x: bk[0], y: A.y1 - 26, c: 'tagt', at: T }],
    };
  };

  // ── 07 자동 장치(item): 요즘 배 갑판의 주황색 장치 — 그 위로 위치 표지가 서고 신호가 '자동으로' 나간다
  ART.device = function (sc, pn, A) {
    const deck = A.y1 - 70, dx = A.cx + 60, T = sc.w('자동으로', pn.t0 - 0.2);
    return {
      layers: [
        { f: 0.12, paint(g) { bg(g, pn, '#D2E9F5', '#F3F9FC'); cloud(g, A.x0 + 100, A.y0 + 40, 0.8); } },
        { f: 0, paint(g) {
          rr(g, pn.bb.x0 - 30, deck, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#5D7A8E', 3);
          for (let x = pn.bb.x0; x < pn.bb.x1; x += 30) { g.beginPath(); g.moveTo(x, deck - 40); g.lineTo(x, deck); inkS(g, 2.5); } g.beginPath(); g.moveTo(pn.bb.x0 - 20, deck - 40); g.lineTo(pn.bb.x1 + 20, deck - 40); inkS(g, 3.5);
          rr(g, dx - 30, deck - 22, 60, 22, 4); fs(g, '#7A8C98', 3); rr(g, dx - 20, deck - 92, 40, 72, 10); fs(g, '#F08A24', 3); rr(g, dx - 20, deck - 60, 40, 10, 0); fs(g, COL.white, 2);
          g.beginPath(); g.moveTo(dx + 8, deck - 92); g.lineTo(dx + 8, deck - 128); inkS(g, 3);
        } },
      ],
      dyn(c, t) {
        if (Math.floor(t * 2.5) % 2) { circ(c, dx - 4, deck - 100, 7); fs(c, COL.red, 2); }
        const k = pop(t, T, 0.35, 2.2); if (k > 0) { const py = deck - 110 - 4 * Math.sin((t - T) * 3); c.save(); c.translate(dx + 100, py); c.scale(k, k); c.beginPath(); c.moveTo(0, 30); c.bezierCurveTo(-26, 2, -22, -26, 0, -26); c.bezierCurveTo(22, -26, 26, 2, 0, 30); c.closePath(); fs(c, COL.red, 3); circ(c, 0, -6, 8); fs(c, COL.white, 0); c.restore(); }
        rings(c, dx + 8, deck - 128, t, T, { a0: -160, a1: -20, r0: 16, r1: 150, col: COL.red, speed: 0.6, n: 3, w: 4, dash: [9, 8] });
      },
      labels: itemTag(sc, pn, A).concat([{ t: sc.word('자동으로'), x: A.x1 - 56, y: A.y0 + 30, c: 'tag', at: T }]),
    };
  };

  // ── 07 도슨트 핵심(기울어진 칸): 사람이 못 보내도 장치가 저절로 — 거친 바다에 기운 배, 갑판 장치의 구조 신호가 칸을 깨고 나간다
  //    중고등은 '1999년'(큰 글)
  ART.beacon = function (sc, pn, A) {
    const wl = A.y1 - 40, sx = A.x0 + 230, dx = A.x1 - 128, dy = wl - 44, mv = sc.moves[pn.i], lw = wordIn(sc, pn, ['저절로']);   // 장치는 물에 반쯤 잠겨 뜬다(배를 떠나 혼자 신호를 낸다)
    const labels = [];
    if (lw) labels.push({ t: sc.word(lw), x: A.x1 - 100, y: A.y0 + 36, c: 'tag', at: sc.w(lw, pn.t0 - 0.2) });
    if (sc.has('1999년') && sayAt(sc, '1999년', pn.t0 - 0.2, pn.t1) != null) labels.push({ t: sc.word('1999년'), x: A.x1 - 120, y: A.y0 + 40, c: 'big', at: sc.w('1999년', pn.t0 - 0.2), rot: -4 });
    return {
      layers: [
        { f: 0.14, paint(g) { bg(g, pn, '#8FA9BA', '#C9D8E1'); cloud(g, A.x0 + 120, pn.bb.y0 + 40, 1.1, 'rgba(110,130,145,.6)'); cloud(g, A.cx + 90, A.y0 + 20, 0.9, 'rgba(110,130,145,.5)'); } },
      ],
      dyn(c, t) {
        const bob = 3 * Math.sin(t * 1.9);
        c.save(); c.translate(sx, wl); c.rotate(-0.12 + 0.04 * Math.sin(t * 1.3)); freighter(c, 0, bob, 1.3, '#2F5D7C'); c.restore();
        // 갑판 장치(뜬 부표형) — 깨고 나가기 전까지 빨간 불이 깜빡이고 고리가 나간다
        rr(c, dx - 18, dy + bob, 36, 60, 10); fs(c, '#F08A24', 3); rr(c, dx - 18, dy + 26 + bob, 36, 9, 0); fs(c, COL.white, 2);
        if (Math.floor(t * 2.5) % 2) { circ(c, dx, dy - 8 + bob, 8); fs(c, COL.red, 2.5); }
        if (t < mv.t0 - 0.35) rings(c, dx, dy - 8 + bob, t, pn.t0 + 0.3, { a0: -160, a1: -20, r0: 16, r1: 120, col: COL.red, speed: 0.7, n: 3, w: 4, dash: [9, 8] });
        seaFill(c, pn.bb.x0 - 40, pn.bb.x1 + 40, wl, t, '#3F7697', 9, 80);
        c.strokeStyle = 'rgba(255,255,255,.55)'; c.lineWidth = 3; for (let k = 0; k < 7; k++) { const xx = A.x0 + 20 + k * 86, yy = wl + 30 + (k % 3) * 22; c.beginPath(); c.moveTo(xx, yy); c.quadraticCurveTo(xx + 14, yy - 8, xx + 28, yy); c.stroke(); }
      },
      labels, from: [dx, dy - 8],
    };
  };

  // ── 07 침묵 칸: 잔잔한 바다의 이웃 배 — 날아온 구조 신호가 돛대 끝에 닿아 멈춘다
  ART.rescueship = function (sc, pn, A) {
    const b = pn.bb, wl = b.y1 - 70, x = b.x0 + 200;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#CFE7F3', '#F4FAFD', b.y0, wl); rr(g, b.x0 - 40, wl - 4, b.x1 - b.x0 + 80, 900, 0); fs(g, '#6FA8C8', 0); } },
        { f: 0, paint(g) { freighter(g, x, wl + 6, 1.15, '#A8432F'); g.strokeStyle = 'rgba(255,255,255,.7)'; g.lineWidth = 3; for (let k = 0; k < 5; k++) { const xx = b.x0 + 20 + k * 70, yy = wl + 30 + (k % 2) * 16; g.beginPath(); g.moveTo(xx, yy); g.lineTo(xx + 24, yy); g.stroke(); } } },
      ],
      to: [x + 40 * 1.15 - 66, wl + 6 - 96 * 1.15 - 10],
    };
  };

  // ── 07 마지막 칸 변형: 두 로봇 사이에 구명 튜브가 둥실 뜬다(로봇 몸 사이 빈자리)
  FINV[4] = function (c, t, A, pn, sc, cx, y) { const yy = y + 40 + 4 * Math.sin(t * 1.8); for (let k = 0; k < 8; k++) { c.beginPath(); c.arc(cx, yy, 20, k * TAU / 8, (k + 1) * TAU / 8); c.strokeStyle = k % 2 ? COL.white : COL.red; c.lineWidth = 10; c.stroke(); } circ(c, cx, yy, 25); inkS(c, 3); circ(c, cx, yy, 15); inkS(c, 3); };

  // ═════════════════════════════════════════════ 14 이동통신 — 차에 싣던 전화 · 작아진 전화 · 세대마다 늘어난 것 · 5세대
  /** 옆에서 본 자동차(앞이 오른쪽, y = 땅). rot = 바퀴 살 각도 */
  function car(c, x, y, s, col, rot) {
    c.save(); c.translate(x, y); c.scale(s, s);
    c.beginPath(); c.moveTo(-72, -14); c.lineTo(-72, -34); c.quadraticCurveTo(-68, -41, -54, -41); c.lineTo(-36, -41); c.lineTo(-20, -63); c.lineTo(28, -63); c.lineTo(46, -41); c.lineTo(66, -39); c.quadraticCurveTo(76, -37, 76, -26); c.lineTo(76, -14); c.closePath(); fs(c, col, 3);
    poly(c, [[-28, -43], [-15, -59], [2, -59], [2, -43]]); fs(c, COL.sig3, 2.5); poly(c, [[8, -43], [8, -59], [25, -59], [39, -43]]); fs(c, COL.sig3, 2.5);
    for (const wx of [-44, 48]) { circ(c, wx, -14, 15); fs(c, COL.ink2, 3); circ(c, wx, -14, 6); fs(c, COL.grey2, 0); c.beginPath(); c.moveTo(wx + Math.cos(rot || 0) * 11, -14 + Math.sin(rot || 0) * 11); c.lineTo(wx - Math.cos(rot || 0) * 11, -14 - Math.sin(rot || 0) * 11); c.strokeStyle = COL.grey2; c.lineWidth = 3; c.stroke(); }
    c.restore();
  }
  /** 전화기 모양 — kind: car(상자 + 꼬인 줄 수화기) · brick(벽돌형, 안테나) · flip(폴더) · smart(스마트폰). y = 바닥 가운데. 화면 사각형을 돌려준다 */
  function handset(c, x, y, s, kind, glow) {
    c.save(); c.translate(x, y); c.scale(s, s);
    let scr = null;
    if (kind === 'car') {
      rr(c, -40, -40, 80, 40, 5); fs(c, '#4B5A64', 3); for (let k = 0; k < 3; k++) { circ(c, -22 + k * 16, -20, 4); fs(c, COL.grey2, 0); }
      c.beginPath(); for (let k = 0; k <= 16; k++) { const u = k / 16; c.lineTo(30 - u * 40 + 6 * Math.sin(u * 30), -40 - u * 30); } c.strokeStyle = COL.ink; c.lineWidth = 2.5; c.stroke();
      c.save(); c.translate(-14, -78); c.rotate(-0.35); rr(c, -34, -8, 68, 16, 8); fs(c, '#3A4750', 3); circ(c, -30, 2, 9); fs(c, '#3A4750', 2.5); circ(c, 30, 2, 9); fs(c, '#3A4750', 2.5); c.restore();
    } else if (kind === 'brick') {
      rr(c, 6, -112, 6, 28, 3); fs(c, COL.ink2, 2); rr(c, -15, -90, 30, 90, 6); fs(c, '#4B5A64', 3); scr = [-10, -80, 20, 14]; rr(c, ...scr, 2); fs(c, glow ? '#B9E4A8' : '#8FA59A', 2);
      for (let r = 0; r < 4; r++) for (let k = 0; k < 3; k++) { rr(c, -10 + k * 7.5, -58 + r * 11, 5, 6, 1.5); fs(c, COL.grey2, 0); }
    } else if (kind === 'flip') {
      c.save(); c.translate(0, -48); c.rotate(-0.12); rr(c, -14, -52, 28, 52, 6); fs(c, '#5F7C93', 3); scr = [-10, -46, 20, 30]; rr(c, ...scr, 3); fs(c, glow ? '#CFEFFF' : '#9DB4C2', 2); c.restore();
      rr(c, -14, -48, 28, 48, 6); fs(c, '#5F7C93', 3); for (let r = 0; r < 3; r++) for (let k = 0; k < 3; k++) { rr(c, -9 + k * 7, -40 + r * 10, 5, 6, 1.5); fs(c, COL.grey2, 0); }
      scr = [-14, -94, 20, 30];          // 기운 윗판의 화면 가운데(≈ −4, −79)를 곧은 사각형으로 어림
    } else {
      rr(c, -21, -86, 42, 86, 9); fs(c, '#22313C', 3); scr = [-17, -80, 34, 70]; rr(c, ...scr, 4); fs(c, glow ? '#CFEFFF' : '#5D7385', 0);
    }
    c.restore();
    return scr && [x + scr[0] * s, y + scr[1] * s, scr[2] * s, scr[3] * s];
  }
  /** 화면 안 그림 — voice(소리 물결) · text(말 상자) · face(얼굴) · voicetext · data(내려받기 화살) */
  function screenIcon(c, r, kind, t) {
    const [x, y, w, h] = r, cx = x + w / 2, cy = y + h / 2, u = Math.min(w, h);
    c.save(); c.beginPath(); c.rect(x, y, w, h); c.clip();
    if (kind === 'voice' || kind === 'voicetext') { for (let k = 0; k < 2; k++) { c.beginPath(); c.arc(cx - u * 0.25, cy, u * (0.18 + 0.16 * k), -0.8, 0.8); c.strokeStyle = COL.ink; c.lineWidth = 2; c.stroke(); } }
    if (kind === 'text' || kind === 'voicetext') { rr(c, cx - u * 0.05, cy - u * 0.32, u * 0.42, u * 0.24, 3); fs(c, COL.white, 1.5); rr(c, cx - u * 0.36, cy + u * 0.06, u * 0.42, u * 0.24, 3); fs(c, COL.amber3, 1.5); }
    if (kind === 'face') { circ(c, cx, cy - h * 0.06, u * 0.26); fs(c, COL.skin, 1.5); for (const s of [-1, 1]) { circ(c, cx + s * u * 0.09, cy - h * 0.08, 1.8); fs(c, COL.ink, 0); } c.beginPath(); c.arc(cx, cy - h * 0.03, u * 0.1, 0.3, Math.PI - 0.3); c.strokeStyle = COL.ink; c.lineWidth = 1.5; c.stroke(); rr(c, cx - u * 0.3, cy + h * 0.2, u * 0.6, h * 0.3, 6); fs(c, COL.teal2, 1.5); }
    if (kind === 'data') { const p = (t * 0.8) % 1; for (let k = 0; k < 3; k++) { const yy = y + h * (0.15 + ((p + k / 3) % 1) * 0.6); poly(c, [[cx - 7, yy], [cx + 7, yy], [cx, yy + 8]]); fs(c, COL.sig, 0); } rr(c, cx - u * 0.32, y + h * 0.8, u * 0.64, 3, 1.5); fs(c, COL.ink, 0); }
    c.restore();
  }

  // ── 14 오프닝(넓은 칸): 선반 위 전화기 넷(차에 싣던 전화 → 벽돌 → 폴더 → 스마트폰) — '발전' 에 불이 차례로, '맨 처음' 에 첫째가 빛난다
  ART.phones = function (sc, pn, A) {
    const shelf = A.y1 - 70, xs = [A.x0 + 110, A.x0 + 250, A.x0 + 370, A.x1 - 110], kinds = ['car', 'brick', 'flip', 'smart'];
    const Tg = sc.w('발전', pn.t0 - 0.2), Tf = sc.w('맨 처음', pn.t0 - 0.2);
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#EDF3F7', '#DCE7EE'); } },
        { f: 0, paint(g) { rr(g, pn.bb.x0 - 30, shelf, pn.bb.x1 - pn.bb.x0 + 60, 18, 0); fs(g, '#A07A4C', 3); rr(g, pn.bb.x0 - 30, shelf + 18, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#E5DCCB', 3);
          g.beginPath(); g.moveTo(A.x0 + 40, shelf + 44); g.lineTo(A.x1 - 50, shelf + 44); inkS(g, 4); poly(g, [[A.x1 - 30, shelf + 44], [A.x1 - 52, shelf + 33], [A.x1 - 52, shelf + 55]]); fs(g, COL.ink, 0); } },
      ],
      dyn(c, t) {
        xs.forEach((x, i) => {
          const on = smooth((t - Tg - i * 0.35) / 0.4);
          c.save(); c.globalAlpha = 0.35 + 0.65 * on; handset(c, x, shelf, i === 0 ? 1.3 : 1.25, kinds[i], on > 0.5); c.restore();
        });
        const k = pop(t, Tf, 0.35, 2); if (k > 0) { c.globalAlpha = 0.5 + 0.4 * Math.sin((t - Tf) * 5) ** 2; circ(c, xs[0], shelf - 64, 70 * Math.min(k, 1.05)); c.strokeStyle = COL.amber2; c.lineWidth = 6; c.stroke(); c.globalAlpha = 1; }
      },
      labels: [{ t: sc.word('이동통신'), x: A.cx, y: A.y0 + 26, c: 'sign', at: sc.w('이동통신') }],
    };
  };

  // ── 14 처음 전화기(item): 들고 다닐 수 없어 자동차에 싣고 다녔다 — 달리는 차 지붕의 안테나, 트렁크엔 전화 상자, 창에는 수화기
  ART.carphone = function (sc, pn, A) {
    const road = A.y1 - 40, cx = A.cx + 30, T = pn.t0 + 0.3;
    return {
      layers: [
        { f: 0.12, paint(g) { bg(g, pn, '#DCEFF8', '#F3F9FC'); cloud(g, A.x1 - 140, A.y0 + 30, 0.8); } },
      ],
      dyn(c, t) {
        // 배경이 뒤로 흐른다(차가 달린다) — 나무·가로등은 위치가 t 의 식
        const off = (t - T) * 120;
        hills(c, pn.bb.x0 - 40, pn.bb.x1, road - 40, 30, '#C7DDB9', 141, road + 10);
        for (let k = 0; k < 6; k++) { const x = ((A.x1 + 60 - k * 130 - off) % 780 + 780) % 780 - 100 + A.x0 - 40; c.fillStyle = '#7E9F74'; c.fillRect(x - 4, road - 60, 8, 40); circ(c, x, road - 70, 22); c.fillStyle = '#9CC28E'; c.fill(); }
        rr(c, pn.bb.x0 - 30, road, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(c, '#8A97A0', 3);
        for (let k = 0; k < 7; k++) { const x = ((k * 110 - off) % 770 + 770) % 770 - 80 + A.x0; rr(c, x, road + 16, 50, 6, 3); c.fillStyle = COL.white; c.fill(); }
        const bob = 1.5 * Math.sin(t * 9);
        c.beginPath(); c.moveTo(cx - 30, road - 63 * 1.6 + bob); c.lineTo(cx - 30, road - 63 * 1.6 - 34 + bob); inkS(c, 3); circ(c, cx - 30, road - 63 * 1.6 - 36 + bob, 4); fs(c, COL.amber2, 2);
        car(c, cx, road + bob, 1.6, '#C9543C', (t - T) * 8);
        rr(c, cx - 40, road - 88 + bob, 30, 18, 3); fs(c, '#4B5A64', 2.5);          // 뒷자리 창에 전화 상자
        c.save(); c.translate(cx + 36, road - 80 + bob); c.rotate(-0.4); rr(c, -16, -5, 32, 10, 5); fs(c, '#3A4750', 2.5); c.restore();   // 앞 창에 수화기
        rings(c, cx - 30, road - 63 * 1.6 - 36 + bob, t, T + 0.3, { a0: -160, a1: -20, r0: 14, r1: 90, n: 3, speed: 0.8, col: COL.sig, w: 3, dash: [7, 7] });
      },
      labels: itemTag(sc, pn, A),
    };
  };

  // ── 14 자동차 한 대보다 비쌌다 — 저울: 전화 상자 쪽이 자동차 쪽보다 아래로 기운다(값의 비유)
  ART.scale = function (sc, pn, A) {
    const px = A.cx - 20, py = A.y0 + 92, L = 170, Tb = sc.w('비쌌', pn.t0 - 0.2), yw = wordIn(sc, pn, ['1984년']);
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#F3EEE4', '#E8DECD'); } },
        { f: 0, paint(g) { rr(g, pn.bb.x0 - 30, A.y1 - 30, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#C8B08A', 3); poly(g, [[px - 46, A.y1 - 30], [px + 46, A.y1 - 30], [px + 10, py + 6], [px - 10, py + 6]]); fs(g, '#8B6B45', 3); } },
      ],
      dyn(c, t) {
        const a = -0.2 * smooth((t - Tb) / 0.7) + 0.03 * Math.sin((t - Tb) * 3) * Math.exp(-Math.max(0, t - Tb - 0.7) * 2) * (t > Tb ? 1 : 0);
        const end = (s) => [px + s * L * Math.cos(a), py + s * L * Math.sin(a)];
        c.beginPath(); c.moveTo(...end(-1)); c.lineTo(...end(1)); inkS(c, 8); c.strokeStyle = '#B88A4E'; c.lineWidth = 4; c.stroke(); circ(c, px, py, 9); fs(c, COL.amber2, 3);
        for (const s of [-1, 1]) {
          const [ex, ey] = end(s), pyy = ey + 62;
          c.beginPath(); c.moveTo(ex, ey); c.lineTo(ex - 40, pyy); c.moveTo(ex, ey); c.lineTo(ex + 40, pyy); c.strokeStyle = COL.ink2; c.lineWidth = 2; c.stroke();
          c.beginPath(); c.moveTo(ex - 52, pyy); c.quadraticCurveTo(ex, pyy + 22, ex + 52, pyy); c.closePath(); fs(c, '#C9D3D9', 3);
          if (s < 0) handset(c, ex, pyy, 0.8, 'car'); else car(c, ex, pyy, 0.5, '#5B8DB0', 0);
        }
      },
      labels: [{ t: sc.word('자동차 한 대'), x: px + L, y: A.y1 - 26, c: 'tagt', at: sc.w('자동차 한 대', pn.t0 - 0.2) }].concat(yw ? [{ t: sc.word(yw), x: A.x0 + 96, y: A.y0 + 36, c: 'big', at: sc.w(yw, pn.t0 - 0.2), rot: -4 }] : []),
    };
  };

  // ── 14 질문 띠 변형: v9 '그 뒤로는?' 벽돌 전화 → 스마트폰 · v10 '5세대는?' 기지국과 막대 다섯이 차오른다
  ASKV[9] = { paint(g, A) { handset(g, A.x0 + 40, A.y1 - 18, 0.9, 'brick'); g.beginPath(); g.moveTo(A.x0 + 70, A.y1 - 60); g.lineTo(A.x0 + 108, A.y1 - 60); inkS(g, 5); poly(g, [[A.x0 + 120, A.y1 - 60], [A.x0 + 104, A.y1 - 70], [A.x0 + 104, A.y1 - 50]]); fs(g, COL.ink, 0); handset(g, A.x0 + 150, A.y1 - 18, 0.9, 'smart', true); } };
  ASKV[10] = {
    paint(g, A) { lattice(g, A.x0 + 50, A.y1 - 12, 110, 46); },
    dyn(c, t, A, pn) { const n = 1 + Math.floor(((t - pn.t0) * 2.2) % 5); for (let k = 0; k < 5; k++) { rr(c, A.x0 + 96 + k * 16, A.y1 - 22 - (k + 1) * 14, 11, (k + 1) * 14, 2); fs(c, k < n ? COL.sig2 : COL.grey2, 2); } },
  };

  // ── 14 초등: 점점 작아져서 손에 들고 — 손 위의 전화가 벽돌만 하다가 작아지고, 지나간 크기는 점선 테두리로 남는다
  ART.shrink = function (sc, pn, A) {
    const hx = A.cx - 30, hy = A.y1 - 30, T = pn.t0 + 0.3, D = Math.max(1.2, pn.t1 - pn.t0 - 0.8), lw = wordIn(sc, pn, ['손에 들고']);
    const sizes = [[64, 170], [44, 120], [40, 96]];
    return {
      layers: [{ f: 0.1, paint(g) { bg(g, pn, '#EEF6FA', '#DCEBF3'); } }],
      dyn(c, t) {
        const p = smooth((t - T) / D), k = p * (sizes.length - 1), i = Math.min(sizes.length - 2, Math.floor(k)), f = k - i;
        const w = lerp(sizes[i][0], sizes[i + 1][0], f), h = lerp(sizes[i][1], sizes[i + 1][1], f);
        for (let j = 0; j <= Math.min(sizes.length - 1, Math.floor(k + 1e-6)); j++) { if (j === sizes.length - 1 && p < 1) continue; const [sw, sh] = sizes[j]; c.setLineDash([6, 6]); rr(c, hx - sw / 2 + 60 + j * 0, hy - 40 - sh, sw, sh, 8); c.strokeStyle = 'rgba(14,36,51,.35)'; c.lineWidth = 2.5; c.stroke(); c.setLineDash([]); }
        rr(c, hx - w / 2, hy - 40 - h, w, h, lerp(6, 10, p)); fs(c, lerp(0, 1, p) > 0.6 ? '#22313C' : '#4B5A64', 3); rr(c, hx - w / 2 + 5, hy - 34 - h, w - 10, lerp(18, h - 12, p), 4); fs(c, '#CFEFFF', 0);
        if (p < 0.5) { rr(c, hx + w / 2 - 14, hy - 40 - h - 26, 6, 28, 3); fs(c, COL.ink2, 2); }
        // 손(아래에서 감싼다)
        c.beginPath(); c.moveTo(hx - 70, A.y1 + 40); c.quadraticCurveTo(hx - 66, hy - 10, hx - w / 2 - 6, hy - 52); c.lineTo(hx + w / 2 + 6, hy - 52); c.quadraticCurveTo(hx + 66, hy - 6, hx + 70, A.y1 + 40); c.closePath(); fs(c, COL.skin, 3);
        for (let j = 0; j < 3; j++) { rr(c, hx + w / 2 - 2, hy - 92 + j * 16, 20, 13, 6); fs(c, COL.skin, 2.5); }
      },
      labels: itemTag(sc, pn, A).concat(lw ? [{ t: sc.word(lw), x: A.x1 - 110, y: A.y0 + 40, c: 'tagt', at: sc.w(lw, pn.t0 - 0.2) }] : []),
    };
  };

  // ── 14 세대마다 늘어난 것: 전화 셋 — 화면에 소리 물결 → 말 상자 → 얼굴(중고등: 음성·문자 → 영상통화 → 데이터). 이름표는 카드 visual.steps 의 k 그대로
  ART.gens = function (sc, pn, A) {
    const steps = ((sc.visual && sc.visual.steps) || []).filter((s) => sayAt(sc, s.k, pn.t0 - 0.2, pn.t1 + 0.05) != null).slice(0, 3);
    const elem = sc.level === '초등', kinds = elem ? ['brick', 'flip', 'smart'] : ['flip', 'flip', 'smart'], icons = elem ? ['voice', 'text', 'face'] : ['voicetext', 'face', 'data'];
    const base = A.y1 - 44, xs = [A.x0 + 110, A.cx, A.x1 - 110], T = steps.map((s) => sc.w(s.k, pn.t0 - 0.2));   // 이름표는 전화 아래(위 왼쪽은 카드 꼬리표 자리)
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#F2F7FA', '#E2EEF4'); } },
        { f: 0, paint(g) { for (const x of xs) { g.beginPath(); g.ellipse(x, base + 2, 60, 10, 0, 0, TAU); fs(g, 'rgba(14,36,51,.1)', 0); } for (let k = 0; k < 2; k++) { const x = (xs[k] + xs[k + 1]) / 2; g.beginPath(); g.moveTo(x - 18, base - 70); g.lineTo(x + 12, base - 70); inkS(g, 4); poly(g, [[x + 22, base - 70], [x + 8, base - 79], [x + 8, base - 61]]); fs(g, COL.ink, 0); } } },
      ],
      dyn(c, t) {
        steps.forEach((s, i) => {
          const on = t >= T[i], k = on ? pop(t, T[i], 0.3, 1.8) : 0, sc2 = kinds[i] === 'smart' ? 1.6 : kinds[i] === 'flip' ? 1.5 : 1.4;
          c.save(); c.globalAlpha = on ? 1 : 0.4; const r = handset(c, xs[i], base, sc2, kinds[i], on); c.restore();
          if (on && r) { c.save(); c.translate(r[0] + r[2] / 2, r[1] + r[3] / 2); c.scale(k, k); c.translate(-(r[0] + r[2] / 2), -(r[1] + r[3] / 2)); screenIcon(c, r, icons[i], t); c.restore(); }
        });
      },
      labels: itemTag(sc, pn, A).concat(steps.map((s, i) => ({ t: s.k, x: xs[i], y: A.y1 - 18, c: i % 2 ? 'tagt' : 'tag', at: T[i] }))),
    };
  };

  // ── 14 중고등: 국내 기준 1996년과 2011년 — 시간 띠 위에 깃발 둘(폴더 · 스마트폰)
  ART.years = function (sc, pn, A) {
    const y = A.y1 - 70, x0 = A.x0 + 40, x1 = A.x1 - 30, f1 = A.x0 + 200, f2 = A.x1 - 170, T1 = sc.w('1996년', pn.t0 - 0.2), T2 = sc.w('2011년', pn.t0 - 0.2);
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#EEF4F8', '#DCE8F0'); } },
        { f: 0, paint(g) { rr(g, x0, y - 10, x1 - x0, 20, 10); fs(g, COL.sig3, 3); poly(g, [[x1 + 22, y], [x1 - 2, y - 20], [x1 - 2, y + 20]]); fs(g, COL.sig, 3); } },
      ],
      dyn(c, t) {
        for (const [x, T, kind] of [[f1, T1, 'flip'], [f2, T2, 'smart']]) {
          const k = pop(t, T, 0.35, 2); if (k <= 0) continue;
          c.beginPath(); c.moveTo(x, y); c.lineTo(x, y - 90 * k); inkS(c, 4); circ(c, x, y, 9); fs(c, COL.amber2, 3);
          c.save(); c.translate(x + 50, y - 10); c.scale(k, k); handset(c, 0, 0, 1.15, kind, true); c.restore();
        }
      },
      labels: [{ t: sc.word('1996년'), x: f1, y: A.y0 + 40, c: 'tag', at: T1 }, { t: sc.word('2011년'), x: f2, y: A.y0 + 40, c: 'tagt', at: T2 }, { t: sc.word('국내 기준'), x: A.cx, y: A.y1 - 22, c: 'tag', at: sc.w('국내 기준', pn.t0 - 0.2) }],
    };
  };

  // ── 14 도슨트 핵심(기울어진 칸): 5세대 — 기지국 하나에 전화·노트북·자동차·집·시계가 함께 이어지고, 영상 한 장이 칸을 깨고 나간다
  ART.many5g = function (sc, pn, A) {
    const tx = A.x0 + 130, base = A.y1 - 16, top = base - 196, mv = sc.moves[pn.i], mw = wordIn(sc, pn, ['많은 기기', '많이']), Tm = mw ? sc.w(mw, pn.t0 - 0.2) : pn.t0 + 0.6, yw = wordIn(sc, pn, ['2019년']);
    const devs = [['smart', A.x0 + 300, A.y0 + 120], ['laptop', A.x0 + 430, A.y0 + 150], ['house', A.x1 - 70, A.y0 + 220], ['car', A.x0 + 400, A.y0 + 280], ['watch', A.x0 + 262, A.y0 + 236], ['smart', A.x1 - 80, A.y0 + 96]];
    const labels = itemTag(sc, pn, A);
    if (yw) labels.push({ t: sc.word(yw), x: A.cx + 60, y: A.y0 + 36, c: 'big', at: sc.w(yw, pn.t0 - 0.2), rot: -4 });
    return {
      layers: [
        { f: 0.12, paint(g) { bg(g, pn, '#E3F0F8', '#F6FAFC'); } },
        { f: 0, paint(g) { rr(g, pn.bb.x0 - 30, base, 300, 600, 0); fs(g, '#C9D9E2', 3); lattice(g, tx, base, 196, 70); for (const s of [-1, 1]) { rr(g, tx + s * 18 - 5, top + 16, 10, 30, 3); fs(g, COL.white, 2.5); } } },
      ],
      dyn(c, t) {
        devs.forEach(([kind, x, y], i) => {
          const on = smooth((t - Tm - i * 0.18) / 0.35);
          if (on > 0) {   // 이은 줄 위로 데이터 점이 오간다
            c.save(); c.globalAlpha = on; c.setLineDash([6, 8]); c.beginPath(); c.moveTo(tx, top - 4); c.lineTo(x, y - 20); c.strokeStyle = COL.sig; c.lineWidth = 3; c.stroke(); c.setLineDash([]);
            const u = ((t * 0.9 + i * 0.37) % 1 + 1) % 1; circ(c, lerp(tx, x, u), lerp(top - 4, y - 20, u), 5); fs(c, COL.amber2, 2); c.restore();
          }
          c.save(); c.globalAlpha = 0.45 + 0.55 * on;
          if (kind === 'smart') handset(c, x, y + 20, 0.6, 'smart', on > 0.5);
          else if (kind === 'laptop') { rr(c, x - 30, y - 20, 60, 38, 4); fs(c, '#22313C', 3); rr(c, x - 25, y - 15, 50, 28, 2); fs(c, on > 0.5 ? '#CFEFFF' : '#5D7385', 0); poly(c, [[x - 40, y + 18], [x + 40, y + 18], [x + 34, y + 26], [x - 34, y + 26]]); fs(c, COL.grey, 3); }
          else if (kind === 'house') house(c, x, y + 20, 0.62, COL.amber3, COL.teal);
          else if (kind === 'car') car(c, x, y + 20, 0.55, '#5B8DB0', 0);
          else { rr(c, x - 6, y - 26, 12, 52, 4); fs(c, '#7A8C98', 2); rr(c, x - 14, y - 14, 28, 28, 7); fs(c, '#22313C', 3); rr(c, x - 10, y - 10, 20, 20, 4); fs(c, on > 0.5 ? '#CFEFFF' : '#5D7385', 0); }
          c.restore();
        });
        if (t < mv.t0 - 0.35) rings(c, tx, top - 6, t, pn.t0 + 0.3, { a0: -170, a1: -10, r0: 16, r1: 80, n: 3, speed: 0.8, col: COL.sig2, w: 3 });
      },
      labels, from: [tx + 46, top - 30],
    };
  };

  // ── 14 침묵 칸: 손 안의 스마트폰 — 날아온 영상이 화면에 들어가 멈춘다(끊기지 않는 영상)
  ART.phone = function (sc, pn, A) {
    const b = pn.bb, cx = (b.x0 + b.x1) / 2, sy = b.y0 + 34, w = 128, h = 236;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#E8F1F7', '#D3E3EE'); } },
        { f: 0, paint(g) {
          rr(g, cx - w / 2, sy, w, h, 16); fs(g, '#22313C', 3.5); rr(g, cx - w / 2 + 8, sy + 16, w - 16, h - 40, 6); fs(g, '#5D7385', 0); rr(g, cx - 14, sy + h - 16, 28, 5, 2.5); fs(g, COL.grey, 0);
          g.beginPath(); g.moveTo(cx - 96, b.y1 + 40); g.quadraticCurveTo(cx - 92, sy + h - 30, cx - w / 2 - 6, sy + h - 60); g.lineTo(cx + w / 2 + 6, sy + h - 60); g.quadraticCurveTo(cx + 92, sy + h - 26, cx + 96, b.y1 + 40); g.closePath(); fs(g, COL.skin, 3);
          for (let j = 0; j < 3; j++) { rr(g, cx + w / 2 - 4, sy + 92 + j * 22, 24, 17, 8); fs(g, COL.skin, 2.5); }
        } },
      ],
      to: [cx, sy + 16 + (h - 40) / 2],
    };
  };

  // ── 14 마지막 칸 변형: 로봇 위로 전화기 넷이 차례로 반짝인다
  FINV[5] = function (c, t, A) { const y = A.y0 + 112, xs = [SW / 2 - 165, SW / 2 - 55, SW / 2 + 55, SW / 2 + 165], kinds = ['car', 'brick', 'flip', 'smart']; xs.forEach((x, i) => { const on = 0.5 + 0.5 * Math.sin(t * 2 - i * 0.9); c.save(); c.globalAlpha = 0.45 + 0.4 * on; handset(c, x, y, 0.62, kinds[i], on > 0.7); c.restore(); }); };

  // ═════════════════════════════════════════════ 17 원격 무선조종 차량 — 행성 탐사 · 멀면 늦게 닿는 말 · 가까운 달
  /** 천체 원판 — earth(파랑·초록) · moon(회색·구덩이) · mars(주황) */
  function orb(c, x, y, r, kind) {
    const col = kind === 'earth' ? '#4F9EC4' : kind === 'moon' ? '#C9CED2' : '#D2743F';
    circ(c, x, y, r); fs(c, col, Math.max(2, r / 14));
    c.save(); circ(c, x, y, r); c.clip();
    if (kind === 'earth') for (const [dx, dy, rr2] of [[-0.35, -0.3, 0.32], [0.2, -0.5, 0.2], [0.3, 0.25, 0.28]]) { circ(c, x + dx * r, y + dy * r, rr2 * r); c.fillStyle = '#8DB27F'; c.fill(); }
    else for (const [dx, dy, rr2] of [[-0.3, -0.2, 0.18], [0.25, 0.3, 0.14], [0.35, -0.35, 0.1], [-0.15, 0.45, 0.1]]) { circ(c, x + dx * r, y + dy * r, rr2 * r); c.fillStyle = kind === 'moon' ? '#A9B0B6' : '#B65E30'; c.fill(); }
    c.restore(); circ(c, x, y, r); inkS(c, Math.max(2, r / 14));
  }
  /** 탐사차 — mars(바퀴 여섯 · 기둥 카메라) · luna(바퀴 여덟 통 모양, 덮개 열림 · 안테나) · lrv(바퀴 넷 열린 차 · 접시 안테나 · 우주비행사). y = 땅 */
  function rover(c, x, y, s, kind, spin) {
    c.save(); c.translate(x, y); c.scale(s, s);
    const wheel = (wx, r) => { circ(c, wx, -r, r); fs(c, COL.ink2, 2.5); c.beginPath(); c.moveTo(wx + Math.cos(spin || 0) * r * 0.7, -r + Math.sin(spin || 0) * r * 0.7); c.lineTo(wx - Math.cos(spin || 0) * r * 0.7, -r - Math.sin(spin || 0) * r * 0.7); c.strokeStyle = COL.grey2; c.lineWidth = 2; c.stroke(); };
    if (kind === 'mars') {
      c.beginPath(); c.moveTo(-40, -16); c.lineTo(-26, -30); c.lineTo(26, -30); c.lineTo(40, -16); inkS(c, 3);
      rr(c, -34, -46, 68, 18, 3); fs(c, '#E8E3D8', 3); rr(c, -38, -50, 76, 6, 2); fs(c, COL.sig, 2);
      c.beginPath(); c.moveTo(22, -50); c.lineTo(22, -78); inkS(c, 3); rr(c, 14, -88, 18, 11, 2); fs(c, '#E8E3D8', 2.5);
      for (const wx of [-36, 0, 36]) wheel(wx, 9);
    } else if (kind === 'luna') {
      for (const wx of [-36, -12, 12, 36]) wheel(wx, 9);
      c.beginPath(); c.moveTo(-44, -36); c.quadraticCurveTo(-40, -16, -30, -16); c.lineTo(30, -16); c.quadraticCurveTo(40, -16, 44, -36); c.closePath(); fs(c, '#B9C0C6', 3);
      c.save(); c.translate(-40, -38); c.rotate(-0.6); rr(c, 0, -5, 84, 8, 2); fs(c, COL.sig, 2.5); c.restore();
      rr(c, -46, -42, 92, 7, 3); fs(c, '#8E979E', 2.5); c.beginPath(); c.moveTo(30, -42); c.lineTo(42, -78); inkS(c, 2.5); circ(c, 42, -80, 3); fs(c, COL.amber2, 1.5);
    } else {
      c.beginPath(); c.moveTo(-44, -20); c.lineTo(44, -20); inkS(c, 4); for (const wx of [-34, 34]) wheel(wx, 11);
      rr(c, -24, -38, 14, 18, 2); fs(c, '#D6D2C4', 2); person(c, -6, -20, 0.5, COL.white, { hair: COL.white }); circ(c, -6, -51, 9); fs(c, '#F2F2EE', 2.5); rr(c, -11, -55, 10, 7, 3); fs(c, '#E3B04B', 0);
      c.beginPath(); c.moveTo(30, -20); c.lineTo(30, -46); inkS(c, 2.5); c.beginPath(); c.arc(30, -52, 10, Math.PI * 0.1, Math.PI * 0.9, true); c.closePath(); fs(c, COL.grey2, 2);
    }
    c.restore();
  }
  /** 명령 꼬투리(작은 캡슐에 ›› 표) — 늦게 닿는 '말' 을 보여 줄 때 */
  function cmdPill(c, x, y, s, col) { c.save(); c.translate(x, y); c.scale(s, s); rr(c, -22, -12, 44, 24, 12); fs(c, col || COL.amber2, 3); for (const dx of [-8, 4]) { c.beginPath(); c.moveTo(dx - 3, -6); c.lineTo(dx + 4, 0); c.lineTo(dx - 3, 6); c.strokeStyle = COL.white; c.lineWidth = 3; c.lineCap = 'round'; c.stroke(); } c.restore(); }

  // ── 17 오프닝(넓은 칸): 붉은 행성 위를 천천히 가는 탐사차 — 이름표 '행성 탐사'
  ART.planet = function (sc, pn, A) {
    const ground = A.y1 - 60, T = pn.t0 + 0.4;
    return {
      layers: [
        { f: 0.14, paint(g) { bg(g, pn, '#E9B79A', '#F6DCC8'); circ(g, A.x1 - 90, A.y0 + 40, 18); fs(g, '#FFF2DA', 0); } },
        { f: 0.06, paint(g) { hills(g, pn.bb.x0 - 40, pn.bb.x1, ground - 30, 50, '#C8794C', 171, ground + 40); } },
        { f: 0, paint(g) { rr(g, pn.bb.x0 - 30, ground, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#D98B5C', 3); for (const [x, y, r] of [[A.x0 + 80, ground + 30, 18], [A.x1 - 120, ground + 44, 26], [A.cx + 30, ground + 60, 12]]) { g.beginPath(); g.ellipse(x, y, r * 1.6, r * 0.5, 0, 0, TAU); fs(g, '#B8683D', 2.5); } } },
      ],
      dyn(c, t) {
        const x = A.x0 + 120 + 22 * Math.max(0, t - T);
        rover(c, Math.min(x, A.x1 - 80), ground + 6, 1.5, 'mars', (t - T) * 3);
        for (let k = 0; k < 3; k++) { const u = ((t * 1.2 + k / 3) % 1 + 1) % 1; c.globalAlpha = 0.5 * (1 - u); circ(c, Math.min(x, A.x1 - 80) - 60 - u * 30, ground - 4 - u * 10, 6 + u * 8); c.fillStyle = '#E8B08C'; c.fill(); } c.globalAlpha = 1;
      },
      labels: [{ t: sc.word('행성 탐사'), x: A.cx, y: A.y0 + 26, c: 'sign', at: sc.w('행성 탐사') }],
    };
  };

  // ── 17 멀리 있는 차를 전파로 움직여 본다(item): 아이가 조종기를 들고, 화면 속 행성 위 탐사차가 움직인다
  ART.remote = function (sc, pn, A) {
    const px = A.x0 + 110, base = A.y1 + 4, scr = [A.cx - 30, A.y0 + 20, 300, 170], lw = wordIn(sc, pn, ['증강현실', '전파']), T = pn.t0 + 0.4;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#E6EEF4', '#D3E0EA'); } },
        { f: 0, paint(g) {
          rr(g, scr[0] - 10, scr[1] - 10, scr[2] + 20, scr[3] + 20, 10); fs(g, '#22313C', 3.5);
          g.save(); rr(g, scr[0], scr[1], scr[2], scr[3], 4); g.clip(); g.fillStyle = '#F2CDB4'; g.fillRect(scr[0], scr[1], scr[2], scr[3]); hills(g, scr[0] - 20, scr[0] + scr[2], scr[1] + 110, 30, '#C8794C', 177, scr[1] + 200); g.fillStyle = '#D98B5C'; g.fillRect(scr[0], scr[1] + 118, scr[2], 60); g.restore();
          rr(g, scr[0] + scr[2] / 2 - 30, scr[1] + scr[3] + 10, 60, 30, 0); fs(g, '#5C6B75', 3);
          person(g, px, base, 1.5, COL.amber2, { hair: '#6B4A33' });
        } },
      ],
      dyn(c, t) {
        // 조종기(손 앞) — 막대가 기울면 화면 속 차가 그쪽으로
        const tilt = 0.35 * Math.sin((t - T) * 1.6), hx = px + 40, hy = base - 70;
        rr(c, hx - 28, hy - 14, 56, 28, 8); fs(c, '#4B5A64', 3); c.beginPath(); c.moveTo(hx, hy - 14); c.lineTo(hx + 20 * Math.sin(tilt), hy - 40); inkS(c, 4); circ(c, hx + 20 * Math.sin(tilt), hy - 42, 6); fs(c, COL.red, 2);
        for (const s of [-1, 1]) { circ(c, hx + s * 30, hy + 4, 9); fs(c, COL.skin, 2.5); }
        c.beginPath(); c.moveTo(hx + 22, hy - 14); c.lineTo(hx + 22, hy - 40); inkS(c, 2.5);
        rings(c, hx + 22, hy - 42, t, T, { a0: -60, a1: 0, r0: 12, r1: 70, n: 3, speed: 0.9, col: COL.sig, w: 3, dash: [6, 6] });
        c.save(); rr(c, scr[0], scr[1], scr[2], scr[3], 4); c.clip();
        const rx = scr[0] + scr[2] / 2 + 80 * Math.sin((t - T) * 0.8 - 0.3); rover(c, rx, scr[1] + 142, 1.1, 'mars', (t - T) * 4); c.restore();
      },
      labels: itemTag(sc, pn, A).concat(lw ? [{ t: sc.word(lw), x: scr[0] + scr[2] - 60, y: scr[1] + 26, c: 'tagt', at: sc.w(lw, pn.t0 - 0.2) }] : []),
    };
  };

  // ── 17 다른 천체 위를 직접 몰아 보는 기분 — 구덩이 밭을 달리는 탐사차(땅이 뒤로 흐른다), 흙먼지
  ART.drive = function (sc, pn, A) {
    const ground = A.y1 - 50, T = pn.t0 + 0.2, rx = A.cx - 20;
    return {
      layers: [
        { f: 0.14, paint(g) { bg(g, pn, '#1A2638', '#3A4A5E'); for (let k = 0; k < 24; k++) { const r = rand(1700 + k); circ(g, pn.bb.x0 + r() * (pn.bb.x1 - pn.bb.x0), pn.bb.y0 - 300 + r() * (ground - pn.bb.y0 + 280), 1 + r() * 1.6); g.fillStyle = 'rgba(255,255,255,.75)'; g.fill(); } orb(g, A.x1 - 100, A.y0 + 50, 26, 'earth'); } },
      ],
      dyn(c, t) {
        const off = (t - T) * 90;
        rr(c, pn.bb.x0 - 30, ground, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(c, '#B9BFC4', 3);
        for (let k = 0; k < 6; k++) { const x = ((k * 140 - off) % 840 + 840) % 840 - 120 + A.x0, w = 30 + (k % 3) * 16; c.beginPath(); c.ellipse(x, ground + 26 + (k % 2) * 22, w, w * 0.28, 0, 0, TAU); fs(c, '#9AA2A8', 2.5); }
        const bump = 3 * Math.abs(Math.sin((t - T) * 5));
        rover(c, rx, ground + 4 - bump, 1.9, 'mars', (t - T) * 5);
        for (let k = 0; k < 4; k++) { const u = ((t * 1.5 + k / 4) % 1 + 1) % 1; c.globalAlpha = 0.6 * (1 - u); circ(c, rx - 76 - u * 60, ground - 6 - u * 16, 7 + u * 10); c.fillStyle = '#D5D9DC'; c.fill(); } c.globalAlpha = 1;
      },
    };
  };

  // ── 17 질문 띠 변형: v11 '지구에서 실시간으로?' 지구 → 점선 → 탐사차 · v12 '달에서는?' 초승달
  ASKV[11] = { dyn(c, t, A) { orb(c, A.x0 + 34, A.y1 - 60, 24, 'earth'); c.setLineDash([6, 7]); c.lineDashOffset = -t * 20; c.beginPath(); c.moveTo(A.x0 + 64, A.y1 - 60); c.lineTo(A.x0 + 130, A.y1 - 48); c.strokeStyle = COL.ink2; c.lineWidth = 3; c.stroke(); c.setLineDash([]); rover(c, A.x0 + 160, A.y1 - 22, 0.8, 'mars', t * 2); } };
  ASKV[12] = { paint(g, A) { const x = A.x0 + 70, y = A.y1 - 64; circ(g, x, y, 38); fs(g, '#F3E7B8', 3); g.save(); circ(g, x + 18, y - 10, 34); g.fillStyle = '#D6EDF2'; g.fill(); g.restore(); circ(g, x + 18, y - 10, 34); g.strokeStyle = 'rgba(14,36,51,.15)'; g.lineWidth = 2; g.stroke(); } };

  // ── 17 너무 멀면 말이 늦게 닿는다(초등 item / 중고등 '빛의 속도인데도 느려요') — 지구에서 떠난 명령이 먼 화성까지 긴 점선을 기어간다, 모래시계
  ART.delay = function (sc, pn, A) {
    const ey = A.y0 + 140, ex = A.x0 + 40, mx = A.x1 - 50, T = pn.t0 + 0.3, D = Math.max(2, pn.t1 - pn.t0 - 0.4), lw = wordIn(sc, pn, ['한참', '빛의 속도']);
    const stars = (() => { const r = rand(1717), out = []; for (let k = 0; k < 26; k++) out.push([pn.bb.x0 + r() * (pn.bb.x1 - pn.bb.x0), pn.bb.y0 - 300 + r() * (pn.bb.y1 - pn.bb.y0 + 600), 1 + 1.6 * r()]); return out; })();
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#0F2132', '#1E3449'); for (const [x, y, r] of stars) { circ(g, x, y, r); g.fillStyle = 'rgba(255,255,255,.7)'; g.fill(); } } },
        { f: 0, paint(g) { orb(g, ex, ey, 56, 'earth'); orb(g, mx, ey, 22, 'mars'); g.setLineDash([4, 10]); g.beginPath(); g.moveTo(ex + 62, ey); g.lineTo(mx - 28, ey); g.strokeStyle = 'rgba(255,255,255,.45)'; g.lineWidth = 3; g.stroke(); g.setLineDash([]); } },
      ],
      dyn(c, t) {
        const p = clamp((t - T) / D), x = lerp(ex + 80, mx - 44, p);
        if (t >= T) cmdPill(c, x, ey, 1, COL.amber2);
        // 모래시계: 위가 비고 아래가 찬다(같은 진행도)
        const hx = A.cx + 10, hy = A.y0 + 54;
        c.beginPath(); c.moveTo(hx - 20, hy - 30); c.lineTo(hx + 20, hy - 30); c.lineTo(hx + 3, hy); c.lineTo(hx + 20, hy + 30); c.lineTo(hx - 20, hy + 30); c.lineTo(hx - 3, hy); c.closePath(); fs(c, 'rgba(255,255,255,.85)', 3);
        poly(c, [[hx - 20 + 17 * p, hy - 30 + 30 * p], [hx + 20 - 17 * p, hy - 30 + 30 * p], [hx + 3, hy], [hx - 3, hy]]); fs(c, COL.amber2, 0);
        poly(c, [[hx - 20, hy + 30], [hx + 20, hy + 30], [hx + 20 - 17 * (1 - p), hy + 30 - 28 * p], [hx - 20 + 17 * (1 - p), hy + 30 - 28 * p]]); fs(c, COL.amber2, 0);
        rr(c, hx - 26, hy - 36, 52, 6, 3); fs(c, '#8B6B45', 2); rr(c, hx - 26, hy + 30, 52, 6, 3); fs(c, '#8B6B45', 2);
      },
      labels: itemTag(sc, pn, A).concat(lw ? [{ t: sc.word(lw), x: A.x1 - 100, y: A.y0 + 40, c: 'tag', at: sc.w(lw, pn.t0 - 0.2) }] : []),
    };
  };

  // ── 17 초등: 그래서 차가 스스로 조심하며 — 바위 앞에서 멈춰 둘러보고(감지 부채꼴), 비켜 돌아간다
  ART.careful = function (sc, pn, A) {
    const ground = A.y1 - 44, rock = [A.cx + 90, ground], T = pn.t0 + 0.2, D = Math.max(2.4, pn.t1 - pn.t0), Ts = sc.w('스스로', pn.t0 - 0.2);
    return {
      layers: [
        { f: 0.12, paint(g) { bg(g, pn, '#E9B79A', '#F6DCC8'); hills(g, pn.bb.x0 - 40, pn.bb.x1, ground - 40, 30, '#D18A5E', 179, ground); } },
        { f: 0, paint(g) { rr(g, pn.bb.x0 - 30, ground, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#D98B5C', 3); g.beginPath(); g.moveTo(rock[0] - 50, ground + 2); g.quadraticCurveTo(rock[0] - 40, ground - 70, rock[0], ground - 74); g.quadraticCurveTo(rock[0] + 46, ground - 66, rock[0] + 54, ground + 2); g.closePath(); fs(g, '#9C5A36', 3); } },
      ],
      dyn(c, t) {
        // 단계: 다가감(0~0.35) → 멈춰 둘러봄(0.35~0.65) → 뒤로 조금 물러나 위쪽 길로 비켜 감(0.65~1) — 모두 진행도 u 의 식
        const u = clamp((t - T) / D), stopX = rock[0] - 150;
        let x, y = ground + 4, scan = 0;
        if (u < 0.35) x = lerp(A.x0 + 40, stopX, smooth(u / 0.35));
        else if (u < 0.65) { x = stopX; scan = (u - 0.35) / 0.3; }
        else { const v = smooth((u - 0.65) / 0.35); x = lerp(stopX, rock[0] + 150, v); y = ground + 4 - 26 * Math.sin(Math.PI * v); }
        if (scan > 0 && scan < 1) { const a = -0.5 + Math.sin(scan * TAU) * 0.35; c.save(); c.globalAlpha = 0.35; c.beginPath(); c.moveTo(x + 30, y - 72); c.arc(x + 30, y - 72, 150, a - 0.28, a + 0.28); c.closePath(); c.fillStyle = COL.amber3; c.fill(); c.restore();
          c.save(); c.translate(x + 30, y - 120); rr(c, -5, -24, 10, 18, 4); fs(c, COL.red, 2); circ(c, 0, 2, 5); fs(c, COL.red, 2); c.restore(); }
        rover(c, x, y, 1.45, 'mars', x * 0.08);
      },
      labels: [{ t: sc.word('스스로'), x: A.x0 + 70, y: A.y0 + 30, c: 'tagt', at: Ts }],
    };
  };

  // ── 17 가까운 달 · 먼 화성: 두 줄 — 지구↔달은 신호가 금방 오가고, 지구→화성은 신호가 한참 기어간다. 이름표는 카드 visual.facts 그대로
  ART.moonmars = function (sc, pn, A) {
    const F = (sc.visual && sc.visual.facts) || [], fMoon = F.find((f) => (f.big + f.label).indexOf('달') >= 0), fMars = F.find((f) => f !== fMoon);
    const y1 = A.y0 + 76, y2 = A.y0 + 186, ex = A.x0 + 46, moonX = A.x0 + 200, marsX = A.x1 - 254;
    const Tmoon = firstAt(sc, ['2초에서 3초', '금방', '달은'], pn.t0 - 0.2, pn.t1) ?? pn.t0 + 0.3, Tmars = firstAt(sc, ['몇 분', '화성'], pn.t0 - 0.2, pn.t1) ?? pn.t0 + 0.3;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#132C40', '#21405A'); for (let k = 0; k < 20; k++) { const r = rand(1777 + k); circ(g, pn.bb.x0 + r() * (pn.bb.x1 - pn.bb.x0), pn.bb.y0 - 200 + r() * (pn.bb.y1 - pn.bb.y0 + 400), 1 + r()); g.fillStyle = 'rgba(255,255,255,.6)'; g.fill(); } } },
        { f: 0, paint(g) {
          for (const [y, x2, kind, r] of [[y1, moonX, 'moon', 16], [y2, marsX, 'mars', 20]]) { orb(g, ex, y, 26, 'earth'); orb(g, x2, y, r, kind); g.setLineDash([4, 9]); g.beginPath(); g.moveTo(ex + 30, y); g.lineTo(x2 - r - 4, y); g.strokeStyle = 'rgba(255,255,255,.45)'; g.lineWidth = 3; g.stroke(); g.setLineDash([]); }
        } },
      ],
      dyn(c, t) {
        if (t >= Tmoon) { const u = ((t - Tmoon) / 1.4) % 1, back = u > 0.5, v = back ? 2 - 2 * u : 2 * u; circ(c, lerp(ex + 32, moonX - 20, v), y1, 7); fs(c, back ? COL.teal2 : COL.amber2, 2.5); }
        if (t >= Tmars) { const v = ((t - Tmars) / 9) % 1; cmdPill(c, lerp(ex + 50, marsX - 40, v), y2, 0.7, COL.amber2); }
      },
      labels: [fMoon, fMars].filter(Boolean).map((f, i) => ({ t: f.big, sub: f.label, x: A.x1 - 112, y: i ? y2 : y1, c: 'fact', at: i ? Tmars : Tmoon, rot: i ? 1 : -1 })),
    };
  };

  // ── 17 중고등: 달은 왕복 2초에서 3초 수준 — 가까운 달까지 신호가 금방 갔다 오고, 초시계가 조금만 돈다
  ART.moonnear = function (sc, pn, A) {
    const y = A.y0 + 120, ex = A.x0 + 100, mx = A.x1 - 160, T = pn.t0 + 0.3, sw = [A.x1 - 60, A.y0 + 56];
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#132C40', '#21405A'); } },
        { f: 0, paint(g) { orb(g, ex, y, 60, 'earth'); orb(g, mx, y, 30, 'moon'); circ(g, sw[0], sw[1], 30); fs(g, COL.white, 3); } },
      ],
      dyn(c, t) {
        if (t < T) return;
        const u = ((t - T) / 1.6) % 1, back = u > 0.5, v = back ? 2 - 2 * u : 2 * u;
        cmdPill(c, lerp(ex + 86, mx - 52, v), y + (back ? 26 : -26), 0.8, back ? COL.teal2 : COL.amber2);
        const a = -Math.PI / 2 + u * TAU * 0.25; c.beginPath(); c.moveTo(sw[0], sw[1]); c.arc(sw[0], sw[1], 22, -Math.PI / 2, a); c.closePath(); c.fillStyle = 'rgba(89,174,214,.5)'; c.fill(); c.beginPath(); c.moveTo(sw[0], sw[1]); c.lineTo(sw[0] + 22 * Math.cos(a), sw[1] + 22 * Math.sin(a)); inkS(c, 3);
      },
      labels: [{ t: sc.word('왕복'), x: A.cx, y: A.y1 - 26, c: 'tagt', at: sc.w('왕복', pn.t0 - 0.2) }],
    };
  };

  // ── 17 도슨트 핵심(기울어진 칸): 지구 관제실 — 화면 속 달 풍경을 보며 몬다. 창밖 접시 안테나에서 명령이 칸을 깨고 달로 간다
  ART.control = function (sc, pn, A) {
    const desk = A.y1 - 44, win = [A.x1 - 210, A.y0 + 14, 190, 170], dish = [win[0] + 120, win[1] + 120], lw = wordIn(sc, pn, ['루노호트 1호', '지구']), yw = wordIn(sc, pn, ['1970년']);
    const labels = itemTag(sc, pn, A);
    if (yw) labels.push({ t: sc.word(yw), x: A.x0 + 300, y: A.y0 + 80, c: 'big', at: sc.w(yw, pn.t0 - 0.2), rot: -4 });
    if (lw) labels.push({ t: sc.word(lw), x: A.x0 + 110, y: A.y0 + 92, c: 'tagt', at: sc.w(lw, pn.t0 - 0.2) });
    return {
      layers: [
        { f: 0.08, paint(g) { bg(g, pn, '#DDE4EA', '#C9D3DB'); } },
        { f: 0, paint(g) {
          rr(g, win[0], win[1], win[2], win[3], 6); fs(g, '#132C40', 4); orb(g, win[0] + 46, win[1] + 40, 18, 'moon');
          g.save(); rr(g, win[0], win[1], win[2], win[3], 6); g.clip(); hills(g, win[0] - 10, win[0] + win[2], win[1] + win[3] - 20, 16, '#2E4B3C', 1790, win[1] + win[3] + 20);
          g.beginPath(); g.moveTo(dish[0], dish[1] + 10); g.lineTo(dish[0] - 10, win[1] + win[3]); g.lineTo(dish[0] + 10, win[1] + win[3]); g.closePath(); fs(g, COL.grey2, 2.5);
          g.save(); g.translate(dish[0], dish[1]); g.rotate(-0.6); g.beginPath(); g.ellipse(0, 0, 34, 12, 0, 0, Math.PI); g.closePath(); fs(g, '#E8ECEF', 3); g.restore(); g.restore();
          rr(g, win[0], win[1], win[2], win[3], 6); inkS(g, 4);
          rr(g, pn.bb.x0 - 30, desk, win[0] - pn.bb.x0 + 10, 600, 0); fs(g, '#5C6B75', 3);
          for (const sx of [A.x0 + 80, A.x0 + 250]) { rr(g, sx - 62, desk - 104, 124, 84, 6); fs(g, '#22313C', 3); g.save(); rr(g, sx - 56, desk - 98, 112, 72, 3); g.clip(); g.fillStyle = '#0D1520'; g.fillRect(sx - 56, desk - 98, 112, 72); g.beginPath(); g.moveTo(sx - 60, desk - 44); g.quadraticCurveTo(sx, desk - 58, sx + 60, desk - 46); g.lineTo(sx + 60, desk); g.lineTo(sx - 60, desk); g.closePath(); g.fillStyle = '#9AA2A8'; g.fill(); g.restore(); }
        } },
        { f: -0.04, front: true, paint(g) { person(g, A.x0 + 120, A.y1 + 40, 1.2, '#3E5A70'); person(g, A.x0 + 290, A.y1 + 44, 1.15, '#5D7A8E', { hair: '#6B4A33' }); } },
      ],
      dyn(c, t) {
        // 화면 속 달 풍경이 조금씩 흐른다(차가 앞으로 간다) — 화면마다 작은 바위
        for (const sx of [A.x0 + 80, A.x0 + 250]) { c.save(); rr(c, sx - 56, desk - 98, 112, 72, 3); c.clip(); const x = sx + 60 - ((t * 14) % 130); circ(c, x, desk - 36, 7); fs(c, '#6F777C', 0); c.restore(); }
        rings(c, dish[0] + 12, dish[1] - 14, t, pn.t0 + 0.4, { a0: -110, a1: -30, r0: 14, r1: 70, n: 3, speed: 0.8, col: COL.amber3, w: 3 });
      },
      labels, from: [dish[0] + 20, dish[1] - 26],
    };
  };

  // ── 17 침묵 칸: 달 위의 바퀴 여덟 탐사차 — 지구에서 온 명령이 안테나 끝에 닿는다(중고등은 뒤에 우주비행사가 탄 월면차도)
  ART.moonrover = function (sc, pn, A) {
    const b = pn.bb, ground = b.y1 - 64, rx = b.x0 + 200, lrv = sc.has('월면차');
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#0B1622', '#1A2A3A'); for (let k = 0; k < 18; k++) { const r = rand(1799 + k); circ(g, b.x0 + r() * (b.x1 - b.x0), b.y0 - 100 + r() * (ground - b.y0 + 80), 1 + r()); g.fillStyle = 'rgba(255,255,255,.75)'; g.fill(); } orb(g, b.x0 + 60, b.y0 + 56, 26, 'earth'); } },
        { f: 0, paint(g) { rr(g, b.x0 - 30, ground, b.x1 - b.x0 + 60, 600, 0); fs(g, '#B9BFC4', 3); for (const [x, w] of [[b.x0 + 80, 30], [b.x1 - 70, 40]]) { g.beginPath(); g.ellipse(x, ground + 30, w, w * 0.28, 0, 0, TAU); fs(g, '#9AA2A8', 2.5); }
          if (lrv) rover(g, b.x1 - 70, ground + 6, 1.0, 'lrv', 0); rover(g, rx, ground + 8, 1.6, 'luna', 0); } },
      ],
      to: [rx + 42 * 1.6 - 60, ground + 8 - 80 * 1.6 - 6],
    };
  };

  // ── 17 마지막 칸 변형: 로봇 위로 지구와 화성 — 그 사이를 명령 꼬투리가 천천히 건넌다(지연)
  FINV[6] = function (c, t, A, pn, sc, cx) { const y = A.y0 + 70, x0 = cx - 210, x1 = cx + 210; orb(c, x0, y, 22, 'earth'); orb(c, x1, y, 14, 'mars'); c.setLineDash([4, 9]); c.beginPath(); c.moveTo(x0 + 28, y); c.lineTo(x1 - 20, y); c.strokeStyle = 'rgba(14,36,51,.35)'; c.lineWidth = 3; c.stroke(); c.setLineDash([]); cmdPill(c, lerp(x0 + 50, x1 - 40, ((t / 10) % 1 + 1) % 1), y, 0.7, COL.amber2); };

  // ═════════════════════════════════════════════ 18 과학 원리 실험 도구 — 손을 대지 않는 악기(테레민)
  /** 테레민: 다리 달린 나무 상자 · 오른쪽 세로 막대(음높이) · 왼쪽 가로 고리(소리 크기). base = 바닥. 세로 막대 끝 = (x + 52s, base − 230s) */
  function theremin(g, x, base, s, glow) {
    g.save(); g.translate(x, base); g.scale(s, s);
    for (const lx of [-40, 40]) { g.beginPath(); g.moveTo(lx, -60); g.lineTo(lx * 1.25, 0); inkS(g, 4); }
    g.beginPath(); g.moveTo(-58, -80); g.lineTo(-82, -80); inkS(g, 5); g.beginPath(); g.ellipse(-112, -82, 30, 9, 0, 0, TAU); g.strokeStyle = COL.ink; g.lineWidth = 7; g.stroke(); g.strokeStyle = '#C9D3D9'; g.lineWidth = 3; g.stroke();
    rr(g, -60, -94, 120, 36, 5); fs(g, '#8B5A2B', 3); for (const k of [0, 1]) { circ(g, -26 + k * 22, -76, 6); fs(g, COL.cream, 2); }
    g.beginPath(); g.moveTo(52, -94); g.lineTo(52, -230); g.strokeStyle = COL.ink; g.lineWidth = 7; g.stroke(); g.strokeStyle = glow ? COL.amber3 : '#C9D3D9'; g.lineWidth = 3; g.stroke();
    g.restore();
  }
  /** 옆에서 본 편 손 — dir = 1 이면 손끝이 왼쪽(소매는 오른쪽으로), dir = −1 이면 거울(손끝 오른쪽). 손끝은 가운데에서 36s 앞 */
  function palm(c, x, y, s, dir, sleeve) {
    c.save(); c.translate(x, y); c.scale(s * dir, s);
    c.beginPath(); c.moveTo(18, 4); c.lineTo(sleeve || 90, 10); c.strokeStyle = COL.ink; c.lineWidth = 24; c.lineCap = 'round'; c.stroke(); c.strokeStyle = COL.teal2; c.lineWidth = 17; c.stroke();
    c.beginPath(); c.ellipse(0, 0, 22, 17, 0, 0, TAU); fs(c, COL.skin, 3);
    for (let k = 0; k < 4; k++) { rr(c, -36, -14 + k * 8, 22, 7, 3.5); fs(c, COL.skin, 2); }
    rr(c, -8, -30, 9, 18, 4.5); fs(c, COL.skin, 2);
    c.restore();
  }
  /** 카드 꼬리표(item)에 이미 든 낱말이면 null — 같은 칸에 같은 글을 두 번 달지 않는다 */
  const dupTag = (sc, pn, kw) => (kw && pn.item != null && sc.items[pn.item] && sc.items[pn.item].t.indexOf(kw) >= 0 ? null : kw);
  /** 음표(머리 + 기둥 + 깃발) — 글자가 아니라 그림이다 */
  function noteGlyph(c, x, y, s, col) { c.save(); c.translate(x, y); c.scale(s, s); c.beginPath(); c.moveTo(7, 8); c.lineTo(7, -30); c.quadraticCurveTo(18, -22, 20, -10); c.strokeStyle = COL.ink; c.lineWidth = 4; c.lineCap = 'round'; c.stroke(); c.beginPath(); c.ellipse(0, 9, 9, 6.5, -0.45, 0, TAU); fs(c, col || COL.amber2, 2.5); c.restore(); }

  // ── 18 오프닝(넓은 칸): 기초 과학 실험 도구가 놓인 탁자 — 테레민 · 말굽자석 · 코일과 나침반 · 전구
  ART.labtable = function (sc, pn, A) {
    const top = A.y1 - 70, T = pn.t0 + 0.5;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#EEF3EC', '#DDE8DA'); for (let x = pn.bb.x0; x < pn.bb.x1; x += 40) { g.fillStyle = 'rgba(14,36,51,.04)'; g.fillRect(x, pn.bb.y0 - 400, 2, pn.bb.y1 - pn.bb.y0 + 800); } } },
        { f: 0, paint(g) {
          rr(g, pn.bb.x0 - 30, top, pn.bb.x1 - pn.bb.x0 + 60, 18, 0); fs(g, '#A07A4C', 3); rr(g, pn.bb.x0 - 30, top + 18, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#D9CDB8', 3);
          theremin(g, A.x0 + 150, top, 0.72);
          const mx = A.cx + 50; g.beginPath(); g.arc(mx, top - 50, 30, Math.PI, 0); g.lineTo(mx + 30, top - 8); g.lineTo(mx + 14, top - 8); g.lineTo(mx + 14, top - 50); g.arc(mx, top - 50, 14, 0, Math.PI, true); g.lineTo(mx - 14, top - 8); g.lineTo(mx - 30, top - 8); g.closePath(); fs(g, COL.red, 3); rr(g, mx - 30, top - 18, 16, 10, 0); fs(g, COL.grey2, 2); rr(g, mx + 14, top - 18, 16, 10, 0); fs(g, COL.grey2, 2);
          const kx = A.x1 - 120; rr(g, kx - 34, top - 40, 68, 40, 6); fs(g, '#C07A3A', 3); for (let k = 0; k < 6; k++) { g.beginPath(); g.moveTo(kx - 26 + k * 10, top - 40); g.lineTo(kx - 26 + k * 10, top); inkS(g, 2); } circ(g, kx + 70, top - 14, 14); fs(g, COL.white, 3);
        } },
      ],
      dyn(c, t) {
        const kx = A.x1 - 120, a = Math.sin((t - T) * 2) * 0.6; c.beginPath(); c.moveTo(kx + 70 - 10 * Math.cos(a), top - 14 - 10 * Math.sin(a)); c.lineTo(kx + 70 + 10 * Math.cos(a), top - 14 + 10 * Math.sin(a)); c.strokeStyle = COL.red; c.lineWidth = 3; c.stroke();
        const rx = A.x0 + 150 + 52 * 0.72, ry = top - 230 * 0.72;
        for (let k = 0; k < 2; k++) { const u = ((t * 0.4 + k / 2) % 1 + 1) % 1; c.globalAlpha = smooth(u / 0.15) * (1 - u); noteGlyph(c, rx + 20 + 24 * u, ry + 20 - 50 * u, 0.9, k ? COL.teal2 : COL.amber2); } c.globalAlpha = 1;
        rings(c, rx, ry, t, T, { a0: -60, a1: 20, r0: 14, r1: 60, n: 2, speed: 0.7, col: COL.sig2, w: 3 });
      },
      labels: [{ t: sc.word('실험 도구'), x: A.cx, y: A.y0 + 26, c: 'sign', at: sc.w('실험 도구') }],
    };
  };

  // ── 18 손만 움직여 연주하는 악기(item): 테레민 앞의 연주자 — 오른손이 세로 막대 앞에서 오가고, 음표와 소리 고리가 나온다
  ART.theremin = function (sc, pn, A) {
    const base = A.y1 - 10, tx = A.cx - 30, rod = [tx + 52, base - 230], T = pn.t0 + 0.4, lw = dupTag(sc, pn, wordIn(sc, pn, ['테레민', '악기']));
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#F2EEF6', '#E3DCEB'); } },
        { f: 0, paint(g) { rr(g, pn.bb.x0 - 30, base, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#C9BFD6', 3); theremin(g, tx, base, 1); person(g, tx - 214, base + 6, 1.6, COL.teal2, { hair: '#6B4A33' }); } },
      ],
      dyn(c, t) {
        const d = 40 + 30 * Math.sin((t - T) * 1.7), hy = base - 150 + 8 * Math.sin((t - T) * 2.3);
        palm(c, rod[0] + d + 36, hy, 0.9, 1, 70);                                           // 오른쪽에서 막대로 손끝을 내민다
        palm(c, tx - 150, base - 108 - 10 * Math.sin((t - T) * 1.2), 0.75, -1, 60);        // 연주자 쪽에서 고리 위로
        if (t >= T) { rings(c, rod[0], hy, t, T, { a0: -40, a1: 40, r0: 20, r1: 110, n: 3, speed: 0.4 + 0.4 * (1 - (d - 10) / 60), col: COL.sig2, w: 3, dash: [6, 6] });
          for (let k = 0; k < 3; k++) { const u = ((t * 0.35 + k / 3) % 1 + 1) % 1; c.globalAlpha = smooth(u / 0.15) * (1 - u); noteGlyph(c, rod[0] + 60 + 50 * u + 20 * Math.sin(u * 6 + k), rod[1] + 60 - 140 * u, 1, [COL.amber2, COL.teal2, COL.sig2][k]); } c.globalAlpha = 1; }
      },
      labels: itemTag(sc, pn, A).concat(lw ? [{ t: sc.word(lw), x: A.x1 - 90, y: A.y0 + 30, c: 'tagt', at: sc.w(lw, pn.t0 - 0.2) }] : []),
    };
  };

  // ── 18 초등: 손을 가까이 → 소리가 높아지고, 멀리 → 낮아진다 — 손과 막대 사이 거리에 따라 물결이 촘촘해졌다 성겨졌다, 음 높이 눈금이 오르내린다
  ART.pitch = function (sc, pn, A) {
    const rx = A.x0 + 90, top = A.y0 + 20, bot = A.y1 - 20, Tn = sc.w('가까이', pn.t0 - 0.2), Tf = sc.w('멀리', pn.t0 - 0.2), wx0 = A.x0 + 330, wx1 = A.x1 - 70, my = A.y0 + 130;
    const near = (t) => smooth((t - Tn) / 0.6) * (1 - smooth((t - Tf) / 0.6));   // 0 = 보통, 1 = 가까이, 멀리 뒤엔 음수 쪽
    const dist = (t) => lerp(110, 30, near(t)) + 50 * smooth((t - Tf) / 0.6);
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#F2EEF6', '#E3DCEB'); } },
        { f: 0, paint(g) { g.beginPath(); g.moveTo(rx, bot); g.lineTo(rx, top); g.strokeStyle = COL.ink; g.lineWidth = 9; g.stroke(); g.strokeStyle = '#C9D3D9'; g.lineWidth = 4; g.stroke(); rr(g, rx - 30, bot - 6, 60, 26, 4); fs(g, '#8B5A2B', 3);
          rr(g, wx1 + 26, top + 10, 16, bot - top - 30, 8); fs(g, COL.white, 2.5); } },
      ],
      dyn(c, t) {
        const d = dist(t), hx = rx + 30 + d, hy = A.y0 + 120;
        palm(c, hx + 34, hy, 0.95, 1, 60);
        c.setLineDash([4, 7]); c.beginPath(); c.moveTo(rx + 8, hy + 30); c.lineTo(hx - 2, hy + 30); c.strokeStyle = COL.ink2; c.lineWidth = 2.5; c.stroke(); c.setLineDash([]);
        // 소리 물결: 거리가 가까울수록 파장이 짧다(높은 소리)
        const wl = lerp(16, 90, clamp((d - 30) / 150));
        sine(c, wx0, wx1, my, 22, wl, -t * 6 * 60 / wl); band2(c, COL.sig2, 4);
        // 음 높이 눈금: 높을수록 위
        const level = 1 - clamp((d - 30) / 150), ny = lerp(bot - 30, top + 20, level);
        noteGlyph(c, wx1 + 34, ny, 0.9, COL.amber2);
      },
      labels: [{ t: sc.word('가까이'), x: A.x0 + 230, y: A.y0 + 30, c: 'tag', at: Tn }, { t: sc.word('멀리'), x: A.x0 + 230, y: A.y1 - 26, c: 'tagt', at: Tf }],
    };
  };

  // ── 18 중고등: 1920년, 가까이 온 것을 알아채는 센서 연구에서 — 실험대의 상자와 막대, 손이 다가오면 계기 바늘이 기울고 등이 켜진다
  ART.sensor = function (sc, pn, A) {
    const F = (sc.visual && sc.visual.facts) || [], f2 = F.find((f) => f.big.indexOf('센서') >= 0), base = A.y1 - 30, bx = A.x0 + 150, rod = [bx + 50, base - 150];
    const Ty = sc.w('1920년', pn.t0 - 0.2), Ts = sc.w('센서 연구', pn.t0 - 0.2), Tc = sc.w('가까이', pn.t0 - 0.2);
    const labels = [{ t: sc.word('1920년'), x: A.x0 + 96, y: A.y0 + 36, c: 'big', at: Ty, rot: -4 }];
    if (f2) labels.push({ t: f2.big, sub: f2.label, x: A.x1 - 180, y: A.y0 + 44, c: 'fact', at: Ts, rot: 1 });
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#F1ECE2', '#E2D8C6'); } },
        { f: 0, paint(g) { rr(g, pn.bb.x0 - 30, base, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#9AA9B3', 3); rr(g, bx - 60, base - 54, 120, 54, 5); fs(g, '#5C6B75', 3);
          g.beginPath(); g.moveTo(rod[0], base - 54); g.lineTo(rod[0], rod[1]); g.strokeStyle = COL.ink; g.lineWidth = 7; g.stroke(); g.strokeStyle = '#C9D3D9'; g.lineWidth = 3; g.stroke();
          g.beginPath(); g.arc(bx - 20, base - 20, 22, Math.PI, 0); fs(g, COL.cream, 2.5); } },
      ],
      dyn(c, t) {
        const near = smooth((t - Tc) / 0.8), hx = lerp(A.x1 - 60, rod[0] + 46, near);
        palm(c, hx, rod[1] + 40, 0.9, 1, 90);
        const a = Math.PI + lerp(0.25, 2.6, near); c.beginPath(); c.moveTo(bx - 20, base - 20); c.lineTo(bx - 20 + 18 * Math.cos(a), base - 20 + 18 * Math.sin(a)); inkS(c, 3);
        circ(c, bx + 32, base - 30, 10); fs(c, near > 0.6 ? COL.amber3 : COL.grey, 2.5);
        if (near > 0.6) { c.globalAlpha = 0.5; circ(c, bx + 32, base - 30, 18 + 3 * Math.sin(t * 8)); c.strokeStyle = COL.amber2; c.lineWidth = 4; c.stroke(); c.globalAlpha = 1; }
      },
      labels,
    };
  };

  // ── 18 질문 띠 변형: v13 '손도 안 대는데?' 막대 앞의 편 손과 음표
  ASKV[13] = { dyn(c, t, A) { const rx = A.x0 + 40; c.beginPath(); c.moveTo(rx, A.y1 - 8); c.lineTo(rx, A.y1 - 120); c.strokeStyle = COL.ink; c.lineWidth = 7; c.stroke(); c.strokeStyle = '#C9D3D9'; c.lineWidth = 3; c.stroke(); palm(c, rx + 50 + 12 * Math.sin(t * 2), A.y1 - 70, 0.7, 1, 60); noteGlyph(c, rx + 130, A.y1 - 110 - 6 * Math.sin(t * 3), 0.8, COL.amber2); } };

  // ── 18 초등: 마법 같지만 마법이 아니에요 — 반짝이는 요술 지팡이와 모자, '아니에요' 에 빨간 X
  ART.magic = function (sc, pn, A) {
    const hx = A.cx - 60, base = A.y1 - 30, Tm = sc.w('마법', pn.t0 - 0.2), Tx = sc.w('아니에요', pn.t0 - 0.2);
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#2E2448', '#4A3B6B'); } },
        { f: 0, paint(g) { rr(g, pn.bb.x0 - 30, base, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#5B4B7A', 3); g.beginPath(); g.ellipse(hx, base - 4, 80, 16, 0, 0, TAU); fs(g, '#1B1530', 3); rr(g, hx - 50, base - 120, 100, 116, 6); fs(g, '#1B1530', 3); rr(g, hx - 50, base - 40, 100, 16, 0); fs(g, COL.red, 2.5); } },
      ],
      dyn(c, t) {
        const a = -0.6 + 0.12 * Math.sin((t - Tm) * 3), wx = hx + 110, wy = base - 70;
        c.save(); c.translate(wx, wy); c.rotate(a); rr(c, -6, -100, 12, 110, 4); fs(c, '#1B1530', 2.5); rr(c, -6, -100, 12, 18, 3); fs(c, COL.white, 2); c.restore();
        const tip = [wx + 100 * Math.sin(a), wy - 100 * Math.cos(a)];   // 지팡이 끝(돌린 좌표의 (0, −100))
        if (t >= Tm) for (let k = 0; k < 6; k++) { const u = ((t * 0.7 + k / 6) % 1 + 1) % 1, ang = k * 1.1, r = 20 + 60 * u; c.save(); c.globalAlpha = 1 - u; c.translate(tip[0] + Math.cos(ang) * r, tip[1] + Math.sin(ang) * r * 0.7); c.rotate(u * 3); poly(c, [[0, -10], [3, -3], [10, 0], [3, 3], [0, 10], [-3, 3], [-10, 0], [-3, -3]]); fs(c, '#FFE08A', 0); c.restore(); }
        const x = pop(t, Tx, 0.3, 2); if (x > 0) { c.save(); c.translate(hx + 40, base - 90); c.scale(x, x); c.beginPath(); c.moveTo(-70, -70); c.lineTo(70, 70); c.moveTo(70, -70); c.lineTo(-70, 70); c.strokeStyle = COL.ink; c.lineWidth = 22; c.lineCap = 'round'; c.stroke(); c.strokeStyle = COL.red; c.lineWidth = 13; c.stroke(); c.restore(); }
      },
      labels: [{ t: sc.word('마법'), x: A.x1 - 80, y: A.y0 + 30, c: 'tag', at: Tm }],
    };
  };

  // ── 18 중고등: 두 금속 막대가 안테나처럼 생겼지만 전파를 주고받는 안테나가 아니다 — 왼쪽 테레민 막대 · 오른쪽 전파 안테나에 X
  ART.notantenna = function (sc, pn, A) {
    const base = A.y1 - 20, Tm = sc.w('금속 막대', pn.t0 - 0.2), Ta = sc.w('안테나', pn.t0 - 0.2), Tx = sc.w('아니에요', pn.t0 - 0.2), ax = A.x1 - 130;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#F2EEF6', '#E3DCEB'); g.fillStyle = '#E1EEF5'; g.fillRect(A.cx + 20, pn.bb.y0 - 1400, pn.bb.x1 - A.cx + 20, pn.bb.y1 - pn.bb.y0 + 2800); } },
        { f: 0, paint(g) { rr(g, pn.bb.x0 - 30, base, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#C9BFD6', 3); theremin(g, A.x0 + 170, base, 0.8); lattice(g, ax, base, 170, 60);
          g.beginPath(); g.moveTo(A.cx + 20, pn.bb.y0 - 10); for (let k = 0; k < 12; k++) g.lineTo(A.cx + 20 + (k % 2 ? 8 : -8), pn.bb.y0 + (pn.bb.y1 - pn.bb.y0) * (k + 1) / 12); inkS(g, 4); } },
      ],
      dyn(c, t) {
        if (t >= Tm) { const g = 0.5 + 0.5 * Math.sin((t - Tm) * 5); c.globalAlpha = 0.3 + 0.4 * g; c.beginPath(); c.moveTo(A.x0 + 170 + 52 * 0.8, base - 94 * 0.8); c.lineTo(A.x0 + 170 + 52 * 0.8, base - 230 * 0.8); c.strokeStyle = COL.amber2; c.lineWidth = 14; c.lineCap = 'round'; c.stroke(); c.beginPath(); c.ellipse(A.x0 + 170 - 112 * 0.8, base - 82 * 0.8, 30 * 0.8 + 6, 9 * 0.8 + 6, 0, 0, TAU); c.stroke(); c.globalAlpha = 1; }
        rings(c, ax, base - 176, t, Ta, { a0: -160, a1: -20, r0: 16, r1: 90, n: 3, speed: 0.7, col: COL.sig2, w: 3, dash: [7, 7] });
        const x = pop(t, Tx, 0.3, 2); if (x > 0) { c.save(); c.translate(ax, base - 120); c.scale(x, x); c.beginPath(); c.moveTo(-50, -50); c.lineTo(50, 50); c.moveTo(50, -50); c.lineTo(-50, 50); c.strokeStyle = COL.ink; c.lineWidth = 18; c.lineCap = 'round'; c.stroke(); c.strokeStyle = COL.red; c.lineWidth = 10; c.stroke(); c.restore(); }
      },
      labels: [{ t: sc.word('금속 막대'), x: A.x0 + 120, y: A.y0 + 30, c: 'tag', at: Tm }, { t: sc.word('안테나'), x: A.x1 - 70, y: A.y0 + 30, c: 'tagt', at: Ta }],
    };
  };

  // ── 18 도슨트 핵심(기울어진 칸): 보이지 않는 전기의 힘이 손을 알아챈다(중고등: 손과 막대가 축전기가 된다) — 다가오는 손과 막대 사이 힘줄이 촘촘해지고, 음표가 칸을 깨고 나간다
  ART.field = function (sc, pn, A) {
    const rx = A.x0 + 170, top = A.y0 + 74, bot = A.y1 - 6, mv = sc.moves[pn.i], T = pn.t0 + 0.3, kw = wordIn(sc, pn, ['축전기', '전기의 힘']), lw = dupTag(sc, pn, kw);
    const labels = itemTag(sc, pn, A);
    if (lw) labels.push({ t: sc.word(lw), x: A.x1 - 110, y: A.y0 + 40, c: 'tagt', at: sc.w(lw, pn.t0 - 0.2) });
    return {
      layers: [
        { f: 0.12, paint(g) { bg(g, pn, '#EFEAF6', '#DDD4EA'); } },
        { f: 0, paint(g) { g.beginPath(); g.moveTo(rx, bot + 200); g.lineTo(rx, top); g.strokeStyle = COL.ink; g.lineWidth = 12; g.stroke(); g.strokeStyle = '#C9D3D9'; g.lineWidth = 6; g.stroke(); circ(g, rx, top - 6, 9); fs(g, '#C9D3D9', 3); } },
      ],
      dyn(c, t) {
        // 손이 칸 시간 동안 다가온다 → 막대와 손 사이 힘줄(점선 곡선)이 늘고 밝아진다
        const p = smooth((t - T) / Math.max(1.5, mv.t0 - T - 0.6)), hx = lerp(A.x1 - 80, rx + 90, p), hy = A.y0 + 150, n = 3 + Math.round(5 * p);
        for (let k = 0; k < n; k++) { const f = (k + 0.5) / n, y0 = lerp(top + 30, bot - 30, f), bend = (y0 - hy) * 0.35; c.beginPath(); c.moveTo(rx + 8, y0); c.quadraticCurveTo((rx + hx) / 2, (y0 + hy) / 2 + bend * 0.2, hx - 42, hy + (f - 0.5) * 40); c.setLineDash([6, 8]); c.lineDashOffset = -t * 30; c.strokeStyle = 'rgba(11,127,181,' + (0.25 + 0.6 * p).toFixed(2) + ')'; c.lineWidth = 3; c.stroke(); c.setLineDash([]); }
        palm(c, hx, hy, 1.1, 1, 100);
        // 중고등: 축전기 기호(두 판 — 막대 쪽 · 손 쪽)
        if (kw === '축전기') { const k = pop(t, sc.w('축전기', pn.t0 - 0.2), 0.3, 2); if (k > 0) { c.save(); c.translate((rx + hx) / 2, A.y1 - 30); c.scale(k, k); for (const s of [-1, 1]) { c.beginPath(); c.moveTo(s * 9, -20); c.lineTo(s * 9, 20); c.moveTo(s * 9, 0); c.lineTo(s * 30, 0); inkS(c, 5); } c.restore(); } }
        if (t < mv.t0 - 0.35) for (let k = 0; k < 2; k++) { const u = ((t * 0.4 + k / 2) % 1 + 1) % 1; c.globalAlpha = smooth(u / 0.15) * (1 - u); noteGlyph(c, rx + 30 + 30 * u, top + 40 - 50 * u, 1, COL.teal2); } c.globalAlpha = 1;
      },
      labels, from: [rx + 46, top + 16],
    };
  };

  // ── 18 침묵 칸: 오선지 — 날아온 음표가 높은 자리(위쪽 줄)에 와서 선다(손이 가까이 왔으니 높은 소리)
  ART.staff = function (sc, pn, A) {
    const b = pn.bb, y0 = b.y0 + 90, gap = 22, xs = b.x0 + 40, xe = b.x1 - 30;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#F7F3EA', '#EDE5D4'); } },
        { f: 0, paint(g) {
          rr(g, b.x0 + 18, b.y0 + 40, b.x1 - b.x0 - 36, b.y1 - b.y0 - 80, 6); fs(g, '#FFFDF7', 2.5);
          for (let k = 0; k < 5; k++) { g.beginPath(); g.moveTo(xs, y0 + k * gap); g.lineTo(xe, y0 + k * gap); g.strokeStyle = COL.ink2; g.lineWidth = 2; g.stroke(); }
          g.beginPath(); g.moveTo(xs + 26, y0 + 4 * gap + 26); g.bezierCurveTo(xs + 6, y0 + 4 * gap - 10, xs + 44, y0 + gap, xs + 30, y0 - 18); g.bezierCurveTo(xs + 20, y0 + 30, xs + 50, y0 + 3 * gap, xs + 24, y0 + 2 * gap + 6); inkS(g, 3.5);
          noteGlyph(g, xs + 110, y0 + 4 * gap - 2, 0.9, COL.grey2); noteGlyph(g, xs + 160, y0 + 3 * gap + 9, 0.9, COL.grey2);
          circ(g, xe - 70, y0 - 2, 16); g.setLineDash([5, 5]); g.strokeStyle = COL.ink2; g.lineWidth = 2; g.stroke(); g.setLineDash([]);
        } },
      ],
      to: [xe - 70, y0 - 16],          // 음표 머리(BRK.note 의 (0, 9)×1.6)가 점선 자리 (xe − 70, y0 − 2) 에 오게
    };
  };

  // ── 18 마지막 칸 변형: 두 로봇 사이에서 음표가 피어오른다
  FINV[7] = function (c, t, A, pn, sc, cx, y) { for (let k = 0; k < 4; k++) { const u = ((t * 0.3 + k / 4) % 1 + 1) % 1; c.globalAlpha = smooth(u / 0.15) * (1 - u); noteGlyph(c, cx - 30 + 60 * ((k * 37) % 4) / 3 + 16 * Math.sin(u * 5 + k), y + 20 - 150 * u, 1, [COL.amber2, COL.teal2, COL.sig2, COL.amber2][k]); } c.globalAlpha = 1; };

  // ═════════════════════════════════════════════ 19 마무리 — 고맙습니다 · 사람이 찾아낸 전파 · 01 의 전파 띠가 관람객에게
  // 오프닝은 01 의 ART.hall 을 저녁(v 1)으로 다시 쓴다 — 첫 큐와 끝 큐가 같은 건물에서 열리고 닫힌다.

  // ── 19 와 주셔서(함께해 주셔서) 고맙습니다 — 두 로봇이 관람객 쪽으로 고개 숙여 인사한다
  ART.bow = function (sc, pn, A) {
    const y = A.y0 + 104, xm = A.cx - 110, xd = A.cx + 110, T = sc.w('고맙습니다', pn.t0 - 0.2);
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#FCE9D2', '#F6D6B0'); g.strokeStyle = 'rgba(185,111,0,.14)'; g.lineWidth = 4; g.setLineDash([12, 12]); for (let r = 90; r < 420; r += 66) { circ(g, A.cx, y + 30, r); g.stroke(); } g.setLineDash([]); } },
        { f: 0, paint(g) { rr(g, pn.bb.x0 - 30, y + 90, pn.bb.x1 - pn.bb.x0 + 60, 600, 0); fs(g, '#E2C08C', 3); } },
        { f: -0.05, front: true, paint(g) { for (let k = 0; k < 7; k++) { const x = A.x0 + 40 + k * 86, h = A.y1 + 30; circ(g, x, h - 58 - (k % 2) * 8, 22); fs(g, ['#3B2A22', '#6B4A33', '#2A2A2A'][k % 3], 2.5); g.beginPath(); g.ellipse(x, h, 40, 34, 0, Math.PI, TAU); fs(g, [COL.teal2, COL.amber2, COL.sig2, COL.red][k % 4], 2.5); } } },
      ],
      dyn(c, t) {
        const b = smooth((t - T + 0.2) / 0.5) * (1 - smooth((t - T - 1.3) / 0.6)), a = 0.42 * b;
        for (const [x, s] of [[xm, 1], [xd, -1]]) { c.save(); c.translate(x, y + 14 * b); c.rotate(0.3 * a * s); robot(c, 0, 0, 54, s < 0); c.restore(); }   // 고개를 숙이며 서로 쪽으로 살짝 기운다
        if (t >= T) for (let k = 0; k < 6; k++) { const u = ((t * 0.5 + k / 6) % 1 + 1) % 1; c.globalAlpha = smooth(u / 0.15) * (1 - u); const hx = A.cx + (k - 2.5) * 34, hy = y - 30 - 70 * u; c.beginPath(); c.moveTo(hx, hy + 8); c.bezierCurveTo(hx - 14, hy - 4, hx - 6, hy - 14, hx, hy - 6); c.bezierCurveTo(hx + 6, hy - 14, hx + 14, hy - 4, hx, hy + 8); fs(c, COL.red, 2); } c.globalAlpha = 1;
      },
      labels: [{ t: sc.word('고맙습니다'), x: A.cx, y: A.y0 + 26, c: 'tag', at: T }],
    };
  };

  // ── 19 도슨트 핵심(기울어진 칸): 사람이 찾아낸 전파 — 돋보기 속에서 드러난 물결이 오른쪽으로 흘러 통신·방송·이동통신에 닿고(중고등: 관리까지),
  //    그 물결 끝의 전파 띠(01 의 BRK.ribbon)가 칸을 깨고 나가 침묵 칸의 관람객 머리 위에 머문다
  //    이름표: 중고등은 카드 visual.steps 의 k 그대로, 초등은 대사 낱말('찾아내서'·'지금처럼')
  ART.found = function (sc, pn, A) {
    const wy = A.y0 + 176, lx = A.x0 + 92, x1 = A.x1 - 60, mv = sc.moves[pn.i];
    const elem = sc.level === '초등', steps = (sc.visual && sc.visual.steps) || [];
    const at = (kws, d) => firstAt(sc, kws, pn.t0 - 0.2, pn.t1) ?? pn.t0 + d;
    const icons = elem
      ? [['lens', lx, at(['찾아내서'], 0.4)], ['tower', A.x0 + 250, at(['지금처럼'], 2)], ['tv', A.x0 + 350, at(['지금처럼'], 2) + 0.25], ['phone', A.x0 + 440, at(['지금처럼'], 2) + 0.5]]
      : [['lens', lx, at(['발견'], 0.4)], ['tower', A.x0 + 222, at(['통신에'], 1.5)], ['tv', A.x0 + 336, at(['방송'], 2.5)], ['phone', A.x0 + 410, at(['이동통신'], 3)], ['shield', A.x1 - 84, at(['관리'], 7)]];
    const labels = [];
    if (elem) {
      labels.push({ t: sc.word('찾아내서'), x: lx, y: A.y0 + 96, c: 'tag', at: icons[0][2] });
      labels.push({ t: sc.word('지금처럼'), x: A.x0 + 350, y: A.y0 + 96, c: 'tagt', at: icons[1][2] });
    } else {
      const S = (k) => steps.find((s) => s.k === k);
      for (const [k, x, i] of [['발견', lx, 0], ['통신', A.x0 + 222, 1], ['방송·이동통신', A.x0 + 373, 2], ['관리', A.x1 - 84, 4]]) if (S(k)) labels.push({ t: S(k).k, x, y: A.y0 + 96, c: i % 2 ? 'tagt' : 'tag', at: icons[i][2] });
    }
    return {
      layers: [
        { f: 0.12, paint(g) { bg(g, pn, '#DDEFF8', '#F6FAFC'); cloud(g, A.x0 + 200, A.y0 + 30, 0.8); } },
        { f: 0.04, paint(g) { hills(g, pn.bb.x0 - 40, pn.bb.x1, A.y1 - 10, 40, '#C7DDB9', 191, pn.bb.y1 + 600); } },
      ],
      dyn(c, t) {
        // 물결: 돋보기에서 드러난 뒤(첫 아이콘 시각) 오른쪽으로 자라 나간다 — 아이콘마다 그 시각까지 자란다
        const T0 = icons[0][2], p = smooth((t - T0) / Math.max(1.5, mv.t0 - T0 - 0.8)), xe = lerp(lx + 50, x1, p);
        c.setLineDash([6, 9]); sine(c, A.x0 + 10, x1, wy, 14, 70, -t * 2.4); c.strokeStyle = COL.grey; c.lineWidth = 3; c.globalAlpha = 0.6; c.stroke(); c.setLineDash([]); c.globalAlpha = 1;
        if (t >= T0) { sine(c, lx + 40, xe, wy, 14, 70, -t * 2.4); band2(c, COL.teal2, 6); }
        for (const [kind, x, T] of icons) {
          const k = pop(t, T, 0.35, 2); if (k <= 0) continue;
          c.save(); c.translate(x, wy); c.scale(k, k);
          if (kind === 'lens') { c.save(); circ(c, 0, 0, 40); c.clip(); c.fillStyle = 'rgba(255,255,255,.85)'; c.fillRect(-40, -40, 80, 80); sine(c, -44, 44, 0, 14, 70, (lx - A.x0 - 54) / 70 * TAU - t * 2.4);   /* 바깥 물결과 위상을 맞춘다 */ band2(c, COL.teal2, 6); c.restore(); lens(c, 0, 0, 40); }
          else if (kind === 'tower') { lattice(c, 0, 44, 96, 40); }
          else if (kind === 'tv') { rr(c, -34, -26, 68, 48, 6); fs(c, '#22313C', 3); rr(c, -28, -20, 56, 36, 3); fs(c, '#CFEFFF', 0); c.beginPath(); c.moveTo(-12, -26); c.lineTo(-24, -44); c.moveTo(12, -26); c.lineTo(24, -44); inkS(c, 3); rr(c, -14, 22, 28, 8, 3); fs(c, COL.grey, 2); }
          else if (kind === 'phone') { handset(c, 0, 34, 0.85, 'smart', true); }
          else { c.beginPath(); c.moveTo(0, -36); c.lineTo(30, -24); c.lineTo(28, 6); c.quadraticCurveTo(22, 28, 0, 38); c.quadraticCurveTo(-22, 28, -28, 6); c.lineTo(-30, -24); c.closePath(); fs(c, COL.sig, 3); c.beginPath(); c.moveTo(-12, 0); c.lineTo(-2, 10); c.lineTo(14, -10); c.strokeStyle = COL.white; c.lineWidth = 5; c.lineCap = 'round'; c.stroke(); }
          c.restore();
        }
      },
      labels, from: [x1 + 8, wy - 6],
    };
  };

  // ── 19 침묵 칸: 뒤에서 본 관람객들 — 날아온 전파 띠가 머리 위에 머문다(가깝게 느끼는 전파)
  ART.crowd = function (sc, pn, A) {
    const b = pn.bb, cx = (b.x0 + b.x1) / 2, base = b.y1 + 20;
    return {
      layers: [
        { f: 0.1, paint(g) { bg(g, pn, '#FBE8C8', '#F6D6B0'); g.strokeStyle = 'rgba(185,111,0,.15)'; g.lineWidth = 4; g.setLineDash([10, 10]); for (let r = 50; r < 260; r += 50) { circ(g, cx, b.y0 + 110, r); g.stroke(); } g.setLineDash([]); } },
        { f: 0, paint(g) { [[cx - 120, 0.95, '#3B2A22', COL.teal2], [cx + 120, 0.95, '#6B4A33', COL.amber2], [cx - 40, 1.15, '#2A2A2A', COL.sig2], [cx + 54, 1.1, '#3B2A22', COL.red]].forEach(([x, s, hair, shirt]) => { g.beginPath(); g.ellipse(x, base, 58 * s, 60 * s, 0, Math.PI, TAU); fs(g, shirt, 3); circ(g, x, base - 84 * s, 30 * s); fs(g, hair, 3); }); } },
      ],
      to: [cx, b.y0 + 110],
    };
  };

  // ── 19 마지막 칸 변형: 색종이가 내려온다(되감아도 같은 자리 — 시드와 t 의 식)
  FINV[8] = function (c, t, A) { const r = rand(1919); for (let k = 0; k < 26; k++) { const x0 = 40 + r() * (SW - 80), sp = 40 + 50 * r(), ph = r() * 10, col = [COL.amber2, COL.teal2, COL.sig2, COL.red][k % 4], u = ((t * sp / 300 + ph) % 1 + 1) % 1, y = A.y0 + 20 + u * (A.h - 60); c.save(); c.globalAlpha = smooth(u / 0.1) * (1 - smooth((u - 0.85) / 0.15)); c.translate(x0 + 14 * Math.sin(t * 2 + ph), y); c.rotate(t * 3 + ph); c.fillStyle = col; c.fillRect(-5, -3, 10, 6); c.restore(); } };

  // ═════════════════════════════════════════════ 칸을 깨고 나오는 물체 — mode: rest(출발 전) · halo(날며 크림색 테두리) · shadow(여백 위 납작한 그림자)
  /** 01: 전파 띠 — 진흥원 탑에서 나가 침묵 칸의 마을 위에 머문다 */
  BRK.ribbon = function (c, st) {
    const ph = st.t * 7, L = 74;
    c.save(); c.translate(st.x, st.y); c.rotate(st.ang);
    const s = st.mode === 'rest' ? st.k : 1; c.scale(s, s);
    const curve = () => { c.beginPath(); for (let x = -L; x <= L; x += 3) { const env = Math.sin(Math.PI * (x + L) / (2 * L)); const y = 13 * env * Math.sin(x / 26 + ph); if (x === -L) c.moveTo(x, y); else c.lineTo(x, y); } };
    c.lineCap = 'round'; c.lineJoin = 'round';
    if (st.mode === 'shadow') { curve(); c.strokeStyle = COL.shade; c.lineWidth = 16; c.stroke(); circ(c, L + 4, 0, 12); c.fillStyle = COL.shade; c.fill(); c.restore(); return; }
    if (st.mode === 'halo') { curve(); c.strokeStyle = COL.cream; c.lineWidth = 28; c.stroke(); circ(c, L + 4, 0, 19); c.fillStyle = COL.cream; c.fill(); }
    curve(); c.strokeStyle = COL.ink; c.lineWidth = 16; c.stroke(); c.strokeStyle = COL.teal2; c.lineWidth = 9; c.stroke();
    circ(c, L + 4, 0, 11); fs(c, COL.amber2, 3.5);
    c.restore();
  };
  /** 02: 모스 신호(점·선 묶음) — 송신 안테나에서 나가 여백(바다)을 건너 수신 안테나에 닿는다 */
  BRK.morse = function (c, st) {
    const seq = [1, 3, 1, 1, 3], gap = 9; let len = 0; for (const m of seq) len += (m === 3 ? 34 : 13) + gap; len -= gap;
    c.save(); c.translate(st.x, st.y); c.rotate(st.ang);
    const s = st.mode === 'rest' ? st.k : 1; c.scale(s, s);
    const each = (fn) => { let x = -len / 2; for (const m of seq) { const w = m === 3 ? 34 : 13; fn(x, w); x += w + gap; } };
    if (st.mode === 'shadow') { c.fillStyle = COL.shade; each((x, w) => { c.beginPath(); c.roundRect(x, -7, w, 14, 7); c.fill(); }); c.restore(); return; }
    if (st.mode === 'halo') {
      c.strokeStyle = COL.sig2; c.lineWidth = 4; c.lineCap = 'round'; c.globalAlpha = 0.75; for (const r of [26, 44]) { c.beginPath(); c.arc(-len / 2 - 26, 0, r, -0.7, 0.7); c.stroke(); } c.globalAlpha = 1;
      c.fillStyle = COL.cream; each((x, w) => { c.beginPath(); c.roundRect(x - 7, -14, w + 14, 28, 14); c.fill(); });
    }
    each((x, w) => { c.beginPath(); c.roundRect(x, -7, w, 14, 7); fs(c, COL.amber2, 3); });
    c.restore();
  };
  /** 03: 짧은 물결 한 묶음(빠르게 출렁이는 쪽의 끝) — 기울어진 칸의 아래 줄 끝에서 떨어져 나가 침묵 칸 비교 자의 빈 자리에 눕는다.
   *  파장·진폭·흐름은 그 줄(ART.squeeze 짧은 줄: λ 48 · 진폭 12 · WAVE_V)과 같다 — 떨어져 나가는 순간 이음매가 맞는다 */
  BRK.packet = function (c, st) {
    const L = 72, wl = SQ.wlS, amp = 12, ph = st.t * TAU * WAVE_V / wl;
    c.save(); c.translate(st.x, st.y); c.rotate(st.ang);
    const s = st.mode === 'rest' ? st.k : 1; c.scale(s, s);
    const curve = () => { c.beginPath(); for (let x = -L; x <= L + 0.1; x += 3) { const y = -amp * Math.sin((x + L) / wl * TAU - ph); if (x === -L) c.moveTo(x, y); else c.lineTo(x, y); } };
    c.lineCap = 'round'; c.lineJoin = 'round';
    if (st.mode === 'shadow') { curve(); c.strokeStyle = COL.shade; c.lineWidth = 14; c.stroke(); c.restore(); return; }
    if (st.mode === 'halo') { curve(); c.strokeStyle = COL.cream; c.lineWidth = 26; c.stroke(); }
    curve(); c.strokeStyle = COL.ink; c.lineWidth = 13; c.stroke(); c.strokeStyle = COL.sig2; c.lineWidth = 6; c.stroke();
    c.restore();
  };
  /** 04: 불꽃에서 나온 전파 한 덩이(번개 심 + 앞으로 퍼지는 고리 둘) — 실험대의 불꽃 틈에서 떠나 떨어진 고리 앞에 멈춘다 */
  BRK.sparkwave = function (c, st) {
    c.save(); c.translate(st.x, st.y); c.rotate(st.ang); const s = st.mode === 'rest' ? st.k : 1; c.scale(s, s);
    const arcs = (col, w) => { for (const r of [24, 40]) { c.beginPath(); c.arc(-18, 0, r, -0.8, 0.8); c.strokeStyle = col; c.lineWidth = w; c.lineCap = 'round'; c.stroke(); } };
    if (st.mode === 'shadow') { arcs(COL.shade, 12); c.restore(); return; }
    const r = rand(1 + Math.floor(st.t * 12)), bolt = () => { c.beginPath(); c.moveTo(-50, 0); for (let k = 1; k < 5; k++) c.lineTo(-50 + k * 7, (r() - 0.5) * 16); c.lineTo(-12, 0); };
    if (st.mode === 'halo') { arcs(COL.cream, 22); bolt(); c.strokeStyle = COL.cream; c.lineWidth = 16; c.stroke(); }
    arcs(COL.ink, 12); arcs(COL.sig2, 6);
    bolt(); c.strokeStyle = COL.ink; c.lineWidth = 8; c.lineJoin = 'round'; c.stroke(); c.strokeStyle = COL.amber3; c.lineWidth = 4; c.stroke();
    c.restore();
  };
  /** 07: 구조 신호(빨간 불과 앞으로 퍼지는 빨간 고리 셋) — 물에 뜬 자동 장치에서 떠나 이웃 배의 돛대 끝에 닿는다 */
  BRK.call = function (c, st) {
    c.save(); c.translate(st.x, st.y); c.rotate(st.ang); const s = st.mode === 'rest' ? st.k : 1; c.scale(s, s);
    const arcs = (col, w) => { for (const r of [18, 32, 46]) { c.beginPath(); c.arc(-30, 0, r, -0.7, 0.7); c.strokeStyle = col; c.lineWidth = w; c.lineCap = 'round'; c.stroke(); } };
    if (st.mode === 'shadow') { arcs(COL.shade, 10); c.restore(); return; }
    if (st.mode === 'halo') { arcs(COL.cream, 20); circ(c, -30, 0, 15); c.fillStyle = COL.cream; c.fill(); }
    arcs(COL.ink, 10); arcs(COL.red, 5); circ(c, -30, 0, 9); fs(c, COL.red, 3);
    c.restore();
  };
  /** 14: 영상 한 장(재생 단추가 있는 화면 조각) — 5세대 기지국에서 떠나 침묵 칸의 손 안 스마트폰 화면에 들어간다 */
  BRK.video = function (c, st) {
    c.save(); c.translate(st.x, st.y); c.rotate(st.ang); const s = st.mode === 'rest' ? st.k : 1; c.scale(s, s);
    if (st.mode === 'shadow') { c.beginPath(); c.roundRect(-42, -28, 84, 56, 8); c.fillStyle = COL.shade; c.fill(); c.restore(); return; }
    if (st.mode === 'halo') { c.beginPath(); c.roundRect(-50, -36, 100, 72, 12); c.fillStyle = COL.cream; c.fill(); }
    rr(c, -42, -28, 84, 56, 8); fs(c, COL.sig, 3.5); poly(c, [[-9, -15], [-9, 11], [14, -2]]); fs(c, COL.white, 0);
    rr(c, -32, 17, 64, 4, 2); c.fillStyle = 'rgba(255,255,255,.45)'; c.fill(); rr(c, -32, 17, 64 * ((st.t * 0.25) % 1), 4, 2); c.fillStyle = COL.amber3; c.fill();
    c.restore();
  };
  /** 17: 명령 꼬투리(›› 가 든 큰 캡슐 + 뒤로 끌리는 작은 고리) — 지구 관제실 접시 안테나에서 떠나 달 위 탐사차의 안테나 끝에 닿는다 */
  BRK.command = function (c, st) {
    c.save(); c.translate(st.x, st.y); c.rotate(st.ang); const s = st.mode === 'rest' ? st.k : 1; c.scale(s, s);
    if (st.mode === 'shadow') { c.beginPath(); c.roundRect(-34, -17, 68, 34, 17); c.fillStyle = COL.shade; c.fill(); c.restore(); return; }
    if (st.mode === 'halo') { c.beginPath(); c.roundRect(-42, -25, 84, 50, 25); c.fillStyle = COL.cream; c.fill(); for (const r of [14, 24]) { c.beginPath(); c.arc(-44, 0, r, Math.PI - 0.7, Math.PI + 0.7); c.strokeStyle = COL.amber3; c.lineWidth = 4; c.lineCap = 'round'; c.stroke(); } }
    rr(c, -34, -17, 68, 34, 17); fs(c, COL.amber2, 3.5);
    for (const dx of [-12, 6]) { c.beginPath(); c.moveTo(dx - 5, -9); c.lineTo(dx + 6, 0); c.lineTo(dx - 5, 9); c.strokeStyle = COL.white; c.lineWidth = 4.5; c.lineCap = 'round'; c.lineJoin = 'round'; c.stroke(); }
    c.restore();
  };
  /** 18: 음표(머리 + 기둥 + 깃발, 1.6배) — 테레민 막대 끝에서 떠나 침묵 칸 오선지의 높은 자리에 선다 */
  BRK.note = function (c, st) {
    c.save(); c.translate(st.x, st.y); c.rotate(st.ang); const s = (st.mode === 'rest' ? st.k : 1) * 1.6; c.scale(s, s);
    const stem = () => { c.beginPath(); c.moveTo(7, 8); c.lineTo(7, -30); c.quadraticCurveTo(18, -22, 20, -10); }, head = () => { c.beginPath(); c.ellipse(0, 9, 9, 6.5, -0.45, 0, TAU); };
    c.lineCap = 'round'; c.lineJoin = 'round';
    if (st.mode === 'shadow') { stem(); c.strokeStyle = COL.shade; c.lineWidth = 5; c.stroke(); head(); c.fillStyle = COL.shade; c.fill(); c.restore(); return; }
    if (st.mode === 'halo') { stem(); c.strokeStyle = COL.cream; c.lineWidth = 12; c.stroke(); head(); c.lineWidth = 10; c.stroke(); }
    stem(); c.strokeStyle = COL.ink; c.lineWidth = 4; c.stroke(); head(); fs(c, COL.amber2, 2.5);
    c.restore();
  };
