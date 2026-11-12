  // ═════════════════════════════════════════════ 큐별 장면 (빌더가 template.html 의 /*__SCENES__*/ 자리에 넣는다)
  // 글자 규칙: 꼬리표의 글은 ① 검증된 카드의 visual(facts·steps) 그대로, ② 그 큐 대사에 실제로 나온 낱말, 둘 중 하나만 쓴다.
  // 시각 규칙: 조각은 `sc.w('낱말')` — 그 낱말을 말하는 때 놓인다. 대사가 바뀌어 낱말이 사라지면 콘솔 경고가 난다.

  // ── 묶음 도구
  function pc(shape, color, h, o) { o = o || {}; o.h = h == null ? 12 : h; return P_(shape, color, o); }
  function grp(sc, parts, x, y, o) { o = o || {}; o.parts = parts; o.x = x; o.y = y; if (o.rot) o.rot *= DEG; return sc.add(o); }
  function fact(sc, f, x, y, o) { o = o || {}; var w = o.w || 340; return grp(sc, [[pc(S.tag(w, 108), o.color || COL.cream, 20)]], x, y, { rot: o.rot || 0, h: 20, at: o.at, phase: o.phase, label: { c: 'l-fact', t: f.big, sub: f.label, w: w - 44 } }); }
  function stepTag(sc, s, x, y, o) { o = o || {}; var w = o.w || 220; return grp(sc, [[pc(S.rect(w, o.hh || 94), COL.cream, 16)]], x, y, { rot: o.rot || 0, h: 16, at: o.at, phase: o.phase, label: { c: 'l-step', t: s.k, sub: s.v, w: w - 18 } }); }
  function tagL(sc, text, x, y, o) { o = o || {}; return grp(sc, [[pc(S.tag(text.length * 18 + 58, 44), o.color || COL.ink, 18)]], x, y, { rot: o.rot || 0, h: 18, at: o.at, phase: o.phase, label: { c: 'l-name', t: text } }); }
  function cap(sc, text, x, y, at, cls, phase) { return sc.add({ x: x, y: y, h: 8, at: at, phase: phase, label: { c: cls || 'l-cap', t: text } }); }
  function strip(sc, x0, x1, y, at, o) { o = o || {}; return grp(sc, [[pc(S.rect(x1 - x0, 9), o.color || COL.ink, 4)]], (x0 + x1) / 2, y, { h: 4, at: at, phase: o.phase }); }
  function dot(sc, x, y, at, o) { o = o || {}; return grp(sc, [[pc(S.circle(o.r || 7), o.color || COL.ink, o.h || 14)]], x, y, { h: o.h || 14, at: at, phase: o.phase, jit: o.jit == null ? .7 : o.jit }); }
  function strike(sc, x, y, len, rot, at, o) { o = o || {}; return grp(sc, [[pc(S.rect(len, 13), COL.red, 22)]], x, y, { rot: rot, h: 22, at: at, phase: o.phase }); }
  /** 퍼지는 고리 — 따로 오린 고리를 갈아 끼운다(교체 애니메이션). a0·a1 은 도 단위 */
  function arcs(sc, x, y, radii, a0, a1, at, o) { o = o || {}; var n = radii.length, per = o.per || 3;
    radii.forEach(function (r, i) { [0, 1].forEach(function (v) { grp(sc, [[pc(S.arc(r, o.th || 8, a0 * DEG, a1 * DEG), (o.colors && o.colors[i]) || o.color || COL.amber, 20)]], x, y, { h: 20, at: at, out: o.out, phase: o.phase, noSettle: 1,
      vis: function (tq, step) { var q = Math.floor(step / per); return q % (n + 1) > i && q % 2 === v; } }); }); }); }
  /** 출렁이는 물결 띠 — 위상이 다른 석 장을 갈아 끼운다 */
  function waves(sc, x, y, w, at, o) { o = o || {}; [0, 1, 2].forEach(function (v) { grp(sc, [[pc(S.wave(w, o.amp || 11, o.th || 9, v * TAU / 3, o.cyc), o.color || COL.sig, o.h || 14)]], x, y, { h: o.h || 14, at: at, out: o.out, phase: o.phase, noSettle: 1, rot: o.rot || 0,
    vis: function (tq, step) { return Math.floor(step / 2) % 3 === v && (!o.vis || o.vis(tq, step)); } }); }); }
  /** 찾은 낱말의 때를 차례로(앞 낱말 뒤에서부터) */
  function seqTimes(sc, kws, from) { var t = from || 0, out = []; kws.forEach(function (k) { t = sc.w(k, t + (out.length ? .3 : 0)); out.push(t); }); return out; }

  // ── 소품(글자 없음). 모두 parts 배열을 돌려준다
  var PR = {
    mast: function () { return [[pc(S.rect(7, 96), COL.ink, 14)], [pc(S.poly([[0, -8], [26, 0], [0, 8]]), COL.amber, 14), 4, -38]]; },
    tower: function () { return [[pc(S.poly([[-17, 62], [17, 62], [5, -62], [-5, -62]]), COL.ink, 12)], [pc(S.rect(30, 6), COL.cream, 2), 0, 22], [pc(S.rect(20, 6), COL.cream, 2), 0, -12], [pc(S.circle(8), COL.amber, 12), 0, -68]]; },
    phone: function () { return [[pc(S.rect(46, 80), COL.ink, 12)], [pc(S.rect(34, 54), COL.mist, 2), 0, -5]]; },
    radio: function () { return [[pc(S.rect(6, 46), COL.ink, 12), 26, -44, 18 * DEG], [pc(S.rect(92, 58), COL.amber, 12)], [pc(S.circle(15), COL.cream, 2), -20, 0], [pc(S.rect(26, 7), COL.ink, 2), 22, -9], [pc(S.rect(26, 7), COL.ink, 2), 22, 8]]; },
    router: function () { return [[pc(S.rect(6, 34), COL.ink, 12), -22, -26, -14 * DEG], [pc(S.rect(6, 34), COL.ink, 12), 22, -26, 14 * DEG], [pc(S.rect(84, 30), COL.teal, 12)], [pc(S.circle(4.5), COL.sun, 1), -24, 0], [pc(S.circle(4.5), COL.sun, 1), -8, 0]]; },
    brick: function () { return [[pc(S.rect(7, 38), COL.ink, 12), 10, -62], [pc(S.rect(38, 92), '#3d4a52', 12)], [pc(S.rect(24, 20), COL.mist, 2), 0, -26], [pc(S.rect(24, 34), COL.cream, 2), 0, 16]]; },
    flip: function () { return [[pc(S.rect(40, 44), COL.teal, 12), 0, -36, -8 * DEG], [pc(S.rect(28, 26), COL.mist, 2), 0, -37, -8 * DEG], [pc(S.rect(40, 46), COL.teal, 12), 0, 10], [pc(S.rect(26, 28), COL.cream, 2), 0, 12]]; },
    car: function () { return [[pc(S.rect(5, 44), COL.ink, 12), 34, -52, 14 * DEG], [pc(S.poly([[-74, 20], [74, 20], [74, -4], [42, -8], [24, -36], [-30, -36], [-50, -8], [-74, -2]]), COL.red, 12)], [pc(S.poly([[-24, -10], [18, -10], [8, -28], [-22, -28]]), COL.mist, 2)], [pc(S.circle(15), COL.ink, 12), -42, 22], [pc(S.circle(15), COL.ink, 12), 44, 22]]; },
    person: function (s, color) { s = s || 1; return [[pc(S.poly([[-32 * s, 48 * s], [32 * s, 48 * s], [21 * s, -14 * s], [-21 * s, -14 * s]]), color || COL.sig, 14)], [pc(S.circle(19 * s), '#ecd3ad', 14), 0, -36 * s]]; },
    ship: function (s) { s = s || 1; return [[pc(S.rect(6 * s, 70 * s), COL.ink, 12), -60 * s, -52 * s], [pc(S.rect(17 * s, 36 * s), COL.amber, 12), -32 * s, -40 * s], [pc(S.rect(17 * s, 36 * s), COL.amber, 12), 0, -40 * s], [pc(S.rect(17 * s, 36 * s), COL.amber, 12), 32 * s, -40 * s], [pc(S.rect(124 * s, 22 * s), COL.cream, 12), 0, -12 * s], [pc(S.poly([[-112 * s, 0], [112 * s, 0], [90 * s, 34 * s], [-94 * s, 34 * s]]), COL.ink, 12)]]; },
    plane: function () { return [[pc(S.poly([[-158, -16], [-124, -16], [-150, -70], [-172, -70]]), COL.sig, 12)], [pc(S.poly([[-176, -2], [-146, -19], [118, -19], [160, -10], [178, 2], [160, 12], [118, 19], [-146, 19]]), '#eef2f0', 14)], [pc(S.poly([[-24, 6], [44, 6], [-18, 96], [-58, 96]]), COL.sig, 16)], [pc(S.rect(150, 7), COL.mist, 1), 30, -5]]; },
    house: function (color, s) { s = s || 1; return [[pc(S.rect(120 * s, 78 * s), color || COL.sig, 12)], [pc(S.poly([[-74 * s, 0], [74 * s, 0], [46 * s, -34 * s], [-46 * s, -34 * s]]), COL.ink, 14), 0, -39 * s], [pc(S.rect(26 * s, 40 * s), COL.cream, 2), 0, 19 * s]]; },
    museum: function () { return [[pc(S.rect(230, 112), COL.cream, 12)], [pc(S.poly([[-132, 0], [132, 0], [0, -52]]), COL.ink, 14), 0, -56], [pc(S.rect(22, 84), COL.mist, 2), -70, 8], [pc(S.rect(22, 84), COL.mist, 2), -24, 8], [pc(S.rect(22, 84), COL.mist, 2), 24, 8], [pc(S.rect(22, 84), COL.mist, 2), 70, 8], [pc(S.rect(250, 14), COL.ink, 12), 0, 60]]; },
    doc: function () { return [[pc(S.rect(60, 78), COL.cream, 12)], [pc(S.rect(40, 5), '#8c9aa2', 1), 0, -20], [pc(S.rect(40, 5), '#8c9aa2', 1), 0, -6], [pc(S.rect(28, 5), '#8c9aa2', 1), -6, 8]]; },
    stamp: function () { return [[pc(S.arc(24, 7, 12 * DEG, 348 * DEG), COL.red, 20)], [pc(S.poly([[-12, 0], [-4, 9], [13, -10], [9, -14], [-4, 1], [-8, -4]]), COL.red, 20)]]; },
    magnifier: function () { return [[pc(S.rect(9, 44), COL.ink, 14), 28, 30, -42 * DEG], [pc(S.circle(26), COL.ink, 14)], [pc(S.circle(18), COL.mist, 2)]]; },
    key: function () { return [[pc(S.rect(118, 16), COL.ink, 12), 0, 22], [pc(S.rect(104, 9), COL.amber, 14), 4, 2, -7 * DEG], [pc(S.circle(12), COL.ink, 14), -44, -8], [pc(S.rect(14, 18), COL.ink, 12), 40, 10]]; },
    gap: function () { return [[pc(S.rect(52, 8), COL.ink, 12), -44, 0], [pc(S.circle(12), COL.ink, 12), -16, 0], [pc(S.rect(52, 8), COL.ink, 12), 44, 0], [pc(S.circle(12), COL.ink, 12), 16, 0]]; },
    jar: function () { return [[pc(S.rect(5, 34), COL.ink, 12), 0, -58], [pc(S.circle(9), COL.sun, 12), 0, -78], [pc(S.rect(58, 88), COL.mist, 12)], [pc(S.rect(58, 46), COL.sun, 2), 0, 20], [pc(S.rect(64, 11), COL.ink, 14), 0, -44]]; },
    sun: function () { return [[pc(S.circle(22), COL.sun, 12)], [pc(S.circle(10), '#fbe7a1', 1)]]; },
    coin: function () { return [[pc(S.circle(27), COL.sun, 14)], [pc(S.circle(17), '#f6dc8a', 1)]]; },
    rover: function (s) { s = s || 1; return [[pc(S.rect(7 * s, 50 * s), COL.ink, 14), 30 * s, -46 * s], [pc(S.rect(30 * s, 18 * s), COL.ink, 14), 30 * s, -76 * s], [pc(S.rect(120 * s, 40 * s), COL.cream, 14)], [pc(S.rect(86 * s, 12 * s), COL.sig, 2), -10 * s, -26 * s], [pc(S.circle(17 * s), COL.ink, 14), -46 * s, 28 * s], [pc(S.circle(17 * s), COL.ink, 14), 0, 28 * s], [pc(S.circle(17 * s), COL.ink, 14), 46 * s, 28 * s]]; },
    camera: function () { return [[pc(S.circle(20), COL.ink, 14), -22, -44], [pc(S.circle(20), COL.ink, 14), 22, -44], [pc(S.rect(96, 62), '#3d4a52', 14)], [pc(S.poly([[48, -16], [84, -30], [84, 30], [48, 16]]), COL.ink, 14)], [pc(S.circle(13), COL.mist, 2), -14, 0]]; },
    frame: function () { return [[pc(S.rect(186, 206), COL.ink, 12)], [pc(S.rect(156, 176), COL.cream, 2)]]; },
    hand: function () { return [[pc(S.poly([[-34, -18], [20, -22], [40, -8], [40, 10], [18, 22], [-34, 18]]), '#ecd3ad', 24)], [pc(S.rect(44, 44), COL.sig, 24), -54, 0]]; },
    spark: function (v) { return [[pc(S.poly([[-12, -3], [-4, -9], [1, -1], [10, -7], [5, 5], [-2, 0], [-9, 7]]), v === 1 ? COL.red : COL.sun, 18)]]; }
  };
  /** 불꽃 깜빡임(석 장 교체) */
  function sparks(sc, x, y, at, o) { o = o || {}; [0, 1, 2].forEach(function (v) { grp(sc, PR.spark(v), x, y - 2 * v, { rot: v * 47, h: 18, at: at, phase: o.phase, noSettle: 1, vis: function (tq, step) { return step % 4 !== 3 && step % 3 === v; } }); }); }

  var SC = {};

  // ── 01 체험관 개요
  SC['01-intro'] = function (sc) {
    var at = sc.at, B = at('open', 1);                           // "전파체험관 이야기 시간에…" 에서 건물이 선다
    sc.add({ parts: [[P_(S.poly(spline([[270, 600, 1], [270, 572, 1], [500, 550], [760, 562], [1050, 546], [1330, 570, 1], [1330, 600, 1]]).map(function (p) { return [p[0] - 800, p[1] - 575, p[2]]; })), COL.land, { h: 3 })]], x: 800, y: 575, h: 3, at: .5 });
    var body = P_(S.rect(300, 172), COL.sig, { h: 12 }), roof = P_(S.poly([[-178, 0], [178, 0], [122, -48], [-122, -48]]), COL.ink, { h: 14 });
    var win = function () { return P_(S.rect(58, 48), COL.mist, { h: 2 }); }, door = P_(S.rect(52, 82), COL.cream, { h: 2 });
    sc.add({ parts: [[P_(S.rect(8, 74), COL.ink, { h: 10 }), 0, -166], [body, 0, 0], [roof, 0, -84], [win(), -96, -8], [win(), 96, -8], [door, 0, 45], [P_(S.circle(11), COL.amber, { h: 12 }), 0, -208]], x: 770, y: 476, h: 12, at: B });
    sc.add({ parts: [[P_(S.rect(206, 46), COL.cream, { h: 16 })]], x: 770, y: 420, rot: -1 * DEG, h: 16, at: B + .35, label: { c: 'l-sign', t: '전파체험관' } });
    arcs(sc, 770, 268, [36, 62, 88], -152, -28, B + .6, { th: 9 });
    sc.add({ parts: [[P_(S.tag(320, 132), COL.cream, { h: 22 })]], x: 1140, y: 262, rot: 3 * DEG, h: 22, at: at('docent0', 1, '2020년'), label: { c: 'l-big', t: sc.cue.visual.facts[0].big, sub: sc.cue.visual.facts[0].label } });
    var L = at('docent0', 2, '생활');
    grp(sc, PR.phone(), 1045, 505, { rot: -6, at: L, jit: .7 }); grp(sc, PR.radio(), 1150, 515, { rot: 3, at: L + .42, jit: .7 }); grp(sc, PR.router(), 1256, 528, { rot: -2, at: L + .84, jit: .7 });
    sc.add({ parts: [[P_(S.circle(36), COL.teal, { h: 24 })]], x: 425, y: 250, h: 24, at: at('ask1', 0, '누가'), out: at('docent1'), jit: 1, label: { c: 'l-q', t: '?' } });
    sc.add({ parts: [[P_(S.tag(346, 72), COL.cream, { h: 20 })]], x: 428, y: 250, rot: -2 * DEG, h: 20, at: at('docent1'), label: { c: 'l-kca', t: '한국방송통신전파진흥원' } });
    [['관리하고', '전파 관리', 338, -1.5, 418], ['진흥하고', '방송·통신·전파 진흥', 410, 1.2, 432], ['키우려고', '인력 키우기', 482, -1, 416]].forEach(function (m) {
      sc.add({ parts: [[P_(S.tag(m[1].length > 8 ? 286 : 214, 54), COL.teal, { h: 15 })]], x: m[4], y: m[2], rot: m[3] * DEG, h: 15, at: at('docent1', 1, m[0]), label: { c: 'l-tag', t: m[1] } }); });
  };

  // ── 02 전파의 발견 역사 (앞 무대: 세 사람 → 카메라가 옆으로 → 뒷 무대: 대서양)
  SC['02-history'] = function (sc) {
    var at = sc.at, TR = sc.TR = 1500, tS = at('docent2', 1) - .15;
    sc.cam = function (tq) { return TR * smooth((tq - tS) / 1.25); };
    sc.add({ parts: [[P_(S.circle(64), COL.teal, { h: 26 })]], x: 800, y: 350, h: 26, at: at('open', 1, '누가'), out: at('docent0'), jit: 1, label: { c: 'l-q2', t: '?' } });
    sc.add({ parts: [[P_(S.rect(150, 66), COL.cream, { h: 10 })]], x: 660, y: 200, rot: -2 * DEG, h: 10, at: at('docent0', 0, '발명'), label: { c: 'l-word', t: '발명' } });
    strike(sc, 660, 200, 196, -13, at('docent0', 0, '아니라'));
    sc.add({ parts: [[P_(S.rect(188, 80), COL.amber, { h: 18 })]], x: 905, y: 197, rot: 2.5 * DEG, h: 18, at: at('docent0', 0, '발견'), label: { c: 'l-word2', t: '발견' } });
    var CX = [500, 800, 1100];
    [['머리로', '예언', -1.4, COL.sig], ['실험으로', '증명', .8, COL.red], ['통신에', '통신', -.7, COL.teal]].forEach(function (c, i) {
      var t = at('docent0', 1, c[0]);
      sc.add({ parts: [[P_(S.rect(236, 292), COL.cream, { h: 8 })]], x: CX[i], y: 416, rot: c[2] * DEG, h: 8, at: t });
      sc.add({ x: CX[i], y: 304, rot: c[2] * DEG, h: 8, at: t, label: { c: 'l-role', t: c[1] } }).el.firstChild.style.color = c[3];
    });
    sc.add({ parts: [[P_(S.poly([[8, -27], [-11, 3], [2, 3], [-8, 27], [13, -7], [0, -7]]), COL.sun, { h: 12 })]], x: 440, y: 392, rot: 4 * DEG, h: 12, at: at('docent1', 0, '전기와'), jit: .6 });
    sc.add({ parts: [[P_(S.poly([[-21, -23], [-7, -23], [-7, 8], [7, 8], [7, -23], [21, -23], [21, 23], [-21, 23]]), COL.red, { h: 12 })], [P_(S.rect(14, 10), COL.cream, { h: 1 }), -14, -18], [P_(S.rect(14, 10), COL.cream, { h: 1 }), 14, -18]], x: 500, y: 392, rot: -3 * DEG, h: 12, at: at('docent1', 0, '자기,'), jit: .6 });
    grp(sc, PR.sun(), 560, 392, { at: at('docent1', 0, '빛이'), jit: .6 });
    waves(sc, 500, 462, 176, at('docent1', 0, '전자기파가'));
    sc.add({ parts: [[P_(S.tag(216, 46), COL.sig, { h: 16 })]], x: 500, y: 528, rot: -1.5 * DEG, h: 16, at: at('docent1', 0), label: { c: 'l-tag', t: '맥스웰 · 이론' } });
    var H0 = at('docent1', 1, '실험으로');
    grp(sc, PR.gap(), 800, 384, { at: at('docent1', 1) }); sparks(sc, 800, 384, H0);
    sc.add({ parts: [[P_(S.arc(27, 8, 110 * DEG, 430 * DEG), COL.ink, { h: 12 })]], x: 800, y: 462, h: 12, at: H0 + .5 });
    sc.add({ parts: [[P_(S.poly([[-6, -2], [-1, -6], [2, 0], [6, -3], [2, 4], [-3, 2]]), COL.sun, { h: 16 })]], x: 800, y: 489, h: 16, at: H0 + .9, noSettle: 1, vis: function (tq, step) { return (step + 1) % 4 < 2; } });
    sc.add({ parts: [[P_(S.tag(216, 46), COL.red, { h: 16 })]], x: 800, y: 528, rot: 1.2 * DEG, h: 16, at: at('docent1', 1, '헤르츠'), label: { c: 'l-tag', t: '헤르츠 · 증명' } });
    var M0 = at('docent2', 0, '무선전신');
    sc.add({ parts: [[P_(S.rect(8, 132), COL.ink, { h: 12 })], [P_(S.rect(64, 7), COL.ink, { h: 12 }), 0, -44], [P_(S.rect(40, 7), COL.ink, { h: 12 }), 0, -22], [P_(S.poly([[-30, 0], [30, 0], [18, -16], [-18, -16]]), COL.teal, { h: 12 }), 0, 66]], x: 1100, y: 420, h: 12, at: M0 });
    arcs(sc, 1136, 362, [20, 38], -50, 50, M0 + .3, { th: 7 }); arcs(sc, 1064, 362, [20, 38], 130, 230, M0 + .3, { th: 7 });
    sc.add({ parts: [[P_(S.tag(246, 46), COL.teal, { h: 16 })]], x: 1100, y: 528, rot: -1 * DEG, h: 16, at: at('docent2', 0), label: { c: 'l-tag', t: '마르코니 · 무선전신' } });
    // 뒷 무대(phase 1): 대서양. 지도는 실제 해안선이 아니라 찢은 종이로 양식화했다
    var T1 = tS - .1, ph = 1, off = function (V, cx, cy) { return V.map(function (p) { return [p[0] - cx, p[1] - cy, p[2]]; }); };
    sc.add({ parts: [[P_(S.rect(1010, 372), COL.sea, { h: 2, decorate: function (c) { c.strokeStyle = 'rgba(255,255,255,.34)'; c.lineWidth = 2; c.setLineDash([10, 12]); for (var y = -120; y <= 120; y += 80) { c.beginPath(); c.moveTo(-500, y); c.bezierCurveTo(-200, y - 26, 200, y + 26, 500, y); c.stroke(); } } })]], x: 800, y: 404, h: 2, at: T1, phase: ph, noSettle: 1 });
    sc.add({ parts: [[P_(off(spline([[296, 220, 1], [420, 236], [468, 318], [432, 402], [478, 498], [412, 590, 1], [296, 590, 1]]), 385, 405), COL.land, { torn: 1.5, h: 9 })]], x: 385, y: 405, h: 9, at: T1, phase: ph, noSettle: 1 });
    sc.add({ parts: [[P_(off(spline([[1304, 220, 1], [1192, 234], [1142, 302], [1172, 392], [1126, 470], [1182, 590, 1], [1304, 590, 1]]), 1215, 405), COL.land, { torn: 1.5, h: 9 })]], x: 1215, y: 405, h: 9, at: T1, phase: ph, noSettle: 1 });
    grp(sc, PR.mast(), 1215, 290, { h: 14, at: T1, phase: ph, noSettle: 1 }); grp(sc, PR.mast(), 385, 290, { h: 14, at: T1, phase: ph, noSettle: 1 });
    sc.add({ parts: [[P_(S.rect(190, 46), COL.cream, { h: 18 })]], x: 800, y: 548, rot: -1.5 * DEG, h: 18, at: at('docent2', 1, '1901년', .05), phase: ph, label: { c: 'l-date', t: '1901. 12. 12' } });
    tagL(sc, '폴듀 (영국)', 1212, 384, { rot: 1.5, at: at('docent2', 1, '폴듀'), phase: ph });
    var s0 = at('docent2', 1, '모스'), s1 = at('docent2', 1, '뉴펀들랜드에서'), NS = 11;
    for (var i = 0; i < NS; i++) { (function (i) { var u = (i + 1) / (NS + 1), q = function (a, c, b) { return (1 - u) * (1 - u) * a + 2 * u * (1 - u) * c + u * u * b; };
      var x = q(1215, 800, 385), y = q(240, 128, 240), ang = Math.atan2(2 * (1 - u) * (128 - 240) + 2 * u * (240 - 128), 2 * (1 - u) * (800 - 1215) + 2 * u * (385 - 800));
      sc.add({ parts: [[i % 3 === 1 ? P_(S.rect(26, 10), COL.cream, { h: 16 }) : P_(S.circle(7.5), COL.cream, { h: 16 })]], x: x, y: y, rot: ang, h: 16, at: lerp(s0, s1, i / (NS - 1)), phase: ph, jit: .8 }); })(i); }
    sc.add({ parts: [[P_(S.rect(276, 76), COL.cream, { h: 22 })]], x: 800, y: 318, rot: 1.5 * DEG, h: 22, at: at('docent2', 1, '약 3,500'), phase: ph, label: { c: 'l-km', t: '약 3,500km' } });
    cap(sc, '대서양', 800, 448, at('docent2', 1, '대서양'), 'l-sea', ph);
    tagL(sc, '뉴펀들랜드', 388, 384, { rot: -1.5, at: at('docent2', 1, '뉴펀들랜드에서'), phase: ph });
    arcs(sc, 385, 238, [22, 40, 58], -160, -20, at('docent2', 1, '받았대요'), { phase: ph });
    sc.add({ parts: [[P_(S.rect(196, 40), COL.amber, { h: 22 })]], x: 392, y: 440, rot: 2 * DEG, h: 22, at: at('docent2', 2, '영국 식민지'), phase: ph, label: { c: 'l-name', t: '그때는 영국 식민지' } });
  };

  // ── 03 전파 이론: 할핀에 꽂은 종이 다이얼 + 주파수에 따라 갈아 끼우는 물결
  SC['03-theory'] = function (sc) {
    var w = sc.w, at = sc.at, D = sc.cue.visual, C0 = 299792458;
    grp(sc, PR.sun(), 372, 222, { at: w('빛과'), jit: .6 });
    waves(sc, 640, 222, 430, w('전자기파의'), { cyc: 4 });
    grp(sc, PR.mast(), 905, 214, { at: w('퍼져 나가요') });
    var d0 = at('docent1'), d1 = sc.U('docent1').t1, f0 = w('100메가헤르츠');
    var E = function (tq) { if (tq < d0) return 3; if (tq < f0) return lerp(3, 12.3, smooth((tq - d0) / (d1 - d0))); return lerp(12.3, 8, smooth((tq - f0) / 2.4)); };
    var ANG = function (e) { return lerp(-130, 130, (e - 3) / 9.3) * DEG; };
    var units = ['Hz', 'kHz', 'MHz', 'GHz', 'THz'], num = function (x) { return Number(x.toPrecision(1)).toLocaleString('en-US', { maximumFractionDigits: 6 }); };
    var fF = function (e) { var k = clamp(Math.floor(e / 3 + 1e-9), 0, 4); return num(Math.pow(10, e - 3 * k)) + units[k]; };
    var fL = function (e) { var m = C0 / Math.pow(10, e); return m >= 1000 ? num(m / 1000) + 'km' : m >= 1 ? num(m) + 'm' : m >= .01 ? num(m * 100) + 'cm' : num(m * 1000) + 'mm'; };
    grp(sc, [[pc(S.circle(112), COL.cream, 10, { decorate: function (c) { c.strokeStyle = 'rgba(22,56,77,.5)'; c.lineWidth = 3; for (var i = 0; i <= 31; i++) { var a = lerp(-130, 130, i / 31) * DEG - Math.PI / 2, r0 = i % 10 === 0 ? 84 : 94; c.beginPath(); c.moveTo(r0 * Math.cos(a), r0 * Math.sin(a)); c.lineTo(104 * Math.cos(a), 104 * Math.sin(a)); c.stroke(); } } })]], 520, 440, { at: d0 });
    grp(sc, [[pc(S.poly([[-10, 12], [10, 12], [0, -88]]), COL.red, 18)], [pc(S.circle(12), COL.sun, 2)]], 520, 440, { h: 18, at: d0 + .25, pose: function (tq) { return { rot: ANG(E(tq)), jit: 0 }; } });
    D.ticks.forEach(function (tk) { var a = ANG(tk.e) - Math.PI / 2, r = tk.row2 ? 176 : 142;
      cap(sc, tk.label, 520 + r * Math.cos(a), 440 + r * Math.sin(a), tk.row2 ? f0 : d0 + .35, tk.row2 ? 'l-fm' : 'l-tick'); });
    grp(sc, [[pc(S.tag(350, 66), COL.cream, 18)]], 1040, 300, { rot: -1, h: 18, at: d0 + .3, label: { c: 'l-read', t: '', dyn: function (tq) { return D.fLabel + ' ' + fF(E(tq)); } } });
    grp(sc, [[pc(S.tag(350, 66), COL.cream, 18)]], 1046, 384, { rot: 1, h: 18, at: at('docent2'), label: { c: 'l-read', t: '', dyn: function (tq) { return D.lLabel + ' ' + fL(E(tq)); } } });
    // 물결: 주파수 구간마다 따로 오린 띠(구간 7 × 위상 2)를 갈아 끼운다 — 그림의 물결 수는 느낌이다(실제 비율 아님)
    [1, 1.5, 2.5, 4, 6, 9, 13].forEach(function (cy, i) { [0, 1].forEach(function (v) {
      grp(sc, [[pc(S.wave(340, 17, 8, v * Math.PI, cy), COL.sig, 14)]], 1040, 478, { h: 14, at: d0 + .5, noSettle: 1, vis: function (tq, step) { return clamp(Math.round((E(tq) - 3) / 9.3 * 6), 0, 6) === i && Math.floor(step / 2) % 2 === v; } }); }); });
    grp(sc, [[pc(S.tag(900, 52), COL.teal, 16)]], 800, 566, { rot: .4, h: 16, at: w('빛의 속도를'), label: { c: 'l-form', t: D.formula } });
  };

  // ── 04 전파이야기 체험
  SC['04-morse'] = function (sc) {
    var w = sc.w, F = sc.cue.visual.facts, X = [480, 800, 1120];
    [['모스 부호,', '모스 부호', PR.key, 0], ['헤르츠의', '헤르츠의 전파 실험', PR.gap, 0], ['라이덴 병까지', '라이덴 병', PR.jar, 6]].forEach(function (m, i) { var t = w(m[0]);
      grp(sc, [[pc(S.rect(238, 226), COL.cream, 8)]], X[i], 300, { rot: [-1.2, .7, -.6][i], h: 8, at: t });
      grp(sc, m[2](), X[i], 276 + m[3], { at: t + .25 }); cap(sc, m[1], X[i], 384, t + .25); });
    var s0 = w('SOS도'), pat = [0, 0, 0, 1, 1, 1, 0, 0, 0], x = 606;
    pat.forEach(function (d, i) { var ww = d ? 34 : 14; grp(sc, [[d ? pc(S.rect(34, 12), COL.ink, 14) : pc(S.circle(7.5), COL.ink, 14)]], x + ww / 2, 458, { h: 14, at: s0 + i * .13, jit: .6 }); x += ww + 16; });
    fact(sc, F[0], 500, 542, { w: 400, rot: -1, at: w('1865년') });
    fact(sc, F[1], 1100, 542, { w: 400, rot: 1, at: s0 + .4 });
    sparks(sc, 800, 276, w('불꽃 간극에'));
    sparks(sc, 1120, 196, w('방전'));
  };

  // ── 05 기증자
  SC['05-donor'] = function (sc) {
    var w = sc.w, St = sc.cue.visual.steps, T = seqTimes(sc, St.map(function (s) { return s.k; })), X = [480, 800, 1120];
    strip(sc, 330, 1270, 232, T[0] - .2);
    St.forEach(function (s, i) { stepTag(sc, s, X[i], 232, { w: 300, rot: [-1, .8, -.6][i], at: T[i] }); });
    grp(sc, PR.person(1.25, '#eef2f0').concat([[pc(S.rect(22, 7), COL.red, 1), 0, 18], [pc(S.rect(7, 22), COL.red, 1), 0, 18]]), 390, 476, { at: w('의사예요') });
    grp(sc, PR.radio(), 520, 506, { rot: 2, at: w('아마추어 무선') }); arcs(sc, 546, 440, [18, 34, 50], -150, -30, w('아마추어 무선') + .3, { th: 7 });
    var c0 = w('수집을'), pile = [[PR.phone, 680, 512, -8], [PR.radio, 760, 530, 4], [PR.brick, 835, 500, 6], [PR.router, 905, 540, -3], [PR.key, 790, 452, -5], [PR.jar, 925, 462, 5]];
    pile.forEach(function (p, i) { grp(sc, p[0](), p[1], p[2], { rot: p[3], at: c0 + i * .28, jit: .6 }); });
    grp(sc, PR.museum(), 1160, 478, { at: w('기증해') }); grp(sc, PR.mast(), 1160, 350, { at: w('문을 열었어요') });
  };

  // ── 06 주파수 대역 (스펙트럼 → 카메라 이동 → 전파가 가는 세 가지 길 → 돌아와 ITU)
  SC['06-bands'] = function (sc) {
    var w = sc.w, at = sc.at, F = sc.cue.visual.facts, TR = sc.TR = 1500, tA = at('docent1') - .15, tB = at('docent2') - .15;
    sc.cam = function (tq) { return TR * (smooth((tq - tA) / 1.2) - smooth((tq - tB) / 1.2)); };
    var cols = ['#2d6f9e', '#2c8aa6', '#3ba39a', '#7fb069', '#d9b23c', '#d98f2b', '#cf6a32', '#bd4a3a'], b0 = w('주파수에 따라');
    cols.forEach(function (c, i) { grp(sc, [[pc(S.rect(116, 50), c, 10)]], 352 + i * 128, 338, { rot: (i % 2 ? .8 : -.8), h: 10, at: b0 + i * .14 }); });
    fact(sc, F[0], 424, 226, { w: 322, rot: -1, at: w('초장파는') });
    fact(sc, F[1], 1176, 226, { w: 322, rot: 1, at: w('밀리미터파는') });
    fact(sc, F[2], 800, 226, { w: 330, at: w('100킬로미터') });
    waves(sc, 470, 436, 380, w('아주 낮은'), { cyc: 1.5, amp: 20 });
    waves(sc, 1130, 436, 380, w('아주 높은'), { cyc: 10, amp: 14, color: COL.red });
    fact(sc, { big: 'ITU', label: '국제전기통신연합' }, 800, 540, { w: 360, at: w('ITU가') });
    // 뒷 무대
    var ph = 1, T1 = tA - .1, G = spline([[290, 600, 1], [290, 544, 1], [560, 538], [700, 476], [800, 444], [900, 476], [1040, 538], [1310, 544, 1], [1310, 600, 1]]).map(function (p) { return [p[0] - 800, p[1] - 522, p[2]]; });
    grp(sc, [[pc(S.rect(1000, 54), COL.mist, 6, { torn: 1.6 })]], 800, 204, { h: 6, at: T1, phase: ph, noSettle: 1 });
    grp(sc, [[pc(G, COL.land, 6)]], 800, 522, { h: 6, at: T1, phase: ph, noSettle: 1 });
    grp(sc, PR.tower(), 372, 480, { at: T1, phase: ph, noSettle: 1 }); grp(sc, PR.house(COL.sig, .7), 1232, 512, { at: T1, phase: ph, noSettle: 1 });
    var hill = function (x) { return 520 - 96 * Math.exp(-Math.pow((x - 800) / 185, 2)); }, i, t;
    t = w('언덕을'); for (i = 0; i < 13; i++) dot(sc, 420 + i * 64, hill(420 + i * 64) - 4, t + i * .13, { color: COL.amber, phase: ph });
    t = w('곧게'); for (i = 0; i < 6; i++) dot(sc, 410 + i * 56, 428, t + i * .13, { color: COL.red, phase: ph });
    t = w('전리층에서') - .5; for (i = 0; i < 13; i++) { var u = i / 12, x = lerp(396, 1208, u), y = u < .5 ? lerp(410, 240, u * 2) : lerp(240, 468, (u - .5) * 2); dot(sc, x, y, t + i * .14, { color: COL.sig, phase: ph }); }
    cap(sc, '전리층', 800, 204, w('전리층에서'), 'l-iono', ph);
  };

  // ── 07 해상무선통신 (낮의 가로 도식 + 연표)
  SC['07-maritime'] = function (sc) {
    var w = sc.w, St = sc.cue.visual.steps, T = seqTimes(sc, St.map(function (s) { return s.k; })), X = [362, 581, 800, 1019, 1238];
    waves(sc, 800, 322, 860, .6, { cyc: 6, color: COL.sea, th: 13, h: 6 });
    grp(sc, PR.ship(1), 520, 270, { rot: -9, at: w('타이타닉이') });
    arcs(sc, 452, 196, [20, 38, 56], -160, -20, w('구조 신호를'), { th: 7 });
    var c0 = w('카르파티아호가');
    grp(sc, PR.ship(.62), 1040, 284, { at: c0, noSettle: 1, pose: function (tq) { return { dx: 230 * (1 - smooth((tq - c0) / 1.8)), jit: .5 }; } });
    strip(sc, 290, 1310, 468, T[0] - .2);
    St.forEach(function (s, i) { dot(sc, X[i], 468, T[i], { color: COL.amber, r: 10, jit: 0 }); stepTag(sc, s, X[i], i % 2 ? 540 : 398, { w: 212, hh: 96, rot: [-1, .8, -.5, 1, -.8][i], at: T[i] + .1 }); });
    var m0 = w('모스 부호가'); grp(sc, PR.key(), 1250, 268, { rot: 4, at: m0 }); strike(sc, 1250, 268, 150, -18, m0 + .6);
  };

  // ── 08 항공무선통신
  SC['08-aviation'] = function (sc) {
    var w = sc.w, F = sc.cue.visual.facts;
    grp(sc, [[pc(S.rect(160, 104), COL.ink, 12)], [pc(S.rect(128, 50), COL.mist, 2), 0, -18], [pc(S.rect(128, 6), COL.land, 1), 0, -8], [pc(S.circle(15), COL.sun, 14), 0, 30], [pc(S.rect(44, 7), COL.sun, 14), 0, 30]], 384, 512, { rot: -2, at: w('시뮬레이터가') });
    grp(sc, PR.plane(), 800, 318, { rot: -3, at: w('항공기'), jit: .5 });
    fact(sc, F[0], 430, 226, { w: 330, rot: -1.5, at: w('무선전화') });
    fact(sc, F[1], 1172, 226, { w: 330, rot: 1.5, at: w('트랜스폰더') });
    fact(sc, F[2], 806, 470, { w: 350, rot: -.6, at: w('비상위치표지') });
    var g0 = w('관제기관과'); grp(sc, PR.tower(), 1250, 492, { at: g0 }); arcs(sc, 1250, 416, [20, 38, 56], 150, 250, g0 + .3, { th: 7 }); arcs(sc, 986, 318, [20, 38], -40, 40, g0 + .3, { th: 7 });
    var c0 = w('1944년'); grp(sc, PR.doc(), 1040, 548, { rot: -5, at: c0 }); tagL(sc, '1944년 시카고 협약', 1190, 572, { rot: 1, at: c0 + .3 });
  };

  // ── 09 특별교류전시 (액자 속만 바뀐다 — 전시품 이름은 지어내지 않는다)
  SC['09-special-exhibit'] = function (sc) {
    var w = sc.w, F = sc.cue.visual.facts, t0 = w('특별 전시품을'), tc = w('그때그때'), sC = Math.round(tc * 12), X = [480, 800, 1120];
    var art = [function () { return [[pc(S.circle(46), COL.sun, 6)]]; }, function () { return [[pc(S.poly([[-56, 44], [56, 44], [0, -52]]), COL.teal, 6)]]; }, function () { return [[pc(S.wave(130, 22, 16, 0, 1.5), COL.sig, 6)]]; }, function () { return [[pc(S.rect(86, 86), COL.red, 6)]]; }];
    X.forEach(function (x, i) { grp(sc, PR.frame(), x, 318, { rot: [-1, .6, -.8][i], at: t0 + i * .3 });
      [0, 1, 2, 3].forEach(function (v) { grp(sc, art[v](), x, 318, { rot: v === 3 ? 12 : 0, h: 6, at: t0 + i * .3 + .25, noSettle: 1, vis: function (tq, step) { return (step < sC ? i : i + 1 + Math.floor((step - sC) / 10)) % 4 === v; } }); }); });
    var u0 = w('유관기관과'); grp(sc, PR.house(COL.teal, .8), 350, 540, { at: u0 }); grp(sc, PR.house(COL.amber, .8), 1250, 540, { at: u0 + .3 });
    grp(sc, [[pc(S.poly([[-40, -9], [14, -9], [14, -22], [42, 0], [14, 22], [14, 9], [-40, 9]]), COL.teal, 14)]], 500, 528, { at: u0 + .6, jit: .6 });
    grp(sc, [[pc(S.poly([[40, -9], [-14, -9], [-14, -22], [-42, 0], [-14, 22], [-14, 9], [40, 9]]), COL.amber, 14)]], 1100, 552, { at: u0 + .9, jit: .6 });
    fact(sc, F[0], 800, 538, { w: 400, at: w('일정 기간') });
  };

  // ── 10 아마추어 무선
  SC['10-ham'] = function (sc) {
    var w = sc.w, at = sc.at, St = sc.cue.visual.steps, a0 = w('아마추어업무를');
    grp(sc, PR.mast(), 292, 432, { at: a0 }); arcs(sc, 292, 378, [20, 38, 56], -150, -30, a0 + .4, { th: 7 });
    grp(sc, PR.person(1.15, COL.teal), 372, 490, { at: a0 + .2 }); grp(sc, PR.radio(), 492, 522, { rot: 2, at: a0 + .5 });
    var m0 = w('금전적'); grp(sc, PR.coin(), 470, 286, { at: m0 }); strike(sc, 470, 286, 92, -40, m0 + .5);
    var p0 = w('상호통신'); grp(sc, PR.person(1.15, COL.amber), 650, 490, { at: p0 }); arcs(sc, 650, 410, [18, 32], -150, -30, p0 + .3, { th: 7 });
    var f = at('docent1', 1), T = [w('무선설비,', f), w('무선국,', f), w('무선종사자예요', f)];
    St.forEach(function (s, i) { stepTag(sc, s, 1090, 236 + i * 112, { w: 440, hh: 92, rot: [-1, .8, -.6][i], at: T[i] }); });
    var n0 = w('통신망이 끊긴'); grp(sc, PR.tower(), 790, 470, { at: w('재난구호') }); strike(sc, 790, 462, 110, -35, n0);
  };

  // ── 11 사물인터넷
  SC['11-iot'] = function (sc) {
    var w = sc.w, F = sc.cue.visual.facts, HX = 800, HY = 330, n0 = w('사물을 서로'), l0 = w('연결해');
    var N = [[500, 250, PR.phone, .7], [650, 196, PR.router, .9], [950, 196, PR.radio, .7], [1100, 250, function () { return PR.house(COL.amber, .55); }, 1], [1110, 420, function () { return PR.car(); }, .55], [940, 462, function () { return [[pc(S.circle(22), COL.sun, 12)], [pc(S.rect(14, 16), COL.ink, 12), 0, 26]]; }, 1], [660, 462, PR.camera, .5], [490, 420, PR.brick, .7]];
    N.forEach(function (n, i) { var dx = HX - n[0], dy = HY - n[1], d = Math.hypot(dx, dy); grp(sc, [[pc(S.rect(d - 96, 6), COL.ink, 3)]], (HX + n[0]) / 2, (HY + n[1]) / 2, { rot: Math.atan2(dy, dx) / DEG, h: 3, at: l0 + i * .12 }); });
    N.forEach(function (n, i) { grp(sc, [[pc(S.circle(40), COL.cream, 10)]], n[0], n[1], { h: 10, at: n0 + i * .16 }); grp(sc, [[pc(S.circle(n[3] * 9), [COL.sig, COL.teal, COL.amber, COL.red][i % 4], 12)]], n[0], n[1], { at: n0 + i * .16 + .1, jit: .5 }); });
    grp(sc, [[pc(S.circle(50), COL.sig, 16)], [pc(S.circle(24), COL.mist, 2)]], HX, HY, { h: 16, at: w('글로벌 인프라') });
    var s0 = w('스스로'); N.forEach(function (n, i) { arcs(sc, n[0], n[1] - 40, [14, 26], -150, -30, s0 + i * .1, { th: 6, per: 2 + i % 3 }); });
    fact(sc, F[0], 470, 548, { w: 410, rot: -1, at: w('백만 대') });
    fact(sc, F[1], 1130, 548, { w: 410, rot: 1, at: w('밀리초') });
  };

  // ── 12 KCA 멀티미디어실
  SC['12-multimedia'] = function (sc) {
    var w = sc.w, at = sc.at, F = sc.cue.visual.facts, s0 = w('콘텐츠를'), f = at('docent1');
    grp(sc, [[pc(S.rect(396, 250), COL.ink, 12)], [pc(S.rect(20, 40), COL.ink, 10), 0, 142], [pc(S.rect(150, 12), COL.ink, 10), 0, 164]], 800, 318, { at: w('멀티미디어실') });
    [[COL.sig, function () { return pc(S.circle(34), COL.sun, 2); }], [COL.amber, function () { return pc(S.poly([[-60, 40], [-10, -34], [20, 6], [44, -18], [70, 40]]), COL.teal, 2); }], [COL.teal, function () { return pc(S.wave(200, 18, 12, 0, 2), COL.cream, 2); }]].forEach(function (p, v) {
      grp(sc, [[pc(S.rect(362, 216), p[0], 2)], [p[1]()]], 800, 318, { h: 2, at: s0, noSettle: 1, vis: function (tq, step) { return Math.floor(step / 14) % 3 === v; } }); });
    for (var i = 0; i < 7; i++) grp(sc, [[pc(S.circle(24), '#3d4a52', 10)]], 590 + i * 70, 548, { h: 10, at: w('공간이에요') + i * .08 });
    fact(sc, F[0], 414, 262, { w: 322, rot: -1.5, at: w('한국방송통신전파진흥원은', f) });
    fact(sc, F[1], 1188, 262, { w: 322, rot: 1.5, at: w('제작 지원은', f) });
    var r0 = w('전파 관리와', f); grp(sc, PR.tower(), 414, 470, { at: r0 }); arcs(sc, 414, 394, [20, 38, 56], -150, -30, r0 + .3, { th: 7 });
    grp(sc, PR.camera(), 1180, 470, { rot: -3, at: w('방송통신 진흥도', f) });
  };

  // ── 13 크로마키 (초록 종이를 걷어 내면 그 자리에 다른 장면이 들어온다)
  SC['13-chromakey'] = function (sc) {
    var w = sc.w, at = sc.at, St = sc.cue.visual.steps, CX = 660, CY = 372;
    var tG = at('docent0') + .2, tK = w('골라'), tT = w('투명하게'), tC = w('다른 화면을'), tSF = w('공상과학'), tD = w('전혀 다른'), sD = Math.round(tD * 12);
    var sel = function (tq, step) { if (tq < tC) return -1; if (tq < tSF) return 0; if (tq < tD) return 1; return Math.floor((step - sD) / 12) % 2; };
    grp(sc, [[pc(S.rect(520, 326), COL.ink, 6)]], CX, CY, { h: 6, at: tG - .1 });
    grp(sc, [[pc(S.rect(480, 290), COL.mist, 4)], [pc(S.circle(34), COL.sun, 2), -150, -80], [pc(S.circle(26), COL.cream, 2), 90, -70], [pc(S.circle(34), COL.cream, 2), 126, -76], [pc(S.circle(24), COL.cream, 2), 164, -66], [pc(S.poly(spline([[-240, 145, 1], [-240, 60, 1], [-120, 10], [0, 70], [130, 30], [240, 80, 1], [240, 145, 1]])), COL.land, 2)]], CX, CY, { h: 4, at: tC, vis: function (tq, step) { return sel(tq, step) === 0; } });
    grp(sc, [[pc(S.rect(480, 290), '#14283a', 4)], [pc(S.circle(56), COL.red, 2), 130, -40], [pc(S.arc(78, 7, 160 * DEG, 380 * DEG), COL.sun, 2), 130, -40, -20 * DEG]].concat([[-190, -100], [-120, 60], [-40, -90], [20, 90], [-170, 20], [200, 100], [60, -30]].map(function (p) { return [pc(S.circle(5), COL.sun, 1), p[0], p[1]]; })), CX, CY, { h: 4, at: tSF, noSettle: 1, vis: function (tq, step) { return sel(tq, step) === 1; } });
    grp(sc, [[pc(S.rect(480, 290), '#4fa35a', 5)]], CX, CY, { h: 5, at: tG, out: tT });
    grp(sc, PR.person(1.9, COL.amber), CX, CY + 54, { h: 22, at: tG + .3 });
    grp(sc, PR.camera(), 330, 540, { rot: -6, at: w('다른 카메라로') });
    grp(sc, [[pc(S.arc(30, 9, 20 * DEG, 340 * DEG), '#4fa35a', 20)]], 1010, 250, { at: tK, out: tT, jit: .6 });
    [tK, tT, tC].forEach(function (t, i) { stepTag(sc, St[i], 1168, 250 + i * 112, { w: 320, hh: 92, rot: [-1, .8, -.6][i], at: t }); });
  };

  // ── 14 이동통신 (연표 위에 그 시대의 전화기)
  SC['14-mobile'] = function (sc) {
    var w = sc.w, St = sc.cue.visual.steps, T = seqTimes(sc, St.map(function (s) { return s.k; })), X = [350, 575, 800, 1025, 1250];
    strip(sc, 280, 1320, 432, T[0] - .2);
    var prop = [PR.car, PR.brick, PR.flip, PR.phone, PR.phone];
    St.forEach(function (s, i) { dot(sc, X[i], 432, T[i], { color: COL.amber, r: 10, jit: 0 });
      grp(sc, [[pc(S.circle(74), COL.cream, 8)]], X[i], 300, { h: 8, at: T[i] }); grp(sc, prop[i](), X[i], i ? 302 : 300, { rot: [0, -6, 4, -4, 5][i], at: T[i] + .2, jit: .5 });
      stepTag(sc, s, X[i], 522, { w: 208, hh: 98, rot: [-1, .8, -.5, 1, -.8][i], at: T[i] + .1 }); });
    grp(sc, PR.coin(), 440, 216, { at: w('400만 원') });
    arcs(sc, 1250, 240, [18, 32, 46], -150, -30, w('세계 최초로'), { th: 7 });
  };

  // ── 15 전자파 측정 (멀어질수록 옅어지는 고리)
  SC['15-emf'] = function (sc) {
    var w = sc.w, F = sc.cue.visual.facts, s0 = w('세기는');
    grp(sc, PR.tower(), 340, 430, { at: w('전자파 인체보호기준을') });
    arcs(sc, 340, 362, [60, 118, 176, 234, 292, 350], -34, 34, s0, { th: 10, per: 2, colors: ['#c9821a', '#d39a3f', '#dbaf64', '#e2c38a', '#e7d2a8', '#ebdcc0'] });
    var m0 = w('어디서 쟀는지가');
    grp(sc, [[pc(S.rect(60, 92), COL.ink, 14)], [pc(S.rect(44, 34), COL.mist, 2), 0, -18], [pc(S.rect(6, 30), COL.ink, 14), 0, -60]], 470, 520, { at: m0, jit: .5 });
    grp(sc, [[pc(S.rect(60, 92), COL.ink, 14)], [pc(S.rect(44, 34), COL.mist, 2), 0, -18], [pc(S.rect(6, 30), COL.ink, 14), 0, -60]], 720, 520, { at: m0 + .5, jit: .5 });
    var l0 = w('1등급과'); ['#4fa35a', '#2c8aa6', '#d9b23c', '#bd4a3a'].forEach(function (c, i) { grp(sc, [[pc(S.rect(74, 50), c, 16)]], 960 + i * 100, 480, { rot: [-3, 2, -2, 3][i], h: 16, at: l0 + i * .32 }); });
    fact(sc, F[0], 1110, 236, { w: 430, rot: -1, at: w('네 가지') });
    fact(sc, F[1], 1110, 360, { w: 430, rot: 1, at: w('1등급은') });
    grp(sc, PR.doc(), 1040, 556, { rot: -6, at: w('국제기구의') }); grp(sc, PR.doc(), 1180, 556, { rot: 5, at: w('국제암연구소는') });
  };

  // ── 16 무선국 검사 (검사 넷에 도장이 하나씩)
  SC['16-inspection'] = function (sc) {
    var w = sc.w, at = sc.at, St = sc.cue.visual.steps, X = [400, 667, 933, 1200], T = seqTimes(sc, St.map(function (s) { return s.k; }), at('docent1'));
    grp(sc, PR.tower(), 350, 248, { at: w('무선국은') }); grp(sc, PR.doc(), 480, 244, { rot: -5, at: w('허가는') }); grp(sc, PR.magnifier(), 590, 240, { at: w('검사가') });
    St.forEach(function (s, i) { stepTag(sc, s, X[i], 452, { w: 238, hh: 150, rot: [-1.2, .8, -.6, 1][i], at: T[i] }); grp(sc, PR.stamp(), X[i] + 86, 396, { rot: [-14, 10, -8, 12][i], h: 20, at: T[i] + .7 }); });
    grp(sc, PR.house(COL.sig, 1), 1190, 258, { at: w('한국방송통신전파진흥원에') });
    grp(sc, [[pc(S.tag(210, 76), COL.cream, 20)]], 950, 250, { rot: -2, h: 20, at: w('1981년'), label: { c: 'l-km', t: '1981년' } });
  };

  // ── 17 원격 무선조종 차량 (탐사차 → 카메라 이동 → 지구·달·화성 사이의 지연)
  SC['17-rover'] = function (sc) {
    var w = sc.w, at = sc.at, F = sc.cue.visual.facts, TR = sc.TR = 1500, tA = at('docent1') - .15;
    sc.cam = function (tq) { return TR * smooth((tq - tA) / 1.25); };
    var G = spline([[280, 600, 1], [280, 530, 1], [470, 500], [680, 540], [900, 512], [1120, 546], [1320, 520, 1], [1320, 600, 1]]).map(function (p) { return [p[0] - 800, p[1] - 550, p[2]]; });
    grp(sc, [[pc(G, '#c98a62', 5, { torn: 1 })]], 800, 550, { h: 5, at: .5 });
    grp(sc, PR.rover(1.15), 790, 452, { rot: -2, at: w('탐사로봇을'), jit: .8 });
    grp(sc, [[pc(S.poly([[-22, 14], [22, 14], [12, -12], [-10, -16]]), '#9a6a4a', 10)]], 470, 478, { at: w('표면을') }); grp(sc, [[pc(S.poly([[-30, 16], [30, 16], [14, -18], [-18, -12]]), '#9a6a4a', 10)]], 1130, 510, { at: w('표면을') + .2 });
    grp(sc, [[pc(S.poly(spline([[0, -26, 1], [16, 4], [0, 22], [-16, 4]])), COL.sig, 16)]], 520, 330, { at: w('물이나'), jit: .8 });
    grp(sc, [[pc(S.circle(20), COL.land, 16)], [pc(S.circle(8), '#7f9b6a', 1), 4, -3]], 800, 290, { at: w('생명체'), jit: .8 });
    grp(sc, [[pc(S.poly([[0, -28], [20, -4], [10, 24], [-12, 22], [-20, -6]]), COL.teal, 16)]], 1080, 330, { at: w('광물자원의'), jit: .8 });
    // 뒷 무대
    var ph = 1, T1 = tA - .1;
    grp(sc, [[pc(S.circle(74), COL.sig, 10)], [pc(S.poly(spline([[-40, -30], [0, -46], [26, -20], [4, 6], [-30, 0]])), COL.land, 1)], [pc(S.poly(spline([[10, 22], [40, 14], [44, 40], [18, 48]])), COL.land, 1)]], 384, 350, { h: 10, at: T1, phase: ph, noSettle: 1 });
    grp(sc, [[pc(S.circle(52), '#c4573a', 10)], [pc(S.circle(13), '#a8452e', 1), -14, -10], [pc(S.circle(8), '#a8452e', 1), 18, 16]], 1236, 318, { h: 10, at: T1, phase: ph, noSettle: 1 });
    var d0 = w('지구와 화성'), d1 = sc.U('docent1').s[0].t1, i;
    for (i = 0; i < 12; i++) dot(sc, lerp(476, 1166, i / 11), lerp(346, 320, i / 11), lerp(d0, d1, i / 11), { color: COL.amber, phase: ph });
    fact(sc, F[0], 820, 226, { w: 420, rot: -1, at: w('3분에서'), phase: ph });
    grp(sc, PR.rover(.6), 1236, 420, { at: w('화성 로버는'), phase: ph, jit: .6 });
    var mT = w('달은');
    grp(sc, [[pc(S.circle(30), '#cfcabd', 10)], [pc(S.circle(7), '#b3ad9f', 1), -8, -6], [pc(S.circle(5), '#b3ad9f', 1), 10, 8]], 610, 500, { h: 10, at: mT, phase: ph });
    [0, 1, 2].forEach(function (k) { dot(sc, lerp(452, 574, (k + 1) / 4), lerp(404, 482, (k + 1) / 4), mT + .5, { color: COL.red, phase: ph, jit: 0 }).vis = function (tq, step) { var q = Math.floor(step / 2) % 4; return (q < 3 ? q : 1) === k; }; });
    fact(sc, F[1], 900, 520, { w: 380, rot: 1, at: w('2초에서'), phase: ph });
  };

  // ── 18 과학 원리 실험 도구 (손이 다가가면 물결이 촘촘해진다)
  SC['18-science'] = function (sc) {
    var w = sc.w, F = sc.cue.visual.facts, t0 = w('테레민이라는'), tH = w('손이 가까워지면'), tE = sc.U('docent1').t1;
    var near = function (tq) { return tq < tH ? 0 : .5 - .5 * Math.cos((tq - tH) * 1.5); };
    grp(sc, [[pc(S.rect(7, 220), COL.ink, 14), 124, -160], [pc(S.arc(40, 8, 60 * DEG, 300 * DEG), COL.ink, 14), -178, 0], [pc(S.rect(290, 104), '#b5793a', 12)], [pc(S.circle(12), COL.cream, 2), -80, 0], [pc(S.circle(12), COL.cream, 2), -40, 0], [pc(S.rect(14, 60), '#8a5a2a', 10), -110, 80], [pc(S.rect(14, 60), '#8a5a2a', 10), 110, 80]], 856, 470, { at: t0 });
    grp(sc, PR.hand(), 1190, 330, { rot: 180, h: 24, at: w('손이 가까워지면') - .4, noSettle: 1, pose: function (tq) { return { dx: -130 * near(tq), jit: .6 }; } });
    [3, 5, 8, 12].forEach(function (cy, i) { [0, 1].forEach(function (v) { grp(sc, [[pc(S.wave(330, 16, 8, v * Math.PI, cy), COL.sig, 14)]], 780, 216, { h: 14, at: t0 + .5, noSettle: 1, vis: function (tq, step) { return clamp(Math.round(near(tq) * 3), 0, 3) === i && Math.floor(step / 2) % 2 === v; } }); }); });
    fact(sc, F[0], 440, 300, { w: 350, rot: -1.5, at: w('1920년') });
    fact(sc, F[1], 440, 426, { w: 350, rot: 1, at: w('1928년') });
  };

  // ── 19 마무리 (오늘의 줄기 + 색종이)
  SC['19-closing'] = function (sc) {
    var w = sc.w, at = sc.at, St = sc.cue.visual.steps, X = [400, 667, 933, 1200], T = [w('발견에서'), w('실용화로'), w('방송과'), w('관리와')];
    strip(sc, 320, 1280, 384, T[0] - .2);
    St.forEach(function (s, i) { grp(sc, [[pc(S.circle(78), COL.cream, 8)]], X[i], 290, { h: 8, at: T[i] }); dot(sc, X[i], 384, T[i], { color: COL.amber, r: 10, jit: 0 }); stepTag(sc, s, X[i], 478, { w: 246, hh: 100, rot: [-1.2, .8, -.6, 1][i], at: T[i] + .1 }); });
    grp(sc, PR.gap(), X[0], 290, { at: T[0] + .2 }); sparks(sc, X[0], 290, T[0] + .5);
    grp(sc, PR.mast(), X[1], 300, { at: T[1] + .2 }); arcs(sc, X[1], 250, [18, 32, 46], -150, -30, T[1] + .5, { th: 7 });
    grp(sc, PR.phone(), X[2], 292, { rot: -5, at: T[2] + .2 });
    grp(sc, PR.doc(), X[3] - 8, 290, { rot: -4, at: T[3] + .2 }); grp(sc, PR.stamp(), X[3] + 26, 312, { rot: 10, h: 20, at: T[3] + .7 });
    var c0 = w('고맙습니다.', at('after')), r = rand(1919), cols = [COL.sig, COL.teal, COL.amber, COL.red, COL.sun, COL.land];
    for (var i = 0; i < 46; i++) grp(sc, [[pc(S.rect(18, 10), cols[i % 6], 18)]], 290 + r() * 1020, 170 + r() * 420, { rot: r() * 180, h: 18, at: c0 + i * .05, jit: 1.2 });
  };
