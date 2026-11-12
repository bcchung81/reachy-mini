  // ═════════════════════════════════════════════ 칸 그림 (빌더가 template.html 의 /*__SCENES__*/ 자리에 넣는다)
  // ART[이름](sc, pn, A) → { layers:[{f, paint(g), front?}], dyn(c, t, d, pn), labels:[…], gut:[…], from:[x,y], to:[x,y], brkAt }
  //   pn = 칸(스트립 좌표 bb·poly·t0·t1…), A = 그림 상자(말풍선 아래 — 주인공은 여기에). 층은 한 번 굽고 y − f·d 에 놓인다.
  // 글자 규칙: 이름표 글은 ① 그 수준의 검증된 카드(items[].t · visual 의 facts/from/to/label) 그대로, ② sc.word('낱말') —
  //   그 큐 대사에 실제로 나온 낱말, 둘 중 하나만. 그래서 같은 그림 함수가 초등·중고등을 모두 그린다(이름표만 그 수준 카드에서).
  // 시각 규칙: 움직이는 것은 칸의 말 시각(pn.t0·pn.t1) 또는 sc.w('낱말') 에 묶는다. 그림은 t 의 순수 함수.
  // 그림 문법: 가까운 층은 잉크 선(3px) + 평면 색, 먼 층은 선 없이 옅게 — 웹툰의 깊이 표현.
  const ART = {}, BRK = {};
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
        { f: 0.16, paint(g) { bg(g, pn, '#CBE6F4', '#F4F9FC'); circ(g, A.x1 - 80, A.y0 + 34, 32); fs(g, COL.amber3, 0); cloud(g, A.x0 + 120, pn.bb.y0 + 70, 1.1); cloud(g, A.x1 - 210, A.y0 + 10, 0.8); } },
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
        } },
      ],
      dyn(c, t) {
        if (v !== 1) return;
        const y = A.y1 - 54; c.setLineDash([8, 9]); c.lineDashOffset = -t * 30; sine(c, A.x0 + 6, A.x1 - 6, y, 16, 90, t * 2); c.strokeStyle = COL.sig; c.lineWidth = 4; c.stroke(); c.setLineDash([]);
        lens(c, A.cx - 20, y - 8 + 4 * Math.sin(t * 2.4), 30);
      },
      labels: [{ t: sc.word('?'), x: A.cx + (v === 1 ? 50 : 4), y: A.y0 + 58, c: 'q', at: pn.t0 + 0.25, rot: 8 }],
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
      dyn(c, t) { rings(c, cx, y - 60, t, pn.t0 + 0.3, { a0: -170, a1: -10, r0: 30, r1: 200, col: COL.sig2, speed: 0.35, al: 0.6 }); },
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
