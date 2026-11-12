// ═════════════════════════════════════════════ 설명선 배치 — 순수 함수(빌더가 template.html 의 /*__LAYOUT__*/ 자리에 넣는다)
// 가중 등위 회귀(PAVA)로 라벨 높이를 정한다. aimotion 148 「분해도」(https://github.com/kstost/cokacmotion, MIT © 2026 kstost)의
// pava·layoutLabels 를 옮겨, 라벨마다 높이가 다른 경우(DOM 라벨은 설명 줄이 한 줄 또는 두 줄)로 넓혔다.
//
// 왜 PAVA 인가: 라벨을 기준점의 화면 y 로 정렬하고 각 라벨 y 를 자기 기준점에 가장 가깝게(가중 최소제곱) 두되 이웃끼리 최소 간격
// s_i 를 지켜야 한다. G_i = Σ_{k<i} s_k, z_i = y_i − G_i 로 바꾸면 간격 조건이 "z 가 줄지 않는다" 가 되어 답이 a_i − G_i 의
// 등위 회귀다(정확해). 위아래 경계는 회귀 결과를 자르는 것으로 정확히 지켜진다. 입력이 매끄럽게 움직이면 결과도 연속이라
// 카메라가 돌아도 라벨이 튀지 않는다. 라벨 순서 = 기준점 순서라서, 기준점 → 버스선 → 대각선 → 라벨로 꺾는 지시선은 엇갈리지 않는다.
var LAYOUT = (function () {
  'use strict';
  /** 가중 이웃 위반 묶기: z 에 가중 최소제곱으로 가장 가까운 비감소 수열 */
  function pava(z, w) {
    var v = [], wt = [], n = [], i, b, k;
    for (i = 0; i < z.length; i++) {
      v.push(z[i]); wt.push(w[i]); n.push(1);
      while (v.length > 1 && v[v.length - 2] > v[v.length - 1]) {
        var v2 = v.pop(), w2 = wt.pop(), n2 = n.pop(), v1 = v.pop(), w1 = wt.pop(), n1 = n.pop();
        v.push((v1 * w1 + v2 * w2) / (w1 + w2)); wt.push(w1 + w2); n.push(n1 + n2);
      }
    }
    var out = [];
    for (b = 0; b < v.length; b++) for (k = 0; k < n[b]; k++) out.push(v[b]);
    return out;
  }
  /**
   * 한 열의 라벨 높이를 정한다. items: [{ay, w, above, below}] — ay 기준점 화면 y, w 가중치(강조 부품은 크게),
   * above/below 라벨의 기준선(이름 줄 가운데)에서 위·아래 끝까지. 결과는 각 item 의 y(기준선)에 적는다.
   * 정렬은 ay 로, 같으면 원래 순서로(안정) — 같은 높이의 두 기준점이 매 프레임 자리를 바꾸지 않게.
   * 넘치면(열 높이보다 라벨이 많으면) 위에서부터 쌓고 over 를 참으로 돌려준다(조용히 겹치지 않게 — 호출 쪽이 경고한다).
   */
  function column(items, top, bot, gap) {
    var idx = items.map(function (_, i) { return i; });
    idx.sort(function (a, b) { return items[a].ay - items[b].ay || a - b; });
    var s = idx.map(function (i) { return items[i]; }), G = [0], i;
    for (i = 1; i < s.length; i++) G.push(G[i - 1] + s[i - 1].below + gap + s[i].above);
    if (!s.length) return { order: [], over: false };
    var z = pava(s.map(function (it, j) { return it.ay - G[j]; }), s.map(function (it) { return it.w; }));
    var lo = top + s[0].above, hi = bot - s[s.length - 1].below - G[G.length - 1], over = hi < lo;
    s.forEach(function (it, j) { var v = over ? lo : Math.min(Math.max(z[j], lo), hi); it.y = v + G[j]; });
    return { order: idx, over: over };
  }
  return { pava: pava, column: column };
})();
if (typeof module !== 'undefined' && module.exports) module.exports = LAYOUT;
