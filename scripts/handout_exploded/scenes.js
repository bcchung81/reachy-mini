  // ═════════════════════════════════════════════ 큐별 부품 모양 (빌더가 template.html 의 /*__SCENES__*/ 자리에 넣는다)
  // 모양만 짓는다 — 시각·글자·움직임은 없다. 어디에 놓이고 언제 어떻게 풀리는지는 전부 `tables.yaml` 의 부품 표가 정한다
  // (표의 `shape` 이름이 여기 함수를 가리킨다). 부품마다 자기 중심이 원점, 긴 축이 y 다.
  // 점등 훅: 모양 함수가 g.userData.lamp = true 로 표시하면 그 부품의 lamp 재질이 '기억해 두기' 뒤에 켜지고,
  // g.userData.emit = Vector3(부품 좌표) 를 주면 그 자리에서 전파 고리가 퍼진다.

  var SHAPES = {};

  // ── 01 체험관 개요 — 전시관 단면(기초 · 기둥 넷 · 바닥판 · 전시층 · 지붕 + 안테나)
  SHAPES['01-intro'] = {
    foundation: function (K, M) {           // 7.2 × 0.7 × 5.0 — 설립 근거(무거운 판)
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(7.2, .7, 5.0, .12), M.slate));
      var plate = K.mesh(K.rbox(1.6, .42, .08, .03), M.steel); plate.position.set(0, 0, 2.52); g.add(plate);   // 머릿돌 자리(글자 없음)
      [-1, 1].forEach(function (s) { var r = K.mesh(K.rbox(6.4, .06, .06, .02), M.ink); r.position.set(0, .2 * s, 2.5); g.add(r); });
      return g;
    },
    pillar: function (K, M) {                // 높이 2.2 — 받침·주두가 넓은 기둥
      var g = new THREE.Group();
      g.add(K.mesh(K.lathe([[0, -1.1], [.46, -1.1, .04], [.46, -.95, .04], [.3, -.84, .12], [.3, .84, .12], [.46, .95, .04], [.46, 1.1, .04], [0, 1.1]], 48), M.porcelain));
      var band = K.mesh(K.cyl(.315, .315, .16, 48), M.rule); band.position.y = .3; g.add(band);
      return g;
    },
    floor: function (K, M) {                 // 6.8 × 0.45 × 4.6 — 기관(바닥판)
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(6.8, .45, 4.6, .1), M.rule));
      var top = K.mesh(K.rbox(6.1, .06, 3.9, .02), M.mist); top.position.y = .25; g.add(top);
      for (var i = -2; i <= 2; i++) { var s = K.mesh(K.rbox(.05, .07, 3.9, .02), M.muted, false); s.position.set(i * 1.2, .27, 0); g.add(s); }
      return g;
    },
    hall: function (K, M) {                  // 높이 2.0 — 유리 띠가 둘린 전시층(점등 때 창이 켜진다)
      var g = new THREE.Group(); g.userData.lamp = true;
      [-1, 1].forEach(function (s) { var r = K.mesh(K.rbox(5.9, .2, 4.1, .05), M.muted); r.position.y = .9 * s; g.add(r); });
      var glaze = K.mesh(K.rbox(5.6, 1.6, 3.8, .03), M.lamp); g.add(glaze);
      for (var i = 0; i <= 7; i++) { var x = -2.8 + i * .8;
        [-1, 1].forEach(function (s) { var m = K.mesh(K.rbox(.07, 1.6, .07, .02), M.muted, false); m.position.set(x, 0, 1.9 * s); g.add(m); }); }
      for (i = 0; i <= 4; i++) { var z = -1.9 + i * .95;
        [-1, 1].forEach(function (s) { var m = K.mesh(K.rbox(.07, 1.6, .07, .02), M.muted, false); m.position.set(2.8 * s, 0, z); g.add(m); }); }
      var door = K.mesh(K.rbox(1.1, 1.3, .08, .02), M.ink); door.position.set(0, -.15, 1.92); g.add(door);
      return g;
    },
    roof: function (K, M) {                  // 7.0 × 0.36 × 4.9 지붕 + 안테나 받침
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(7.0, .36, 4.9, .1), M.porcelain));
      var lip = K.mesh(K.rbox(6.4, .1, 4.3, .03), M.rule); lip.position.y = .2; g.add(lip);
      var base = K.mesh(K.rbox(1.6, .4, 1.2, .06), M.slate); base.position.y = .38; g.add(base);
      return g;
    },
    mast: function (K, M) {                  // 높이 2.4 — 끝에서 전파 고리가 퍼진다
      var g = new THREE.Group();
      g.add(K.mesh(K.lathe([[0, -1.2], [.16, -1.2, .03], [.16, -1.05, .03], [.08, -.95, .05], [.05, 1.1], [0, 1.1]], 24), M.steel));
      [[-.5, .26], [.05, .2], [.55, .14]].forEach(function (r) { var t = K.mesh(new THREE.TorusGeometry(r[1], .028, 10, 40), M.steel); t.rotation.x = Math.PI / 2; t.position.y = r[0]; g.add(t); });
      var tip = K.mesh(K.ball(.11), M.ink); tip.position.y = 1.16; g.add(tip);
      g.userData.emit = new THREE.Vector3(0, 1.16, 0);
      return g;
    }
  };

  // ── 02 전파의 발견 역사 — 실용 무선전신 한 벌을 세 사람의 일로(받침 · 불꽃 쌍극자 · 송신 장치) + 1785년 판 + 수신 측
  SHAPES['02-history'] = {
    plate: function (K, M) {                 // 1785년 판 — 지름 4.6, 두께 0.22, 테두리의 두 전하 구
      var g = new THREE.Group();
      g.add(K.mesh(K.lathe([[0, -.11], [2.3, -.11, .05], [2.3, .11, .05], [0, .11]], 72), M.muted));
      [-1, 1].forEach(function (s) { var b = K.mesh(K.ball(.17), M.steel); b.position.set(2.48 * s, 0, 0); g.add(b);
        var st = K.mesh(K.cyl(.035, .035, .2, 12), M.steel); st.rotation.z = Math.PI / 2; st.position.set(2.32 * s, 0, 0); g.add(st); });
      return g;
    },
    pedestal: function (K, M) {              // 이론(받침) — 옆면을 감는 사인 파동 고리
      var g = new THREE.Group();
      g.add(K.mesh(K.lathe([[0, -.6], [1.9, -.6, .08], [1.9, -.42, .08], [1.62, -.3, .2], [1.62, .45, .1], [1.72, .6, .06], [0, .6]], 72), M.slate));
      var pts = []; for (var i = 0; i < 240; i++) { var a = i / 240 * Math.PI * 2; pts.push(new THREE.Vector3(1.67 * Math.cos(a), .06 + .16 * Math.sin(8 * a), 1.67 * Math.sin(a))); }
      g.add(K.mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts, true), 480, .045, 8, true), M.steel));
      var top = K.mesh(K.lathe([[0, -.03], [1.45, -.03, .02], [1.45, .03, .02], [0, .03]], 64), M.ink); top.position.y = .6; g.add(top);
      return g;
    },
    dipole: function (K, M) {                // 실험 — 절연 기둥 위 가로 막대 둘, 가운데 불꽃 간극, 끝의 큰 구
      var g = new THREE.Group(); g.userData.lamp = true;
      g.add(K.mesh(K.lathe([[0, -.78], [.62, -.78, .04], [.62, -.66, .04], [.2, -.58, .08], [.2, .38], [0, .38]], 48), M.ink));
      var ribs = []; for (var i = 0; i < 6; i++) ribs.push([.17 + (i % 2 ? 0 : .07), -.5 + i * .16]);
      g.add(K.mesh(K.lathe([[0, -.55]].concat(ribs.map(function (r) { return [r[0], r[1], .03]; })).concat([[.16, .45], [0, .45]]), 40), M.porcelain));
      [-1, 1].forEach(function (s) {
        var rod = K.mesh(K.cyl(.05, .05, 1.7, 16), M.steel); rod.rotation.z = Math.PI / 2; rod.position.set(s * .98, .55, 0); g.add(rod);
        var end = K.mesh(K.ball(.42), M.steel); end.position.set(s * 1.98, .55, 0); g.add(end);
        var knob = K.mesh(K.ball(.11), M.steel); knob.position.set(s * .15, .55, 0); g.add(knob);
      });
      var spark = K.mesh(K.ball(.07), M.lamp, false); spark.position.set(0, .55, 0); g.add(spark);
      return g;
    },
    ring: function (K, M) {                  // 실험의 짝 — 틈이 있는 고리(받는 쪽), 작은 받침 위에 선다
      var g = new THREE.Group();
      var t = K.mesh(new THREE.TorusGeometry(.72, .045, 12, 64, Math.PI * 2 - .22), M.steel); t.rotation.z = Math.PI / 2 + .11; t.position.y = .3; g.add(t);
      // 고리 평면(xy)에서 틈은 맨 위(각 π/2 ± 0.11) — 틈 양 끝에 작은 구
      [-1, 1].forEach(function (s) { var a = Math.PI / 2 + .11 * s, b = K.mesh(K.ball(.07), M.steel); b.position.set(.72 * Math.cos(a), .3 + .72 * Math.sin(a), 0); g.add(b); });
      var post = K.mesh(K.cyl(.05, .05, .5, 12), M.porcelain); post.position.y = -.6; g.add(post);
      var foot = K.mesh(K.lathe([[0, -.9], [.38, -.9, .03], [.38, -.82, .03], [0, -.82]], 32), M.ink); g.add(foot);
      return g;
    },
    cabinet: function (K, M) {               // 실용화 — 송신 장치(앞 패널·다이얼·급전 애자). 가운데 표시등이 점등 때 켜진다
      var g = new THREE.Group(); g.userData.lamp = true;
      g.add(K.mesh(K.rbox(2.6, 1.5, 1.7, .1), M.slate));
      var panel = K.mesh(K.rbox(2.2, 1.0, .06, .03), M.ink); panel.position.set(0, -.05, .86); g.add(panel);
      [-.6, 0, .6].forEach(function (x, i) { var d = K.mesh(K.cyl(.17, .17, .08, 32), i === 1 ? M.lamp : M.steel); d.rotation.x = Math.PI / 2; d.position.set(x, .08, .92); g.add(d); });
      var ins = K.mesh(K.lathe([[0, -.22], [.16, -.22, .02], [.12, -.1], [.17, 0, .03], [.11, .1], [.15, .2, .02], [0, .22]], 24), M.porcelain); ins.position.set(.75, .97, -.2); g.add(ins);
      return g;
    },
    key: function (K, M) {                   // 모스 부호를 치는 손잡이(전건 모양 — 라벨은 대사의 말로)
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(1.15, .12, .62, .04), M.muted));
      var piv = K.mesh(K.cyl(.07, .07, .4, 16), M.steel); piv.rotation.x = Math.PI / 2; piv.position.set(.25, .16, 0); g.add(piv);
      var lever = K.mesh(K.rbox(.95, .07, .12, .03), M.steel); lever.position.set(-.05, .22, 0); lever.rotation.z = -.08; g.add(lever);
      var knob = K.mesh(K.lathe([[0, -.06], [.16, -.06, .03], [.16, .05, .03], [0, .07]], 32), M.ink); knob.position.set(-.5, .3, 0); g.add(knob);
      var contact = K.mesh(K.cyl(.05, .05, .1, 12), M.steel); contact.position.set(-.45, .1, 0); g.add(contact);
      return g;
    },
    mast: function (K, M) {                  // 보내는 쪽 안테나 — 높이 3.0, 애자 셋, 위 가로대
      var g = new THREE.Group();
      g.add(K.mesh(K.lathe([[0, -1.5], [.2, -1.5, .03], [.2, -1.38, .03], [.08, -1.28, .05], [.055, 1.4], [0, 1.4]], 24), M.steel));
      [-.7, .1, .9].forEach(function (y) { var d = K.mesh(K.lathe([[0, -.05], [.2, -.05, .03], [.2, .05, .03], [0, .05]], 24), M.porcelain); d.position.y = y; g.add(d); });
      var arm = K.mesh(K.rbox(1.3, .07, .07, .02), M.steel); arm.position.y = 1.36; g.add(arm);
      [-1, 1].forEach(function (s) { var b = K.mesh(K.ball(.07), M.ink); b.position.set(.65 * s, 1.36, 0); g.add(b); });
      g.userData.emit = new THREE.Vector3(0, 1.4, 0);
      return g;
    },
    receiver: function (K, M) {              // 받는 쪽 — 작은 수신 장치와 짧은 안테나
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(1.0, .6, .7, .06), M.slate));
      var face = K.mesh(K.rbox(.8, .36, .04, .02), M.ink); face.position.set(0, 0, .36); g.add(face);
      var m = K.mesh(K.cyl(.035, .045, 1.4, 12), M.steel); m.position.set(.3, 1.0, 0); g.add(m);
      var arm = K.mesh(K.rbox(.7, .05, .05, .02), M.steel); arm.position.set(.3, 1.68, 0); g.add(arm);
      return g;
    }
  };

  // ── 03 전파 이론 — 주파수 다이얼 한 대를 정의의 층으로(받침 하우징 · 물결 · 눈금 고리 · 유리 덮개 · 손잡이 · 머리판 · 가운데 축)
  // 눈금 각도: e = log10(주파수 Hz). 카드 다이얼과 같은 눈금(1kHz·1MHz·1GHz·1THz = e 3·6·9·12)과 끝 멈춤쇠(3,000GHz = e 12.477)를
  // 왼쪽 뒤 → 앞 → 오른쪽으로 270° 에 늘어놓는다. 멈춤쇠가 오른쪽 가장자리(카메라에서 고리의 오른쪽 끝)에 오게 해서 "ITU 전파규칙" 설명선의
  // 기준점 바로 옆에 보이게 했다. 바늘은 FM 라디오 100MHz(e 8 — 카드가 "맞추기" 단추로 고르는 값)를 가리킨다. 글자는 없다
  var DIAL = function (e) { return Math.PI * 1.25 - (e - 2.5) / 10.5 * Math.PI * 1.5; };
  SHAPES['03-theory'] = {
    spindle: function (K, M) {               // 가운데 축 = 눈금 막대(길이 3.0, 0.25 마다 색이 바뀌는 자) — 움직이지 않는 기준. 끝에서 전파 고리가 퍼진다
      var g = new THREE.Group(); g.userData.lamp = true;
      for (var i = 0; i < 12; i++) { var s = K.mesh(K.cyl(.075, .075, .25, 24), i % 2 ? M.porcelain : M.ink); s.position.y = -1.375 + i * .25; g.add(s); }
      var collar = K.mesh(K.lathe([[0, -.06], [.16, -.06, .02], [.16, .06, .02], [0, .06]], 32), M.steel); collar.position.y = -1.44; g.add(collar);
      var tip = K.mesh(K.ball(.11), M.lamp); tip.position.y = 1.58; g.add(tip);
      g.userData.emit = new THREE.Vector3(0, 1.6, 0);
      return g;
    },
    housing: function (K, M) {               // 받침 하우징 — 속이 빈 원통(지름 4.6, 높이 0.8). 안에 물결이 들어 있다. 다리 넷
      var g = new THREE.Group();
      g.add(K.mesh(K.lathe([[0, -.4], [2.3, -.4, .06], [2.3, .4, .05], [2.1, .4, .03], [2.1, -.26, .05], [0, -.26]], 72), M.porcelain));
      // 띠는 열린 원통으로 — 닫힌 원통이면 윗면 뚜껑이 하우징 속(물결)을 덮는다
      var band = K.mesh(new THREE.CylinderGeometry(2.318, 2.318, .12, 72, 1, true), M.rule); band.position.y = -.05; g.add(band);
      var inner = K.mesh(K.cyl(2.07, 2.07, .02, 72), M.mist, false); inner.position.y = -.25; g.add(inner);
      for (var i = 0; i < 4; i++) { var a = Math.PI / 4 + i * Math.PI / 2, f = K.mesh(K.rbox(.5, .14, .5, .05), M.slate); f.position.set(1.6 * Math.cos(a), -.46, 1.6 * Math.sin(a)); g.add(f); }
      return g;
    },
    wave: function (K, M) {                  // 물결 — 세운 사인 곡선 세 주기(파장 1.0, 진폭 0.2)를 받침 띠 위에. 점등 때 켜진다
      var g = new THREE.Group(); g.userData.lamp = true;
      var pts = []; for (var i = 0; i <= 180; i++) { var x = -1.5 + 3 * i / 180; pts.push(new THREE.Vector3(x, .2 * Math.sin(2 * Math.PI * x), 0)); }
      g.add(K.mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 360, .045, 10, false), M.lamp));
      var rail = K.mesh(K.rbox(3.3, .07, .34, .03), M.ink); rail.position.y = -.27; g.add(rail);
      [-1.5, 1.5].forEach(function (x) { var post = K.mesh(K.cyl(.025, .025, .27, 10), M.steel); post.position.set(x, -.135, 0); g.add(post); });
      return g;
    },
    scale: function (K, M) {                 // 눈금 고리 — 10배마다 눈금 하나(셋째마다 큰 눈금)와 흰 끝 멈춤쇠(3,000GHz)
      var g = new THREE.Group();
      g.add(K.mesh(K.lathe([[1.95, -.07], [2.45, -.07, .03], [2.45, .07, .03], [1.95, .07, .03], [1.95, -.07]], 96), M.ink));
      for (var e = 3; e <= 12; e++) { var big = e % 3 === 0, a = DIAL(e), t = K.mesh(K.rbox(.05, big ? .14 : .08, big ? .3 : .18, .015), M.steel, false);
        t.position.set(2.24 * Math.cos(a), .07 + (big ? .07 : .04), 2.24 * Math.sin(a)); t.rotation.y = Math.PI / 2 - a; g.add(t); }
      var a1 = DIAL(12.477), stop = K.mesh(K.rbox(.2, .24, .38, .04), M.porcelain); stop.position.set(2.2 * Math.cos(a1), .17, 2.2 * Math.sin(a1)); stop.rotation.y = Math.PI / 2 - a1; g.add(stop);
      return g;
    },
    face: function (K, M) {                  // 유리 덮개 — 얇은 유리판과 금속 테
      var g = new THREE.Group();
      g.add(K.mesh(K.cyl(1.9, 1.9, .04, 72), M.glass, false));
      g.add(K.mesh(K.lathe([[1.84, -.05], [1.96, -.05, .015], [1.96, .05, .015], [1.84, .05, .015], [1.84, -.05]], 72), M.steel));
      return g;
    },
    knob: function (K, M) {                  // 손잡이 — 넓은 치마 + 홈 판 손잡이. 치마에서 흰 바늘이 FM 라디오 100MHz 눈금 쪽으로 나온다
      var g = new THREE.Group();
      g.add(K.mesh(K.lathe([[0, -.32], [.74, -.32, .04], [.74, -.2, .04], [.6, -.12, .06], [.52, .26, .06], [.38, .32, .03], [0, .32]], 64), M.slate));
      for (var i = 0; i < 20; i++) { var a = i / 20 * Math.PI * 2, r = K.mesh(K.rbox(.05, .3, .08, .02), M.steel, false); r.position.set(.565 * Math.cos(a), .07, .565 * Math.sin(a)); r.rotation.y = Math.PI / 2 - a; g.add(r); }
      var b = DIAL(8), needle = K.mesh(K.rbox(.06, .05, 1.0, .02), M.porcelain); needle.position.set(1.22 * Math.cos(b), -.27, 1.22 * Math.sin(b)); needle.rotation.y = Math.PI / 2 - b; g.add(needle);
      return g;
    },
    cap: function (K, M) {                   // 머리판 — 축이 지나가는 고리판(가운데 구멍)과 안쪽 테
      var g = new THREE.Group();
      g.add(K.mesh(K.lathe([[.13, -.05], [.5, -.05, .03], [.5, .05, .03], [.13, .05, .02], [.13, -.05]], 48), M.steel));
      var r = K.mesh(new THREE.TorusGeometry(.32, .022, 10, 48), M.ink); r.rotation.x = Math.PI / 2; r.position.y = .05; g.add(r);
      return g;
    }
  };

  // ── 04 체험 세 장치 — 체험대 · 전건(→ 점·선 판 → 점 타일) · 라이덴 병 · 룸코르프 유도코일 · 1미터 쌍극자(02 의 모양을 다시 쓴다)
  // 점·선 판의 무늬는 글자가 아니라 길이 규칙만 보인다: 점 = 1칸, 선 = 3칸, 같은 글자 안 간격 = 1칸(대사 "선은 점 셋")
  function morseRow(K, M, g, units, z, u) {   // units: 1 = 점, 3 = 선 — 칸 u 로 왼쪽부터 늘어놓는다
    var x = -.8;
    units.forEach(function (n) { var m = n === 1 ? K.mesh(K.cyl(u * .45, u * .45, .03, 16), M.ink, false) : K.mesh(K.rbox(u * n, .03, u * .9, .01), M.ink, false);
      m.position.set(x + u * n / 2, .05, z); g.add(m); x += u * (n + 1); });
  }
  SHAPES['04-morse'] = {
    bench: function (K, M) {                 // 체험대 — 상판 6.6 × 0.3 × 2.8, 앞 띠, 다리 넷
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(6.6, .3, 2.8, .08), M.porcelain));
      var strip = K.mesh(K.rbox(6.3, .08, .04, .02), M.rule, false); strip.position.set(0, 0, 1.41); g.add(strip);
      [[-1, -1], [-1, 1], [1, -1], [1, 1]].forEach(function (s) { var l = K.mesh(K.rbox(.22, 1.0, .22, .04), M.slate); l.position.set(3.0 * s[0], -.65, 1.2 * s[1]); g.add(l); });
      return g;
    },
    key: function (K, M) {                   // 전건 모양 — 받침판 · 축 · 지렛대 · 손잡이 · 접점 · 뒤 단자 둘
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(1.5, .16, .8, .05), M.slate));
      var piv = K.mesh(K.cyl(.09, .09, .5, 16), M.steel); piv.rotation.x = Math.PI / 2; piv.position.set(.35, .2, 0); g.add(piv);
      var lever = K.mesh(K.rbox(1.25, .09, .16, .03), M.steel); lever.position.set(-.05, .3, 0); lever.rotation.z = -.07; g.add(lever);
      var knob = K.mesh(K.lathe([[0, -.08], [.22, -.08, .04], [.22, .07, .04], [0, .09]], 32), M.ink); knob.position.set(-.62, .42, 0); g.add(knob);
      var contact = K.mesh(K.cyl(.06, .06, .14, 12), M.steel); contact.position.set(-.55, .14, 0); g.add(contact);
      [-1, 1].forEach(function (s) { var t = K.mesh(K.cyl(.07, .07, .12, 16), M.steel); t.position.set(.6, .14, .26 * s); g.add(t); });
      return g;
    },
    code: function (K, M) {                  // 점·선 판(1.9 × 0.8) — 세 줄의 점·선 무늬(글자 없음, 길이 규칙만)
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(1.9, .08, .8, .03), M.porcelain));
      morseRow(K, M, g, [1, 3], -.24, .095); morseRow(K, M, g, [3, 1, 1, 1], 0, .095); morseRow(K, M, g, [3, 1, 3, 1], .24, .095);
      return g;
    },
    dots: function (K, M) {                  // 점 타일(1.8 × 0.45, 칸 u) — 위 줄 점 셋, 아래 줄 선 하나(같은 길이) + 오른쪽 일곱 칸 간격(양 끝 세운 탭)
      var g = new THREE.Group(), u = .125, x0 = -.85;
      g.add(K.mesh(K.rbox(1.8, .06, .45, .02), M.rule));
      for (var i = 0; i < 13; i++) { var t = K.mesh(K.rbox(.014, .012, .08, .004), M.muted, false); t.position.set(x0 + i * u + u / 2, .035, .19); g.add(t); }
      for (i = 0; i < 3; i++) { var d = K.mesh(K.rbox(u * .8, .08, u * .8, .02), M.ink); d.position.set(x0 + u / 2 + i * u, .07, -.08); g.add(d); }
      var dash = K.mesh(K.rbox(u * 3 - .012, .08, u * .8, .02), M.ink); dash.position.set(x0 + u * 1.5, .07, .07); g.add(dash);
      var g0 = x0 + u * 4;                   // 일곱 칸 간격: 넷째 칸부터 열한째 칸까지
      [g0, g0 + u * 7].forEach(function (x) { var tab = K.mesh(K.rbox(.03, .2, .26, .01), M.slate); tab.position.set(x, .13, 0); g.add(tab); });
      var span = K.mesh(K.rbox(u * 7, .018, .025, .006), M.steel, false); span.position.set(g0 + u * 3.5, .16, 0); g.add(span);
      return g;
    },
    jar: function (K, M) {                   // 라이덴 병 — 유리병 · 안팎 금속박 · 나무 뚜껑 · 놋쇠 막대와 꼭지 구 · 안쪽 사슬
      var g = new THREE.Group();
      var inner = K.mesh(new THREE.CylinderGeometry(.44, .44, .72, 40, 1, true), M.muted, false); inner.position.y = -.26; g.add(inner);
      var chain = K.mesh(K.cyl(.015, .015, 1.0, 8), M.steel, false); chain.position.y = .22; g.add(chain);
      g.add(K.mesh(K.lathe([[0, -.7], [.5, -.7, .06], [.5, .45, .04], [.42, .6, .04], [.42, .68, .02], [0, .68]], 48), M.glass, false));
      var foil = K.mesh(new THREE.CylinderGeometry(.515, .515, .8, 48, 1, true), M.steel); foil.position.y = -.26; g.add(foil);
      var lid = K.mesh(K.lathe([[0, -.04], [.46, -.04, .02], [.46, .04, .02], [0, .04]], 40), M.slate); lid.position.y = .72; g.add(lid);
      var rod = K.mesh(K.cyl(.035, .035, .7, 12), M.steel); rod.position.y = 1.1; g.add(rod);
      var ball = K.mesh(K.ball(.12), M.steel); ball.position.y = 1.48; g.add(ball);
      return g;
    },
    coil: function (K, M) {                  // 룸코르프 유도코일 — 가로로 누운 감은 통(감은 줄 띠) · 양 끝 판 · 받침 · 위의 고전압 단자 둘
      var g = new THREE.Group();
      var base = K.mesh(K.rbox(2.0, .18, .9, .05), M.slate); base.position.y = -.45; g.add(base);
      var body = K.mesh(K.cyl(.4, .4, 1.5, 40), M.rule); body.rotation.z = Math.PI / 2; body.position.y = .1; g.add(body);
      for (var i = 0; i < 14; i++) { var w = K.mesh(new THREE.TorusGeometry(.405, .016, 8, 40), M.muted, false); w.rotation.y = Math.PI / 2; w.position.set(-.65 + i * .1, .1, 0); g.add(w); }
      [-1, 1].forEach(function (s) {
        var ch = K.mesh(K.cyl(.55, .55, .08, 40), M.porcelain); ch.rotation.z = Math.PI / 2; ch.position.set(.78 * s, .1, 0); g.add(ch);
        var sup = K.mesh(K.rbox(.12, .45, .5, .03), M.slate); sup.position.set(.78 * s, -.2, 0); g.add(sup);
        var post = K.mesh(K.cyl(.03, .03, .35, 10), M.steel); post.position.set(.78 * s, .82, 0); g.add(post);
        var b = K.mesh(K.ball(.07), M.steel); b.position.set(.78 * s, 1.0, 0); g.add(b);
      });
      return g;
    },
    dipole: function (K, M) {                // 02 의 쌍극자 그대로 + 불꽃 간극에서 전파 고리
      var g = SHAPES['02-history'].dipole(K, M); g.userData.emit = new THREE.Vector3(0, .55, 0);
      return g;
    }
  };

  // ── 05 기증자 — 아마추어 무선국 한 벌(받침 · 책상 · 송수신기 · 전건 · 안테나 돛대) + 1턴에 떨어지는 셋(진료 가방 · QST 잡지 판 · 기증 상자)
  // 기기는 일반형이다(HM4DF 무선국의 실제 장비는 조사 자료에 없다 — 기종을 지어 그리지 않는다). 송수신기·돛대·책상은 10(아마추어 무선)이 다시 쓴다
  function hamDesk(K, M) {                  // 책상 — 상판 2.6 × 0.12 × 1.4(원점 = 상판 가운데), 다리 넷(0.9), 앞 가림판
    var g = new THREE.Group(); g.add(K.mesh(K.rbox(2.6, .12, 1.4, .04), M.slate));
    [[-1, -1], [-1, 1], [1, -1], [1, 1]].forEach(function (s) { var l = K.mesh(K.rbox(.1, .9, .1, .03), M.ink); l.position.set(1.18 * s[0], -.51, .6 * s[1]); g.add(l); });
    var pan = K.mesh(K.rbox(2.3, .45, .04, .02), M.muted); pan.position.set(0, -.32, .6); g.add(pan);
    return g;
  }
  function hamRig(K, M) {                   // 송수신기 1.2 × 0.55 × 0.75 — 앞판 · 큰 다이얼(점등) · 계기 창 · 손잡이 셋 · 옆 손잡이 둘
    var g = new THREE.Group(); g.userData.lamp = true;
    g.add(K.mesh(K.rbox(1.2, .55, .75, .05), M.slate));
    var face = K.mesh(K.rbox(1.1, .45, .03, .02), M.ink); face.position.set(0, 0, .38); g.add(face);
    var dial = K.mesh(K.cyl(.14, .14, .05, 32), M.lamp); dial.rotation.x = Math.PI / 2; dial.position.set(-.25, .02, .41); g.add(dial);
    var meter = K.mesh(K.rbox(.3, .16, .02, .01), M.mist, false); meter.position.set(.25, .1, .405); g.add(meter);
    [.12, .25, .38].forEach(function (x) { var k = K.mesh(K.cyl(.035, .035, .05, 12), M.steel, false); k.rotation.x = Math.PI / 2; k.position.set(x, -.12, .41); g.add(k); });
    [-1, 1].forEach(function (s) { var h = K.mesh(K.rbox(.04, .3, .04, .015), M.steel); h.position.set(.62 * s, 0, .3); g.add(h); });
    return g;
  }
  function hamMast(K, M) {                  // 안테나 돛대 — 높이 3.4, 위 가로 붐과 소자 셋(야기 모양). 끝에서 전파 고리
    var g = new THREE.Group();
    g.add(K.mesh(K.lathe([[0, -1.7], [.12, -1.7, .02], [.06, -1.55], [.045, 1.6], [0, 1.6]], 16), M.steel));
    var boom = K.mesh(K.rbox(1.4, .05, .05, .015), M.steel); boom.position.y = 1.55; g.add(boom);
    [-.55, 0, .55].forEach(function (x, i) { var e = K.mesh(K.cyl(.018, .018, 1.1 - i * .15, 8), M.ink); e.rotation.x = Math.PI / 2; e.position.set(x, 1.55, 0); g.add(e); });
    g.userData.emit = new THREE.Vector3(0, 1.6, 0);
    return g;
  }
  function hamStage(K, M) {                 // 받침 3.8 × 0.7 × 2.0 — 닫힌 상자(떨어져 나갈 부품이 속에 숨는다), 앞 띠
    var g = new THREE.Group(); g.add(K.mesh(K.rbox(3.8, .7, 2.0, .06), M.porcelain));
    var strip = K.mesh(K.rbox(3.6, .06, .03, .01), M.rule, false); strip.position.set(0, .15, 1.01); g.add(strip);
    return g;
  }
  SHAPES['05-donor'] = {
    stage: hamStage,
    desk: hamDesk,
    rig: hamRig,
    key: function (K, M) { var g = SHAPES['02-history'].key(K, M); g.scale.setScalar(.75); return g; },   // 02 의 전건 모양을 0.75 배로
    mast: hamMast,
    bag: function (K, M) {                  // 진료 가방 — 둥근 몸통 0.7 × 0.42 × 0.36, 여밈 띠, 반원 손잡이
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(.7, .42, .36, .1), M.ink));
      var band = K.mesh(K.rbox(.72, .04, .38, .01), M.steel, false); band.position.y = .12; g.add(band);
      var h = K.mesh(new THREE.TorusGeometry(.13, .025, 8, 24, Math.PI), M.slate); h.position.y = .21; g.add(h);
      return g;
    },
    qst: function (K, M) {                  // 잡지 — 0.55 × 0.03 × 0.75 판, 위 표지 띠와 본문 줄(글자 없음)
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(.55, .03, .75, .01), M.porcelain));
      var band = K.mesh(K.rbox(.5, .012, .18, .004), M.ink, false); band.position.set(0, .02, -.25); g.add(band);
      for (var i = 0; i < 4; i++) { var l = K.mesh(K.rbox(.42, .008, .03, .003), M.muted, false); l.position.set(0, .02, -.02 + i * .1); g.add(l); }
      return g;
    },
    crate: function (K, M) {                // 기증 상자 0.7 × 0.5 × 0.6(받침 높이 0.7 안에 숨는다) — 널판 띠 둘
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(.7, .5, .6, .03), M.rule));
      [-.12, .12].forEach(function (y) { var s = K.mesh(K.rbox(.72, .05, .62, .01), M.muted, false); s.position.y = y; g.add(s); });
      return g;
    }
  };

  // ── 06 주파수 대역별 기증품 — ITU 대역 표를 쌓은 탑(받침 = V.431-8 표 · 축 · 접힌 주파수 막대 · 대역 4~11 여덟 층 · 이름 칸 둘)
  // 층 k(0 = 대역 4 VLF … 7 = 대역 11 EHF): 반지름 R(k) 가 위로 곧게 준다 — 높이가 로그 주파수, 반지름이 로그 파장이면 반비례(λ = c/f)는
  // 곧은 기울기다. 크기: 처음엔 맨 아래 2.3·받침 2.75 로 지었더니 둥근 받침의 경계 상자 대각선이 가로 맞춤을 정해 탑이 화면 가운데 열의
  // 3분의 2 폭으로 작아졌다 — 맨 아래 2.0·받침 2.3 으로 줄이고 그만큼 세로로 벌린다(tables.yaml 의 간격).
  // 테두리 물결은 둘레에 3(k+1) 주기 — 위로 갈수록 반지름은 줄고 주기는 늘어 물결 한 마루의 길이가 약 22배 짧아진다
  // (실제는 대역마다 10배 — 그림은 '위로 갈수록 짧다' 만 말하고 비율은 말하지 않는다). 이름 칸은 각 AL(주파수 기준 열, 어두운 칸)·AR(파장 기준
  // 열, 은색 칸)에 — 카메라 방위 0.4~0.6 에서 AL 은 화면 왼쪽 앞, AR 은 오른쪽 앞이다(오른쪽 = (cos az, 0, −sin az) 와 내적으로 정했다).
  // 맨 아래 층의 왼쪽 칸과 맨 위 층의 오른쪽 칸은 따로 빠지는 부품(ftab·wtab)이라 그 층 모양에서는 뺀다. 글자는 없다
  var B06 = { R: function (k) { return 2.0 - .18 * k; }, AL: 2.15, AR: -.03, TAB: [.46, .16, .26] };
  function bandTab(K, M, mat, a) {           // 이름 칸 하나 — 긴 변이 반지름 방향(각 a)을 향한다(rotation.y = −a 면 자기 x 축이 (cos a, 0, sin a))
    // 칸 끝 손잡이 테(둥근 상자)는 뺐다 — 칸 열넷에 하나씩이면 삼각형만 8천 개 늘고 화면에서는 거의 안 보였다(아래 물결 관 주석의 프레임 시간)
    var g = new THREE.Group(), t = K.mesh(K.rbox(B06.TAB[0], B06.TAB[1], B06.TAB[2], .04), mat); t.rotation.y = -a; g.add(t);
    return g;
  }
  function bandTier(k) {
    return function (K, M) {
      var g = new THREE.Group(), r = B06.R(k), n = 3 * (k + 1); g.userData.lamp = true;
      g.add(K.mesh(K.lathe([[.2, -.13], [r, -.13, .05], [r, .13, .05], [.2, .13, .03], [.2, -.13]], 48), k % 2 ? M.rule : M.porcelain));
      // 윗면 장식 고리는 모서리 다듬기 없이(점 넷) — 다듬기 넷이면 이 가는 고리 하나가 삼각형 3.8천 개였다
      var top = K.mesh(K.lathe([[r * .55, -.012], [r * .72, -.012], [r * .72, .012], [r * .55, .012], [r * .55, -.012]], 48), k % 2 ? M.porcelain : M.rule, false);
      top.position.y = .135; g.add(top);
      // 테두리 물결 — 옆면에 붙은 닫힌 사인 관(점등 때 켜진다). 처음 한 주기 24점·마디 2배·둘레 8, 몸통 96분할로 지었더니 06 한 장이 삼각형 11만 개(07 은
      // 1.6만)라 GPU 없는 PC(SwiftShader)에서 프레임이 다른 큐의 세 배(평균 142 ms)였다 → 한 주기 12점·둘레 5·몸통 48분할. 사인이 꺾여 보이지 않는다(캡처로 확인)
      var pts = [], N = Math.max(72, 12 * n);
      for (var i = 0; i < N; i++) { var a = i / N * Math.PI * 2; pts.push(new THREE.Vector3((r + .012) * Math.cos(a), .065 * Math.sin(n * a), (r + .012) * Math.sin(a))); }
      g.add(K.mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts, true), N, .026, 5, true), M.lamp, false));
      if (k > 0) { var L = bandTab(K, M, M.ink, B06.AL); L.position.set((r + .18) * Math.cos(B06.AL), 0, (r + .18) * Math.sin(B06.AL)); g.add(L); }
      if (k < 7) { var Rt = bandTab(K, M, M.steel, B06.AR); Rt.position.set((r + .18) * Math.cos(B06.AR), 0, (r + .18) * Math.sin(B06.AR)); g.add(Rt); }
      return g;
    };
  }
  SHAPES['06-bands'] = {
    base: function (K, M) {                 // 받침 — 지름 4.6, 높이 0.4. 윗면에 표 무늬(여덟 줄 × 세 칸: 대역번호 · 주파수 기준 · 파장 기준) — 글자 없음
      var g = new THREE.Group();
      g.add(K.mesh(K.lathe([[0, -.2], [2.3, -.2, .06], [2.3, .2, .05], [0, .2]], 64), M.slate));
      var sheet = K.mesh(K.rbox(2.4, .03, 1.7, .01), M.porcelain, false); sheet.position.y = .215; g.add(sheet);
      for (var i = 0; i <= 8; i++) { var row = K.mesh(K.rbox(2.3, .012, .014, .004), M.muted, false); row.position.set(0, .235, -.8 + i * .2); g.add(row); }
      [-1.15, -.6, .3, 1.15].forEach(function (x) { var col = K.mesh(K.rbox(.014, .012, 1.6, .004), M.muted, false); col.position.set(x, .235, 0); g.add(col); });
      return g;
    },
    axis: function (K, M) {                 // 축 — 높이 2.55, 반지름 0.1(속이 빈 관이라 주파수 막대가 접혀 들어간다). 아래 깃
      var g = new THREE.Group();
      g.add(K.mesh(new THREE.CylinderGeometry(.1, .1, 2.55, 32, 1, true), M.steel));
      var collar = K.mesh(K.lathe([[.1, -.06], [.2, -.06, .02], [.2, .06, .02], [.1, .06, .02], [.1, -.06]], 32), M.steel); collar.position.y = -1.2; g.add(collar);
      var rim = K.mesh(new THREE.TorusGeometry(.1, .018, 8, 32), M.ink); rim.rotation.x = Math.PI / 2; rim.position.y = 1.275; g.add(rim);
      return g;
    },
    mast: function (K, M) {                 // 주파수 막대 아래 마디 — 높이 2.4, 반지름 0.075(속이 빈 관 — 위 마디가 접혀 들어간다). 위 끝 테
      var g = new THREE.Group();
      g.add(K.mesh(new THREE.CylinderGeometry(.075, .075, 2.4, 24, 1, true), M.steel));
      var t = K.mesh(new THREE.TorusGeometry(.075, .015, 8, 24), M.ink); t.rotation.x = Math.PI / 2; t.position.y = 1.2; g.add(t);
      return g;
    },
    mast2: function (K, M) {                // 위 마디 — 높이 2.3, 반지름 0.05. 끝 구슬(점등 · 전파 고리). 접혔을 때 구슬이 축 윗면에 맞닿아 축의 마개로 보인다
      var g = new THREE.Group(); g.userData.lamp = true;
      g.add(K.mesh(K.cyl(.05, .05, 2.3, 20), M.steel));
      var tip = K.mesh(K.ball(.085), M.lamp); tip.position.y = 1.19; g.add(tip);
      g.userData.emit = new THREE.Vector3(0, 1.21, 0);
      return g;
    },
    b4: bandTier(0),
    b5: bandTier(1),
    b6: bandTier(2),
    b7: bandTier(3),
    b8: bandTier(4),
    b9: bandTier(5),
    b10: bandTier(6),
    b11: bandTier(7),
    ftab: function (K, M) { return bandTab(K, M, M.ink, B06.AL); },      // 맨 아래 층(VLF)의 주파수 기준 칸 — 초장파
    wtab: function (K, M) { return bandTab(K, M, M.steel, B06.AR); }     // 맨 위 층(EHF)의 파장 기준 칸 — 밀리미터파
  };

  // ── 08 항공무선통신 — 항공기 앞 동체 한 토막(받침 · 아래 껍데기(바닥·계기판) · 위 껍데기(앞유리·안테나 자리) · 좌석 · 요크 · 페달 ·
  // 무선전화 송수신기 두 대 · 트랜스폰더 · 비상위치지시용 무선표지설비 · 위 날개 안테나). 기종은 그리지 않는다(조사 자료 '확인 불가' — 일반형 동체).
  // 동체 축은 x(뱃머리 +x). 반원통은 CylinderGeometry 를 z 축으로 90° 돌려 눕힌다 — 돌린 뒤 y = r·sinθ 라 아래 반은 θ π~2π, 위 반은 0~π.
  // 껍데기는 속이 보여야 해서 양면(DoubleSide) — 이 부품만의 재질이라 다른 부품에 번지지 않는다. 껍데기 색은 rule(옅은 청회색) — 처음 porcelain(흰색)으로
  // 칠했더니 밝은 바탕에 묻혀 위 껍데기가 떠오른 뒤 어디 있는지 안 보였다. 받침도 4.6 → 3.6, 객실 3.2 → 2.8(동체 길이가 가로 맞춤을 정한다)
  var F08 = { R: .9, L: 2.8, X0: -1.5, NOSE: 1.33 };
  function shellHalf(K, mat, lower) {        // 객실 반원통 + 앞 코 반구(길이 1.2 — x 를 1.33 배)
    var g = new THREE.Group(), cx = F08.X0 + F08.L / 2;
    var c = new THREE.CylinderGeometry(F08.R, F08.R, F08.L, 48, 1, true, lower ? Math.PI : 0, Math.PI); c.rotateZ(Math.PI / 2); c.translate(cx, 0, 0);
    g.add(K.mesh(c, mat));
    var n = new THREE.SphereGeometry(F08.R, 40, 12, Math.PI / 2, Math.PI, lower ? Math.PI / 2 : 0, Math.PI / 2); n.scale(F08.NOSE, 1, 1); n.translate(F08.X0 + F08.L, 0, 0);
    g.add(K.mesh(n, mat));
    return g;
  }
  SHAPES['08-aviation'] = {
    slab: function (K, M) {                 // 받침판 3.6 × 0.25 × 2.0 + 동체를 받치는 안장 둘
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(3.6, .25, 2.0, .05), M.porcelain));
      [-.9, .9].forEach(function (x) { var s = K.mesh(K.rbox(.3, .5, 1.1, .04), M.rule); s.position.set(x, .37, 0); g.add(s); });
      return g;
    },
    belly: function (K, M) {                // 아래 껍데기 — 바닥판 · 계기판(화면 둘은 점등) · 배 아래 작은 안테나
      var g = new THREE.Group(); g.userData.lamp = true; M.rule.side = THREE.DoubleSide;
      g.add(shellHalf(K, M.rule, true));
      var floor = K.mesh(K.rbox(2.6, .06, 1.6, .02), M.porcelain); floor.position.set(-.1, -.3, 0); g.add(floor);
      var panel = K.mesh(K.rbox(.08, .45, 1.3, .03), M.slate); panel.position.set(1.22, -.02, 0); g.add(panel);
      [-.3, .3].forEach(function (z) { var s = K.mesh(K.rbox(.02, .2, .38, .01), M.lamp, false); s.position.set(1.17, .03, z); g.add(s); });
      var fin = K.mesh(K.rbox(.3, .14, .03, .015), M.ink); fin.position.set(.2, -.96, 0); g.add(fin);
      return g;
    },
    roof: function (K, M) {                 // 위 껍데기 — 앞유리 띠(유리) · 뒤쪽 짧은 막대 안테나
      var g = new THREE.Group(); M.rule.side = THREE.DoubleSide;
      g.add(shellHalf(K, M.rule, false));
      var w = new THREE.SphereGeometry(F08.R * 1.012, 32, 8, Math.PI - .9, 1.8, .5, .75); w.scale(F08.NOSE, 1, 1); w.translate(F08.X0 + F08.L, 0, 0);
      g.add(K.mesh(w, M.glass, false));
      var whip = K.mesh(K.cyl(.015, .02, .4, 8), M.ink); whip.position.set(-1.2, 1.08, 0); whip.rotation.z = .35; g.add(whip);
      return g;
    },
    blade: function (K, M) {                // 위 날개 안테나(공대지 음성) — 뒤로 젖힌 얇은 날개 + 받침판
      var g = new THREE.Group(), s = new THREE.Shape();
      s.moveTo(-.2, 0); s.lineTo(.2, 0); s.lineTo(-.05, .45); s.lineTo(-.22, .45); s.lineTo(-.2, 0);
      var geo = new THREE.ExtrudeGeometry(s, { depth: .04, bevelEnabled: true, bevelThickness: .01, bevelSize: .01, bevelSegments: 1 }); geo.translate(0, 0, -.02);
      g.add(K.mesh(geo, M.ink));
      var foot = K.mesh(K.rbox(.46, .03, .12, .01), M.steel); g.add(foot);
      g.userData.emit = new THREE.Vector3(-.13, .47, 0);
      return g;
    },
    seat: function (K, M) {                 // 좌석 — 방석 · 등받이 · 기둥
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(.5, .1, .5, .04), M.slate));
      var back = K.mesh(K.rbox(.1, .6, .5, .04), M.slate); back.position.set(-.25, .3, 0); back.rotation.z = .15; g.add(back);
      var post = K.mesh(K.cyl(.04, .06, .3, 12), M.steel); post.position.y = -.2; g.add(post);
      return g;
    },
    yoke: function (K, M) {                 // 요크 — 기둥(0.5) 위 가로 손잡이(z 로 0.5)와 양 끝 세운 손잡이
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(.06, .5, .06, .02), M.steel));
      var bar = K.mesh(K.rbox(.06, .06, .5, .02), M.ink); bar.position.y = .27; g.add(bar);
      [-1, 1].forEach(function (s) { var h = K.mesh(K.rbox(.07, .18, .07, .03), M.ink); h.position.set(0, .33, .25 * s); g.add(h); });
      return g;
    },
    pedals: function (K, M) {               // 페달 둘 — 가로 막대에 기울여 단 판
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(.05, .05, .6, .02), M.steel));
      [-1, 1].forEach(function (s) { var p = K.mesh(K.rbox(.05, .28, .16, .02), M.ink); p.position.set(.04, .1, .2 * s); p.rotation.z = -.35; g.add(p); });
      return g;
    },
    radios: function (K, M) {               // 무선전화 송수신기 두 대 — 위아래로 쌓은 두 상자(앞판 +z), 각자 다이얼
      var g = new THREE.Group();
      [0, .22].forEach(function (y) { var b = K.mesh(K.rbox(.6, .18, .42, .03), M.slate); b.position.y = y; g.add(b);
        var f = K.mesh(K.rbox(.5, .12, .02, .01), M.ink, false); f.position.set(0, y, .215); g.add(f);
        var d = K.mesh(K.cyl(.045, .045, .03, 16), M.steel, false); d.rotation.x = Math.PI / 2; d.position.set(.17, y, .23); g.add(d); });
      return g;
    },
    xpdr: function (K, M) {                 // 트랜스폰더 — 납작한 상자, 숫자 창 하나
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(.5, .12, .36, .03), M.slate));
      var win = K.mesh(K.rbox(.3, .05, .02, .01), M.mist, false); win.position.set(-.05, 0, .185); g.add(win);
      return g;
    },
    elt: function (K, M) {                  // 비상위치지시용 무선표지설비 — 상자 · 손잡이 · 짧은 막대 안테나(점등 뒤 전파 고리)
      var g = new THREE.Group(); g.userData.lamp = true;
      g.add(K.mesh(K.rbox(.42, .26, .26, .04), M.porcelain));
      var band = K.mesh(K.rbox(.44, .06, .28, .01), M.lamp, false); band.position.y = .05; g.add(band);
      var ant = K.mesh(K.cyl(.012, .012, .35, 8), M.ink); ant.position.set(.12, .3, 0); g.add(ant);
      g.userData.emit = new THREE.Vector3(.12, .48, 0);
      return g;
    }
  };

  // ── 09 특별교류전시 — 진열장 한 대: 상자(바닥·뒤판)는 남고 속이 바뀐다(받침 · 진열장 · 유리 덮개 · 소장 받침대 · 대여 받침대 · 빈 명판 틀).
  // 속 물건은 이름 없는 덩어리(상자 하나 · 둥근 병 하나)다 — 지금 놓인 전시품 목록은 조사 자료 '확인 불가' 라 어떤 물건인지 그리지 않는다
  SHAPES['09-special-exhibit'] = {
    plinth: function (K, M) {               // 받침 2.6 × 1.0 × 1.6, 앞 띠
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(2.6, 1.0, 1.6, .06), M.porcelain));
      var strip = K.mesh(K.rbox(2.4, .06, .03, .01), M.rule, false); strip.position.set(0, .3, .81); g.add(strip);
      return g;
    },
    case: function (K, M) {                 // 진열장 — 바닥판 2.4 × 0.08 × 1.4 와 뒤판(높이 1.3). 움직이지 않는 기준(상설 — 상자는 남는다)
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(2.4, .08, 1.4, .03), M.slate));
      var back = K.mesh(K.rbox(2.4, 1.3, .06, .03), M.rule); back.position.set(0, .69, -.67); g.add(back);
      var rail = K.mesh(K.rbox(2.2, .04, .04, .01), M.steel, false); rail.position.set(0, 1.0, -.62); g.add(rail);
      return g;
    },
    glass: function (K, M) {                // 유리 덮개 — 2.4 × 1.4 × 1.4 유리 상자와 쇠 모서리 열둘(모서리만 외곽선을 받는다)
      var g = new THREE.Group(), w = 1.2, h = .7, d = .7;
      g.add(K.mesh(K.rbox(2.36, 1.36, 1.36, .02), M.glass, false));
      for (var a = -1; a <= 1; a += 2) for (var b = -1; b <= 1; b += 2) {
        var x = K.mesh(K.rbox(2.4, .04, .04, .01), M.steel); x.position.set(0, a * h, b * d); g.add(x);
        var y = K.mesh(K.rbox(.04, 1.4, .04, .01), M.steel); y.position.set(a * w, 0, b * d); g.add(y);
        var z = K.mesh(K.rbox(.04, .04, 1.4, .01), M.steel); z.position.set(a * w, b * h, 0); g.add(z);
      }
      return g;
    },
    standA: function (K, M) {               // 소장 받침대 — 각진 대 0.6 × 0.45 × 0.6
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(.6, .45, .6, .04), M.slate)); return g;
    },
    standB: function (K, M) {               // 대여 받침대 — 둥근 대(지름 0.6)
      var g = new THREE.Group(); g.add(K.mesh(K.cyl(.3, .3, .45, 32), M.muted)); return g;
    },
    // 실물 둘 — 받침대와 따로 떼어(자식 부품) "지금 놓인 실물을" 에서 물건만 강조한다. 처음엔 받침대 모양에 붙였더니 그 낱말에 강조할 것이
    // 빈 유리 덮개뿐이었다(덮개는 실물이 아니다)
    objA: function (K, M) {                 // 이름 없는 상자
      var g = new THREE.Group(), o = K.mesh(K.rbox(.34, .3, .26, .05), M.rule); o.rotation.y = .3; g.add(o); return g;   // 흰색이면 강조 때 외곽선만 보였다
    },
    objB: function (K, M) {                 // 이름 없는 둥근 병
      var g = new THREE.Group(); g.add(K.mesh(K.lathe([[0, -.18], [.13, -.18, .04], [.16, .02, .06], [.07, .15, .03], [.08, .2, .01], [0, .2]], 32), M.steel)); return g;
    },
    plate: function (K, M) {                // 명판 틀 — 비스듬히 세운 빈 판(글자 없음 — 목록은 시기마다 바뀐다)
      var g = new THREE.Group(), t = K.mesh(K.rbox(.7, .32, .04, .02), M.porcelain); t.rotation.x = -.35; g.add(t);
      var f = K.mesh(K.rbox(.74, .36, .03, .02), M.ink, false); f.position.z = -.02; f.rotation.x = -.35; g.add(f);
      var foot = K.mesh(K.rbox(.4, .04, .16, .01), M.ink); foot.position.set(0, -.17, -.04); g.add(foot);
      return g;
    }
  };

  // ── 10 아마추어 무선 — 05 의 무선국(받침 · 책상 · 송수신기 · 안테나 돛대)을 다시 쓰고, 제도의 부품을 더한다: 출력계 · 자격 판 받침 ·
  // 자격증 판 넷(네 등급) · 비상 가방(받침 속에 숨어 있다가 오른다). 판의 막대 길이는 카드 그림의 안테나공급전력 상한을 로그로 줄인 것이다
  // (1kW · 200W · 100W · 10W → 0.13 × log10 W) — 그림도 사실 주장이라 비율을 지어내지 않는다. 글자는 없다
  var LIC10 = [1000, 200, 100, 10];
  function licPlate(i) {
    return function (K, M) {
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(.5, .03, .36, .01), i % 2 ? M.rule : M.porcelain));
      var len = .13 * Math.log10(LIC10[i]), bar = K.mesh(K.rbox(len, .014, .07, .004), M.ink, false); bar.position.set(-.2 + len / 2, .02, .06); g.add(bar);
      var tag = K.mesh(K.rbox(.08, .014, .08, .004), M.slate, false); tag.position.set(-.16, .02, -.1); g.add(tag);
      return g;
    };
  }
  SHAPES['10-ham'] = {
    stage: hamStage,
    desk: hamDesk,
    rig: hamRig,
    mast: hamMast,
    meter: function (K, M) {                // 출력계 — 상자 0.4 × 0.32 × 0.3, 반달 눈금 창과 바늘
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(.4, .32, .3, .03), M.slate));
      var win = K.mesh(K.cyl(.12, .12, .02, 24, 1, false, -Math.PI / 2, Math.PI), M.mist, false); win.rotation.x = Math.PI / 2; win.position.set(0, -.02, .155); g.add(win);
      var nd = K.mesh(K.rbox(.012, .1, .01, .003), M.ink, false); nd.position.set(.02, .02, .165); nd.rotation.z = -.5; g.add(nd);
      return g;
    },
    tray: function (K, M) {                 // 자격 판 받침 — 낮은 쟁반 0.62 × 0.06 × 0.46(테두리)
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(.62, .04, .46, .015), M.slate));
      [[0, .23, .62, .03], [0, -.23, .62, .03]].forEach(function (r) { var e = K.mesh(K.rbox(r[2], .06, r[3], .01), M.ink, false); e.position.set(r[0], .03, r[1]); g.add(e); });
      return g;
    },
    lic1: licPlate(0),
    lic2: licPlate(1),
    lic3: licPlate(2),
    lic4: licPlate(3),
    gobag: function (K, M) {                // 비상 가방 0.6 × 0.5 × 0.4(받침 높이 0.7 안에 숨는다) — 덮개 · 옆에 꽂은 휴대 무전기와 짧은 안테나
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(.6, .5, .4, .1), M.slate));
      var flap = K.mesh(K.rbox(.62, .12, .42, .05), M.ink, false); flap.position.y = .2; g.add(flap);
      var hh = K.mesh(K.rbox(.1, .26, .07, .03), M.muted); hh.position.set(.36, .02, 0); g.add(hh);
      var ant = K.mesh(K.cyl(.012, .012, .2, 8), M.ink); ant.position.set(.36, .25, 0); g.add(ant);
      return g;
    }
  };

  // ── 11 사물인터넷 — 표준의 층 모형: 받침(Y.4000) · 사물 판(물리적 사물 — 이름 없는 상자·원기둥·공·원뿔) · 가상 사물(같은 모양의 반투명 쌍둥이) ·
  // 기기 판(작은 상자와 안테나) · 사물 간 통신 판(마디와 잇는 막대) · 서비스 계층 판 · 사람(옆에 서 있다가 "개입 없이" 에서 흐리게 빠진다) +
  // 받침 속에 숨은 둘(점 격자 판 = 연결밀도 · 짧은 구간 막대 = 지연 1밀리초). 기기 종류는 그리지 않는다(조사 자료 '확인 불가')
  var OBJ11 = [[-.8, -.35, 'box'], [-.2, .4, 'cyl'], [.45, -.25, 'ball'], [.95, .35, 'cone']];
  function thing11(K, mat, kind, sc) {
    var m = kind === 'box' ? K.rbox(.32 * sc, .32 * sc, .32 * sc, .05) : kind === 'cyl' ? K.cyl(.15 * sc, .15 * sc, .34 * sc, 24) :
      kind === 'ball' ? K.ball(.17 * sc) : K.cyl(.001, .19 * sc, .36 * sc, 24);
    return K.mesh(m, mat, mat.transparent ? false : true);
  }
  SHAPES['11-iot'] = {
    base: function (K, M) {                 // 받침 3.0 × 0.5 × 2.2 — 닫힌 상자(점 격자 판·구간 막대가 속에 숨는다), 앞 띠
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(3.0, .5, 2.2, .06), M.slate));
      var strip = K.mesh(K.rbox(2.8, .05, .03, .01), M.rule, false); strip.position.set(0, .1, 1.11); g.add(strip);
      return g;
    },
    things: function (K, M) {               // 사물 판 2.6 × 0.1 × 1.8 위에 물리적 사물 넷(움직이지 않는 기준)
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(2.6, .1, 1.8, .03), M.porcelain));
      var mats = [M.rule, M.slate, M.steel, M.muted];
      OBJ11.forEach(function (o, i) { var m = thing11(K, mats[i], o[2], 1); m.position.set(o[0], .05 + .17, o[1]); g.add(m); });
      return g;
    },
    virt: function (K, M) {                 // 가상 사물 — 같은 넷의 반투명 쌍둥이(1.05 배). 분해되면 사물 위로 떠오른다
      var g = new THREE.Group();
      OBJ11.forEach(function (o) { var m = thing11(K, M.glass, o[2], 1.05); m.position.set(o[0], .05 + .17, o[1]); g.add(m); });
      return g;
    },
    devices: function (K, M) {              // 기기 판 2.4 × 0.08 × 1.6 위에 기기 다섯 — 작은 상자와 짧은 안테나(통신 기능)
      var g = new THREE.Group(); g.userData.lamp = true; g.add(K.mesh(K.rbox(2.4, .08, 1.6, .03), M.rule));
      [[-.9, .3], [-.35, -.4], [.15, .35], [.6, -.3], [1.0, .45]].forEach(function (d) {
        var b = K.mesh(K.rbox(.26, .14, .2, .03), M.slate); b.position.set(d[0], .11, d[1]); g.add(b);
        var a = K.mesh(K.cyl(.012, .012, .2, 8), M.ink); a.position.set(d[0] + .08, .28, d[1]); g.add(a);
        var l = K.mesh(K.rbox(.06, .03, .02, .01), M.lamp, false); l.position.set(d[0] - .05, .12, d[1] + .1); g.add(l); });
      return g;
    },
    comm: function (K, M) {                 // 사물 간 통신 판 2.2 × 0.06 × 1.4 — 마디 여섯과 잇는 막대(그물)
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(2.2, .06, 1.4, .02), M.porcelain));
      var P = [[-.85, .35], [-.4, -.4], [0, .3], [.4, -.35], [.85, .4], [.0, -.05]];
      P.forEach(function (q) { var n = K.mesh(K.ball(.07), M.ink); n.position.set(q[0], .1, q[1]); g.add(n); });
      [[0, 1], [0, 2], [1, 5], [2, 5], [2, 4], [3, 5], [3, 4], [1, 3]].forEach(function (e) {
        var a = P[e[0]], b = P[e[1]], dx = b[0] - a[0], dz = b[1] - a[1], L = Math.hypot(dx, dz);
        var r = K.mesh(K.rbox(L, .025, .025, .008), M.steel, false); r.position.set((a[0] + b[0]) / 2, .1, (a[1] + b[1]) / 2); r.rotation.y = -Math.atan2(dz, dx); g.add(r); });
      return g;
    },
    service: function (K, M) {              // 서비스 계층 판 2.0 × 0.14 × 1.2 위에 둥근 타일 셋(점등) — 점등 뒤 가운데서 전파 고리
      var g = new THREE.Group(); g.userData.lamp = true; g.add(K.mesh(K.rbox(2.0, .14, 1.2, .04), M.slate));
      [-.6, 0, .6].forEach(function (x) { var t = K.mesh(K.rbox(.44, .06, .44, .08), M.lamp); t.position.set(x, .1, 0); g.add(t); });
      g.userData.emit = new THREE.Vector3(0, .2, 0);
      return g;
    },
    person: function (K, M) {               // 사람 — 몸통(캡슐)과 머리(높이 1.2). 표정·옷 없음
      var g = new THREE.Group();
      var body = K.mesh(K.lathe([[0, -.6], [.16, -.6, .04], [.2, -.1, .1], [.17, .25, .08], [.08, .33, .03], [0, .33]], 32), M.muted); g.add(body);
      var head = K.mesh(K.ball(.15), M.muted); head.position.y = .5; g.add(head);
      return g;
    },
    grid: function (K, M) {                 // 점 격자 판 0.9 × 0.05 × 0.9 — 6 × 6 점(연결밀도 — 수를 세는 그림이 아니라 '빽빽하다' 만)
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(.9, .05, .9, .02), M.porcelain));
      for (var i = 0; i < 6; i++) for (var j = 0; j < 6; j++) { var d = K.mesh(K.cyl(.035, .035, .03, 10), M.ink, false); d.position.set(-.35 + i * .14, .035, -.35 + j * .14); g.add(d); }
      return g;
    },
    bar: function (K, M) {                  // 구간 막대 — 긴 눈금 자(0.9) 위 아주 짧은 구간(양 끝 세운 탭) = 무선 구간 편도 지연
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(.9, .05, .18, .02), M.porcelain));
      for (var i = 0; i <= 8; i++) { var t = K.mesh(K.rbox(.01, .012, .06, .003), M.muted, false); t.position.set(-.4 + i * .1, .03, .05); g.add(t); }
      [-.4, -.32].forEach(function (x) { var tab = K.mesh(K.rbox(.02, .14, .12, .01), M.ink); tab.position.set(x, .09, -.02); g.add(tab); });
      var span = K.mesh(K.rbox(.08, .02, .03, .006), M.ink, false); span.position.set(-.36, .14, -.02); g.add(span);
      return g;
    }
  };

  // ── 12 KCA 멀티미디어실 — 기관 판 갈래 모형: 받침(제66조) · 기관 판 두 칸(관리 · 진흥) · 진흥 칸의 갈래 기둥 셋 · 기금 상자 · 빈 화면 판 · 촬영 슬레이트.
  // 화면은 비운다 — 구체적인 지원작은 확인 전이라는 대사 그대로(키오스크 같은 기기 모양도 조사 자료 '확인 불가' 라 그리지 않는다)
  SHAPES['12-multimedia'] = {
    base: function (K, M) {                 // 받침 3.2 × 0.5 × 2.0
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(3.2, .5, 2.0, .06), M.slate));
      var strip = K.mesh(K.rbox(3.0, .05, .03, .01), M.rule, false); strip.position.set(0, .1, 1.01); g.add(strip);
      return g;
    },
    mgmt: function (K, M) {                 // 관리 칸 — 기관 판의 왼쪽 반(1.5 × 0.3 × 1.8)
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(1.5, .3, 1.8, .05), M.rule));
      var t = K.mesh(K.rbox(1.2, .02, 1.4, .01), M.porcelain, false); t.position.y = .16; g.add(t);
      return g;
    },
    promo: function (K, M) {                // 진흥 칸 — 오른쪽 반
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(1.5, .3, 1.8, .05), M.porcelain));
      var t = K.mesh(K.rbox(1.2, .02, 1.4, .01), M.rule, false); t.position.y = .16; g.add(t);
      return g;
    },
    branch: function (K, M) {               // 갈래 기둥 셋(옆 0.5 · 가운데 0.9)과 머리판 — 원점은 기둥 밑동
      var g = new THREE.Group();
      [[-.45, .5], [0, .9], [.45, .5]].forEach(function (b) { var c = K.mesh(K.cyl(.05, .06, b[1], 16), M.steel); c.position.set(b[0], b[1] / 2, 0); g.add(c);
        var cap = K.mesh(K.cyl(.16, .16, .05, 24), M.ink); cap.position.set(b[0], b[1] + .02, 0); g.add(cap); });
      var foot = K.mesh(K.rbox(1.15, .06, .3, .02), M.ink); foot.position.y = .03; g.add(foot);
      return g;
    },
    fund: function (K, M) {                 // 기금 상자 0.6 × 0.4 × 0.45 — 금고 문 · 둥근 손잡이 · 경첩(돈 기호 없음)
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(.6, .4, .45, .05), M.slate));
      var door = K.mesh(K.rbox(.46, .3, .02, .02), M.ink, false); door.position.z = .23; g.add(door);
      var knob = K.mesh(K.cyl(.06, .06, .04, 20), M.steel, false); knob.rotation.x = Math.PI / 2; knob.position.set(.08, 0, .25); g.add(knob);
      return g;
    },
    screen: function (K, M) {               // 빈 화면 판 — 1.0 × 0.62 화면(점등)과 테, 카메라 쪽으로 0.5 돌림. 그림은 없다
      var g = new THREE.Group(), h = new THREE.Group(); h.rotation.y = .5; g.add(h); g.userData.lamp = true;
      h.add(K.mesh(K.rbox(1.0, .62, .06, .03), M.ink));
      var s = K.mesh(K.rbox(.9, .52, .02, .01), M.lamp, false); s.position.z = .035; h.add(s);
      var leg = K.mesh(K.rbox(.06, .2, .06, .02), M.steel); leg.position.y = -.4; h.add(leg);
      return g;
    },
    clapper: function (K, M) {              // 촬영 슬레이트 — 판 0.42 × 0.32 와 위의 줄무늬 막대(비스듬히 열림)
      var g = new THREE.Group(), h = new THREE.Group(); h.rotation.y = .5; g.add(h);
      h.add(K.mesh(K.rbox(.42, .32, .04, .02), M.slate));
      var stick = new THREE.Group(); stick.position.set(-.21, .18, 0); stick.rotation.z = .3; h.add(stick);
      for (var i = 0; i < 5; i++) { var st = K.mesh(K.rbox(.084, .06, .045, .005), i % 2 ? M.porcelain : M.ink); st.position.set(.042 + i * .084, 0, 0); stick.add(st); }
      return g;
    }
  };

  // ── 13 크로마키 체험 — 합성 세 겹: 받침 · 합성 화면 틀 · 키 막(바둑판 = 투명) · 배경 판(일반 풍경) · 뒤에 겹친 두 판(날씨 지도 · 영화 장면 — 이름 없는
  // 일반 무늬) · 전경(사람 오린 판) · 촬영 카메라(모양만). 판은 모두 xy 평면(앞 = +z), 2.4 × 1.4
  function plate13(K, M, mat) { var g = new THREE.Group(); g.add(K.mesh(K.rbox(2.4, 1.4, .04, .02), mat)); return g; }
  SHAPES['13-chromakey'] = {
    stand: function (K, M) {                // 받침 3.0 × 0.2 × 1.2 와 틀을 받치는 기둥 둘
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(3.0, .2, 1.2, .04), M.porcelain));
      [-1.0, 1.0].forEach(function (x) { var c = K.mesh(K.rbox(.08, .4, .08, .02), M.steel); c.position.set(x, .3, 0); g.add(c); });
      return g;
    },
    frame: function (K, M) {                // 합성 화면 틀 — 바깥 2.6 × 1.6, 테 두께 0.1(속이 빈 액자)
      var g = new THREE.Group();
      [[0, .75, 2.6, .1], [0, -.75, 2.6, .1], [-1.25, 0, .1, 1.6], [1.25, 0, .1, 1.6]].forEach(function (b) { var m = K.mesh(K.rbox(b[2], b[3], .14, .03), M.ink); m.position.set(b[0], b[1], 0); g.add(m); });
      return g;
    },
    key: function (K, M) {                  // 키 막 — 8 × 5 칸 바둑판의 절반만 채운 판(빈 칸으로 뒤가 보인다 = 투명하게 처리된 자리) + 가는 테
      var g = new THREE.Group(), cw = .3, ch = .28;
      for (var i = 0; i < 8; i++) for (var j = 0; j < 5; j++) if ((i + j) % 2 === 0) { var c = K.mesh(K.rbox(cw, ch, .03, .005), M.rule); c.position.set(-1.05 + i * cw, -.56 + j * ch, 0); g.add(c); }
      [[0, .71, 2.42, .03], [0, -.71, 2.42, .03], [-1.21, 0, .03, 1.42], [1.21, 0, .03, 1.42]].forEach(function (b) { var m = K.mesh(K.rbox(b[2], b[3], .03, .01), M.muted, false); m.position.set(b[0], b[1], 0); g.add(m); });
      return g;
    },
    bg: function (K, M) {                   // 배경 판 — 지평선 띠 · 낮은 산 셋(돋을새김) · 해
      var g = plate13(K, M, M.porcelain);
      var band = K.mesh(K.rbox(2.3, .3, .02, .01), M.rule, false); band.position.set(0, -.5, .03); g.add(band);
      [[-.7, .55], [.1, .75], [.8, .5]].forEach(function (m) { var s = new THREE.Shape(); s.moveTo(-m[1], 0); s.lineTo(0, m[1] * .8); s.lineTo(m[1], 0); s.lineTo(-m[1], 0);
        var geo = new THREE.ExtrudeGeometry(s, { depth: .03, bevelEnabled: false }); var mm = K.mesh(geo, M.muted, false); mm.position.set(m[0], -.35, .02); g.add(mm); });
      var sun = K.mesh(K.cyl(.13, .13, .03, 24), M.steel, false); sun.rotation.x = Math.PI / 2; sun.position.set(.75, .35, .03); g.add(sun);
      return g;
    },
    bg2: function (K, M) {                  // 날씨 지도 판 — 이름 없는 땅 모양 하나와 등압선 고리 셋(일반 무늬 — 어느 나라 지도도 아니다)
      var g = plate13(K, M, M.mist), s = new THREE.Shape();
      s.moveTo(-.5, -.4); s.quadraticCurveTo(-.7, .1, -.3, .45); s.quadraticCurveTo(.2, .6, .45, .2); s.quadraticCurveTo(.7, -.2, .3, -.5); s.quadraticCurveTo(-.1, -.6, -.5, -.4);
      var land = K.mesh(new THREE.ExtrudeGeometry(s, { depth: .03, bevelEnabled: false }), M.rule, false); land.position.set(-.3, 0, .02); g.add(land);
      [.3, .45, .6].forEach(function (r) { var t = K.mesh(new THREE.TorusGeometry(r, .012, 6, 40, Math.PI * 1.2), M.ink, false); t.position.set(.55, .05, .04); t.rotation.z = -.4; g.add(t); });
      return g;
    },
    bg3: function (K, M) {                  // 영화 장면 판 — 이름 없는 건물 실루엣 줄(높이가 다른 상자들)
      var g = plate13(K, M, M.rule);
      [[-.95, .5], [-.65, .8], [-.35, .55], [-.05, 1.0], [.3, .65], [.6, .85], [.92, .45]].forEach(function (b) { var m = K.mesh(K.rbox(.26, b[1], .03, .01), M.slate, false); m.position.set(b[0], -.7 + b[1] / 2, .03); g.add(m); });
      return g;
    },
    fg: function (K, M) {                   // 전경 — 사람 오린 판(머리 · 어깨 · 몸, 높이 1.1)과 작은 받침
      var g = new THREE.Group(), s = new THREE.Shape();
      s.moveTo(-.32, -.55); s.lineTo(-.3, .05); s.quadraticCurveTo(-.3, .2, -.12, .22); s.lineTo(.12, .22); s.quadraticCurveTo(.3, .2, .3, .05); s.lineTo(.32, -.55); s.lineTo(-.32, -.55);
      var body = K.mesh(new THREE.ExtrudeGeometry(s, { depth: .05, bevelEnabled: true, bevelThickness: .01, bevelSize: .01, bevelSegments: 1 }), M.slate); body.position.z = -.025; g.add(body);
      var head = K.mesh(K.cyl(.14, .14, .05, 28), M.slate); head.rotation.x = Math.PI / 2; head.position.y = .4; g.add(head);
      var foot = K.mesh(K.rbox(.5, .04, .25, .01), M.ink); foot.position.y = -.57; g.add(foot);
      return g;
    },
    camera: function (K, M) {               // 촬영 카메라 — 몸통 · 렌즈(−z 를 향한다) · 다리 셋. 판 쪽(왼쪽 뒤)을 보게 45° 돌림
      var g = new THREE.Group(), h = new THREE.Group(); h.rotation.y = Math.PI / 4; g.add(h);
      h.add(K.mesh(K.rbox(.32, .26, .44, .04), M.slate));
      var lens = K.mesh(K.cyl(.09, .1, .2, 24), M.ink); lens.rotation.x = Math.PI / 2; lens.position.z = -.3; h.add(lens);
      [0, 2.1, 4.2].forEach(function (a) { var l = K.mesh(K.cyl(.015, .015, .85, 8), M.steel); l.position.set(.18 * Math.cos(a), -.5, .18 * Math.sin(a)); l.rotation.set(.2 * Math.sin(a), 0, -.2 * Math.cos(a)); h.add(l); });
      return g;
    }
  };

  // ── 15·16 공용 — 누운 판(글자 없음). 받침 속에 숨어 있다가 빠지면서 표의 tilt 로 카메라 쪽에 선다. 줄 무늬는 '문서' 라는 표시일 뿐 내용이 아니다
  function docPlate(K, M, w, d, mat, rows) {
    var g = new THREE.Group(); g.add(K.mesh(K.rbox(w, .04, d, .015), mat || M.porcelain));
    for (var i = 0; i < (rows || 3); i++) { var l = K.mesh(K.rbox(w * .7, .008, .025, .003), M.muted, false); l.position.set(-w * .05, .024, -d * .25 + i * d * .5 / Math.max(1, (rows || 3) - 1)); g.add(l); }
    return g;
  }
  function pair(K, M, offset) {             // 두 칸짜리 판 — 같은 크기 두 장을 나란히(offset 0 = 함께 놓고 본다) 또는 앞뒤로 엇갈려(offset > 0 = 시차). 폭 1.3
    var g = new THREE.Group();
    [-1, 1].forEach(function (s, i) { var p = docPlate(K, M, .6, .44, i ? M.rule : M.porcelain, 3); p.position.set(.33 * s, 0, s > 0 ? -offset : 0); g.add(p); });
    return g;
  }

  // ── 15 전자파 측정 — 둥근 받침 · 기지국 돛대(패널 안테나 셋 · 아래 장비함) · 울타리(반지름 1.2) · 등급 고리 넷 · 2턴의 두 칸짜리 판 둘
  // 고리 색은 안쪽(경고)일수록 진하다 — 세기의 계단(라벨 색 규칙인 연두·파랑·주황·빨강은 쓰지 않는다: 강조색 하나 원칙, 그리고 그 라벨은 무선국 설비에 붙는 것이지
  // 둘레 공간의 색이 아니다 — 조사 자료 A)
  function emfRing(r0, r1, mat) {
    return function (K, M) { var g = new THREE.Group(); g.add(K.mesh(K.lathe([[r0, -.03], [r1, -.03, .015], [r1, .03, .015], [r0, .03, .015], [r0, -.03]], 96), M[mat])); return g; };
  }
  SHAPES['15-emf'] = {
    slab: function (K, M) {                 // 둥근 받침 — 지름 3.2, 높이 0.4(닫힌 원통 — 판 둘이 앞쪽 현에 포개져 숨는다). 처음 지름 4.1 은 가로 맞춤에 걸려 전체가 작았다
      var g = new THREE.Group(); g.add(K.mesh(K.lathe([[0, -.2], [1.6, -.2, .05], [1.6, .2, .04], [0, .2]], 96), M.porcelain));
      var band = K.mesh(new THREE.CylinderGeometry(1.612, 1.612, .05, 96, 1, true), M.rule, false); band.position.y = .05; g.add(band);
      return g;
    },
    mast: function (K, M) {                 // 기지국 돛대 — 높이 4.0(받침 위 0.4 부터), 위 패널 안테나 셋(120° 간격), 아래 장비함. 점등 뒤 꼭대기에서 전파 고리
      var g = new THREE.Group(); g.userData.lamp = true;
      g.add(K.mesh(K.lathe([[0, -2.0], [.17, -2.0, .03], [.11, -1.85], [.06, 1.95], [0, 1.95]], 20), M.steel));
      for (var i = 0; i < 3; i++) { var a = i * Math.PI * 2 / 3 + .3, p = K.mesh(K.rbox(.1, .65, .2, .03), M.porcelain); p.position.set(.16 * Math.cos(a), 1.5, .16 * Math.sin(a)); p.rotation.y = -a; g.add(p); }
      var lamp = K.mesh(K.ball(.06), M.lamp); lamp.position.y = 2.0; g.add(lamp);
      var box = K.mesh(K.rbox(.32, .36, .26, .03), M.slate); box.position.set(-.26, -1.82, -.22); g.add(box);
      g.userData.emit = new THREE.Vector3(0, 2.0, 0);
      return g;
    },
    fence: function (K, M) {                // 울타리 — 반지름 0.91, 기둥 열넷(높이 0.5)과 위아래 가로대 고리
      var g = new THREE.Group();
      for (var i = 0; i < 14; i++) { var a = i / 14 * Math.PI * 2, c = K.mesh(K.cyl(.022, .022, .5, 8), M.ink); c.position.set(.91 * Math.cos(a), 0, .91 * Math.sin(a)); g.add(c); }
      [-.15, .2].forEach(function (y) { var t = K.mesh(new THREE.TorusGeometry(.91, .016, 6, 72), M.ink); t.rotation.x = Math.PI / 2; t.position.y = y; g.add(t); });
      return g;
    },
    ring1: emfRing(1.3, 1.55, 'porcelain'),  // 1등급 — 가장 바깥, 가장 낮다
    ring2: emfRing(1.0, 1.22, 'rule'),
    ring3: emfRing(.62, .84, 'muted'),      // 주의 — 울타리(0.91) 안
    ring4: emfRing(.24, .52, 'slate'),      // 경고 — 가장 안쪽, 가장 높다
    who: function (K, M) { return pair(K, M, 0); },      // 세계보건기구 정리 · 국제암연구소 2B — 나란히
    guide: function (K, M) { return pair(K, M, .18); }   // 2020년 개정 · 2019년판 — 엇갈려
  };

  // ── 16 무선국 검사 — 받침(닫힌 상자 — 다섯이 숨는다) · 무선설비 함(안테나) · 운용자 자리 · 검사증명서 판 · 달력 고리(다섯 마디) · 배·비행기 모형 ·
  // 위임 판 · 위탁 판 · 명판. 검사 장비의 기종은 그리지 않는다
  SHAPES['16-inspection'] = {
    base: function (K, M) {                 // 받침 2.8 × 0.6 × 2.0, 앞 띠(처음 3.4 × 2.2 는 가로 맞춤에 걸려 무선국이 작았다)
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(2.8, .6, 2.0, .06), M.slate));
      var strip = K.mesh(K.rbox(2.6, .05, .03, .01), M.rule, false); strip.position.set(0, .15, 1.01); g.add(strip);
      return g;
    },
    equip: function (K, M) {                // 무선설비 함 0.9 × 1.3 × 0.6 — 앞판 · 계기 둘(점등) · 위 짧은 안테나(점등 뒤 전파 고리)
      var g = new THREE.Group(); g.userData.lamp = true; g.add(K.mesh(K.rbox(.9, 1.3, .6, .05), M.porcelain));
      var face = K.mesh(K.rbox(.76, 1.1, .02, .02), M.rule, false); face.position.z = .31; g.add(face);
      [.3, 0].forEach(function (y) { var m = K.mesh(K.rbox(.4, .14, .02, .01), M.lamp, false); m.position.set(0, y, .325); g.add(m); });
      var ant = K.mesh(K.cyl(.02, .03, .9, 10), M.steel); ant.position.set(.25, 1.1, 0); g.add(ant);
      g.userData.emit = new THREE.Vector3(.25, 1.55, 0);
      return g;
    },
    operator: function (K, M) {             // 운용자 자리 — 작은 책상(0.9 × 0.08 × 0.6, 다리 넷) · 의자 · 책상 위 헤드셋
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(.9, .08, .6, .03), M.slate));
      [[-1, -1], [-1, 1], [1, -1], [1, 1]].forEach(function (s) { var l = K.mesh(K.rbox(.05, .4, .05, .02), M.ink); l.position.set(.4 * s[0], -.24, .26 * s[1]); g.add(l); });
      var hs = K.mesh(new THREE.TorusGeometry(.11, .02, 8, 24, Math.PI), M.ink); hs.position.set(-.1, .1, 0); g.add(hs);
      [-1, 1].forEach(function (s) { var c = K.mesh(K.cyl(.045, .045, .04, 16), M.ink); c.rotation.z = Math.PI / 2; c.position.set(-.1 + .11 * s, .08, 0); g.add(c); });
      var seat = K.mesh(K.rbox(.32, .06, .32, .03), M.muted); seat.position.set(.62, -.18, .05); g.add(seat);     // 의자는 책상 오른쪽 — 앞에 두면 2턴 판이 오를 길을 막는다
      var back = K.mesh(K.rbox(.05, .36, .32, .02), M.muted); back.position.set(.79, 0, .05); g.add(back);
      return g;
    },
    cert: function (K, M) {                 // 검사증명서 판 — 받침대에 세운 액자(0.6 × 0.42), 카메라 쪽으로 0.5 돌림. 글자 없음
      var g = new THREE.Group(), h = new THREE.Group(); h.rotation.y = .5; g.add(h);
      h.add(K.mesh(K.rbox(.6, .42, .04, .02), M.ink));
      var paper = K.mesh(K.rbox(.5, .32, .02, .01), M.porcelain, false); paper.position.z = .025; h.add(paper);
      var seal = K.mesh(K.cyl(.05, .05, .02, 20), M.steel, false); seal.rotation.x = Math.PI / 2; seal.position.set(.15, -.08, .04); h.add(seal);
      var leg = K.mesh(K.rbox(.05, .3, .05, .02), M.steel); leg.position.y = -.33; h.add(leg);
      return g;
    },
    cal: function (K, M) {                  // 달력 고리 — 누운 고리를 다섯 마디로(마디 사이 틈) = 5년 범위
      var g = new THREE.Group();
      for (var i = 0; i < 5; i++) { var t = K.mesh(new THREE.TorusGeometry(.32, .045, 8, 20, Math.PI * 2 / 5 - .12), i % 2 ? M.rule : M.slate); t.rotation.set(-Math.PI / 2, 0, i * Math.PI * 2 / 5); g.add(t); }
      var hub = K.mesh(K.cyl(.06, .06, .04, 16), M.ink); g.add(hub);
      return g;
    },
    trip: function (K, M) {                 // 배·비행기 작은 모형 — 판 위에 작은 배와 작은 비행기(외국 출항)
      var g = new THREE.Group(); g.add(K.mesh(K.rbox(.7, .04, .4, .015), M.porcelain));
      var hull = K.mesh(K.rbox(.3, .08, .12, .03), M.slate); hull.position.set(-.16, .06, .05); g.add(hull);
      var cab = K.mesh(K.rbox(.1, .07, .08, .02), M.rule); cab.position.set(-.18, .13, .05); g.add(cab);
      var fus = K.mesh(K.cyl(.035, .035, .32, 12), M.steel); fus.rotation.z = Math.PI / 2; fus.position.set(.17, .14, -.05); g.add(fus);
      var wing = K.mesh(K.rbox(.08, .012, .34, .004), M.steel); wing.position.set(.17, .14, -.05); g.add(wing);
      return g;
    },
    deleg: function (K, M) { return docPlate(K, M, .66, .44, M.porcelain, 3); },  // 위임 판
    entrust: function (K, M) { return docPlate(K, M, .66, .44, M.rule, 3); },     // 위탁 판
    plaque: function (K, M) { return docPlate(K, M, .66, .3, M.steel, 2); }       // 명판
  };

  // ── 07 해상무선통신 — 선박 무선국 한 척(선체 · 구명정 · 받침판 · 해역 고리 넷 · 무선실 · GMDSS 콘솔 · 비상위치표지 · 트랜스폰더 · 돛대와 안테나 줄)
  // 선체는 평면도(뾰족한 뱃머리)를 세로로 밀어 낸 모양 — ExtrudeGeometry 는 z 로 밀므로 x 축으로 −90° 돌려 높이를 y 로 맞춘다
  // 해역 고리 — 선체를 감싸는 납작한 타원 고리(폭 0.1, z 를 0.5 로 눌렀다). 라벨 없음(조율자 결정: 모양만). 원으로 두면(반지름 3.4)
  // 고리의 경계 상자가 카메라 맞춤을 정해 배 전체가 작아졌다 — 선체 길이(±2.85) 안팎으로 눌러 둔다
  function zoneRing(r) {
    return function (K, M) { var g = new THREE.Group();
      var m = K.mesh(K.lathe([[r - .05, -.02], [r + .05, -.02], [r + .05, .02], [r - .05, .02], [r - .05, -.02]], 96), M.rule, false); m.scale.set(1, 1, .5); g.add(m); return g; };
  }
  SHAPES['07-maritime'] = {
    hull: function (K, M) {                  // 선체 — 길이 5.6 · 폭 1.5 · 높이 1.0, 뱃머리 +x. 흘수선 띠와 갑판
      var g = new THREE.Group(), s = new THREE.Shape();
      s.moveTo(-2.8, -.75); s.lineTo(1.5, -.75); s.quadraticCurveTo(2.5, -.6, 2.85, 0); s.quadraticCurveTo(2.5, .6, 1.5, .75); s.lineTo(-2.8, .75); s.lineTo(-2.8, -.75);
      var geo = new THREE.ExtrudeGeometry(s, { depth: .9, bevelEnabled: true, bevelThickness: .05, bevelSize: .05, bevelSegments: 2, curveSegments: 16 });
      geo.rotateX(-Math.PI / 2); geo.translate(0, -.45, 0);
      g.add(K.mesh(geo, M.slate));
      var stripe = new THREE.ExtrudeGeometry(s, { depth: .08, bevelEnabled: false, curveSegments: 16 }); stripe.rotateX(-Math.PI / 2); stripe.scale(1.012, 1, 1.03); stripe.translate(0, .05, 0);
      g.add(K.mesh(stripe, M.porcelain, false));
      var deck = new THREE.ExtrudeGeometry(s, { depth: .04, bevelEnabled: false, curveSegments: 16 }); deck.rotateX(-Math.PI / 2); deck.scale(.96, 1, .9); deck.translate(0, .48, 0);
      g.add(K.mesh(deck, M.mist, false));
      return g;
    },
    boat: function (K, M) {                  // 구명정 — 반구를 늘인 배 바닥 + 테두리
      var g = new THREE.Group();
      var b = K.mesh(new THREE.SphereGeometry(.34, 32, 12, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2), M.porcelain); b.scale.set(2.4, 1.2, 1.1); g.add(b);
      var rim = K.mesh(new THREE.TorusGeometry(.34, .03, 8, 40), M.rule); rim.rotation.x = Math.PI / 2; rim.scale.set(2.4, 1.1, 1); g.add(rim);
      [-1, 1].forEach(function (s) { var t = K.mesh(K.rbox(.06, .02, .5, .01), M.muted, false); t.position.set(.25 * s, -.02, 0); g.add(t); });
      return g;
    },
    slab: function (K, M) {                  // 받침판 — 6.4 × 0.15 × 2.2(협약이 바탕)
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(6.4, .15, 2.2, .05), M.porcelain));
      var edge = K.mesh(K.rbox(6.2, .05, .03, .01), M.rule, false); edge.position.set(0, 0, 1.11); g.add(edge);
      return g;
    },
    zone1: zoneRing(1.8),
    zone2: zoneRing(2.2),
    zone3: zoneRing(2.6),
    zone4: zoneRing(3.0),
    house: function (K, M) {                 // 무선실 — 1.8 × 1.0 × 1.1, 창 띠(점등 때 켜진다)·문·지붕
      var g = new THREE.Group(); g.userData.lamp = true;
      g.add(K.mesh(K.rbox(1.8, 1.0, 1.1, .06), M.porcelain));
      var win = K.mesh(K.rbox(1.5, .22, 1.12, .03), M.lamp, false); win.position.y = .18; g.add(win);
      var door = K.mesh(K.rbox(.06, .6, .36, .02), M.ink, false); door.position.set(.91, -.18, 0); g.add(door);
      var roof = K.mesh(K.rbox(2.0, .1, 1.3, .04), M.rule); roof.position.y = .55; g.add(roof);
      return g;
    },
    console: function (K, M) {               // GMDSS 장비 콘솔 — 화면(점등)·손잡이 줄
      var g = new THREE.Group(); g.userData.lamp = true;
      g.add(K.mesh(K.rbox(.4, .6, .9, .04), M.slate));
      var scr = K.mesh(K.rbox(.04, .26, .6, .02), M.lamp, false); scr.position.set(.21, .1, 0); g.add(scr);
      [-.25, -.08, .08, .25].forEach(function (z) { var k = K.mesh(K.cyl(.035, .035, .05, 12), M.steel, false); k.rotation.z = Math.PI / 2; k.position.set(.22, -.17, z); g.add(k); });
      return g;
    },
    epirb: function (K, M) {                 // 406MHz 비상위치표지 — 원통 몸통·검은 머리·짧은 안테나. 점등 뒤 여기서 전파 고리
      var g = new THREE.Group(); g.userData.lamp = true;
      g.add(K.mesh(K.lathe([[0, -.25], [.13, -.25, .03], [.13, .12, .02], [.1, .17], [0, .17]], 24), M.porcelain));
      var head = K.mesh(K.cyl(.1, .1, .1, 24), M.lamp); head.position.y = .2; g.add(head);
      var ant = K.mesh(K.cyl(.012, .012, .3, 8), M.ink); ant.position.y = .4; g.add(ant);
      g.userData.emit = new THREE.Vector3(0, .55, 0);
      return g;
    },
    sart: function (K, M) {                  // 수색구조 트랜스폰더 — 가는 막대 몸통 + 띠
      var g = new THREE.Group();
      g.add(K.mesh(K.cyl(.07, .07, .5, 20), M.slate));
      var band = K.mesh(K.cyl(.075, .075, .06, 20), M.porcelain, false); band.position.y = .12; g.add(band);
      var cap = K.mesh(K.ball(.07), M.ink); cap.position.y = .27; g.add(cap);
      return g;
    },
    rig: function (K, M) {                   // 돛대 둘(x ±2.0, 높이 3.2)과 꼭대기 사이 안테나 줄, 줄 가운데서 무선실로 내려오는 끌어들임 줄
      var g = new THREE.Group();
      [-2.0, 2.0].forEach(function (x) {
        var m = K.mesh(K.lathe([[0, -1.6], [.09, -1.6, .02], [.06, -1.4], [.04, 1.6], [0, 1.6]], 16), M.steel); m.position.x = x; g.add(m);
        var yard = K.mesh(K.rbox(.06, .06, .7, .02), M.steel); yard.position.set(x, 1.2, 0); g.add(yard);
      });
      var wire = K.mesh(K.cyl(.018, .018, 4.0, 8), M.ink, false); wire.rotation.z = Math.PI / 2; wire.position.y = 1.5; g.add(wire);
      var lead = K.mesh(K.cyl(.014, .014, 1.9, 8), M.ink, false); lead.position.set(-.2, .55, 0); g.add(lead);
      return g;
    }
  };

  // ── 14 이동통신 — 계단 받침 · 세대별 단말 다섯(차량전화 · 막대 전화 · 접는 전화 · 4세대 · 5세대) · 20:1 막대 둘
  // 단말은 모두 서 있고 얼굴(+z)을 카메라 쪽으로 0.4 돌려 둔다(모양 묶음 자체를 돌린다 — 엔진은 부품 묶음만 움직인다).
  // 크기는 1.35 배(PH) — 1.0 이면 계단 폭(1.15)에 비해 단말이 작아 떠오른 뒤 무엇인지 안 읽혔다. 표의 rest·anchor 는 이 배율을 넣어 셌다
  var PH = 1.35;
  function screenFace(K, M, g, w, h, y, z, mat) { var s = K.mesh(K.rbox(w, h, .012, .01), mat || M.mist, false); s.position.set(0, y, z); g.add(s); }
  SHAPES['14-mobile'] = {
    stand: function (K, M) {                 // 계단 받침 — 다섯 계단(폭 1.15, 높이 0.3 씩), 앞 띠
      var g = new THREE.Group();
      for (var k = 0; k < 5; k++) { var h = .3 * (k + 1), s = K.mesh(K.rbox(1.15, h, 1.4, .04), k % 2 ? M.rule : M.porcelain); s.position.set(-2.4 + 1.2 * k, h / 2, 0); g.add(s); }
      var strip = K.mesh(K.rbox(5.9, .05, .03, .01), M.muted, false); strip.position.set(0, .05, .71); g.add(strip);
      return g;
    },
    car: function (K, M) {                   // 차량전화 — 본체 상자 위에 누운 수화기, 감긴 줄
      var g = new THREE.Group(); g.rotation.y = .4; g.scale.setScalar(PH);
      g.add(K.mesh(K.rbox(.95, .25, .55, .05), M.slate));
      var hs = K.mesh(K.rbox(.8, .1, .17, .04), M.ink); hs.position.set(0, .2, .05); g.add(hs);
      [-1, 1].forEach(function (s) { var e = K.mesh(K.rbox(.2, .12, .24, .05), M.ink); e.position.set(.36 * s, .17, .05); g.add(e); });
      for (var i = 0; i < 6; i++) { var c = K.mesh(new THREE.TorusGeometry(.045, .012, 6, 16), M.muted, false); c.rotation.y = Math.PI / 2; c.position.set(-.5 - i * .05, .02, .2); g.add(c); }
      var keys = K.mesh(K.rbox(.4, .02, .22, .01), M.steel, false); keys.position.set(.18, .13, -.12); g.add(keys);
      return g;
    },
    g2: function (K, M) {                    // 막대 전화(1996) — 몸통 · 작은 화면 · 숫자판 · 짧은 안테나
      var g = new THREE.Group(); g.rotation.y = .4; g.scale.setScalar(PH);
      g.add(K.mesh(K.rbox(.46, 1.05, .2, .08), M.slate));
      screenFace(K, M, g, .32, .26, .27, .105);
      for (var r = 0; r < 4; r++) for (var c = 0; c < 3; c++) { var b = K.mesh(K.rbox(.08, .055, .02, .01), M.steel, false); b.position.set(-.1 + c * .1, -.06 - r * .085, .105); g.add(b); }
      var ant = K.mesh(K.cyl(.035, .045, .3, 12), M.ink); ant.position.set(.14, .65, 0); g.add(ant);
      return g;
    },
    g3: function (K, M) {                    // 접는 전화(2003) — 아래 반쪽(숫자판) · 경첩 · 뒤로 젖힌 위 반쪽(화면)
      var g = new THREE.Group(); g.rotation.y = .4; g.scale.setScalar(PH);
      var lo = K.mesh(K.rbox(.48, .55, .12, .06), M.slate); lo.position.y = -.27; g.add(lo);
      for (var r = 0; r < 4; r++) for (var c = 0; c < 3; c++) { var b = K.mesh(K.rbox(.08, .05, .02, .01), M.steel, false); b.position.set(-.1 + c * .1, -.12 - r * .085, .065); g.add(b); }
      var hinge = K.mesh(K.cyl(.05, .05, .44, 16), M.ink); hinge.rotation.z = Math.PI / 2; hinge.position.y = .02; g.add(hinge);
      var up = new THREE.Group(); up.position.y = .02; up.rotation.x = -.3; g.add(up);
      var top = K.mesh(K.rbox(.48, .55, .1, .06), M.slate); top.position.y = .28; up.add(top);
      var scr = K.mesh(K.rbox(.36, .36, .012, .01), M.mist, false); scr.position.set(0, .3, .055); up.add(scr);
      return g;
    },
    g4: function (K, M) {                    // 4세대(2011) — 화면이 큰 판 · 아래 동그란 단추
      var g = new THREE.Group(); g.rotation.y = .4; g.scale.setScalar(PH);
      g.add(K.mesh(K.rbox(.6, 1.15, .11, .07), M.ink));
      screenFace(K, M, g, .5, .86, .03, .06);
      var btn = K.mesh(K.cyl(.045, .045, .02, 20), M.muted, false); btn.rotation.x = Math.PI / 2; btn.position.set(0, -.49, .058); g.add(btn);
      return g;
    },
    g5: function (K, M) {                    // 5세대(2019) — 얇고 긴 판 · 앞면 가득한 화면(점등) · 뒤 카메라. 점등 뒤 위에서 전파 고리
      var g = new THREE.Group(); g.rotation.y = .4; g.scale.setScalar(PH); g.userData.lamp = true;
      g.add(K.mesh(K.rbox(.64, 1.3, .08, .07), M.slate));
      screenFace(K, M, g, .58, 1.22, 0, .043, M.lamp);
      var cam = K.mesh(K.rbox(.2, .2, .03, .04), M.ink, false); cam.position.set(-.16, .48, -.05); g.add(cam);
      g.userData.emit = new THREE.Vector3(0, .8, 0);
      return g;
    },
    bar20: function (K, M) {                 // 20기가비트 막대 — 높이 1.4(1기가비트 막대의 20배). 가장 높은 계단(1.5) 속에 다 들어가는 높이
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(.26, 1.4, .26, .03), M.slate));
      var cap = K.mesh(K.rbox(.28, .04, .28, .01), M.steel, false); cap.position.y = .7; g.add(cap);
      return g;
    },
    bar1: function (K, M) {                  // 1기가비트 막대 — 높이 0.07
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(.26, .07, .26, .02), M.slate));
      return g;
    }
  };

  // ── 17 행성 탐사 — 지면판 · 로버(차체 · 마스트 카메라 · 접시 안테나 · 바퀴 묶음 둘) · 루노호트 1호 · 아폴로 월면차
  SHAPES['17-rover'] = {
    ground: function (K, M) {                // 전시 받침 — 5.2 × 0.9 × 3.0(속에 두 차가 숨는다 — 닫힌 상자), 윗면 분화구 고리 셋과 돌
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(5.2, .9, 3.0, .06), M.porcelain));
      var top = K.mesh(K.rbox(5.0, .04, 2.8, .02), M.mist, false); top.position.y = .45; g.add(top);
      [[-1.5, .9, .38], [1.6, .8, .28], [.2, -1.0, .3]].forEach(function (c) { var r = K.mesh(new THREE.TorusGeometry(c[2], .04, 8, 40), M.rule, false); r.rotation.x = Math.PI / 2; r.position.set(c[0], .47, c[1]); g.add(r); });
      [[-.6, 1.1, .09], [2.1, .2, .12], [-2.1, -.5, .1], [.5, 1.2, .07]].forEach(function (p) { var st = K.mesh(K.ball(p[2]), M.muted); st.position.set(p[0], .49, p[1]); st.scale.y = .6; g.add(st); });
      return g;
    },
    body: function (K, M) {                  // 차체 — 2.2 × 0.5 × 1.4, 위 갑판 · 뒤 상자 · 앞 범퍼
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(2.2, .5, 1.4, .07), M.porcelain));
      var deck = K.mesh(K.rbox(2.0, .06, 1.2, .02), M.rule); deck.position.y = .28; g.add(deck);
      var box = K.mesh(K.rbox(.4, .4, .5, .04), M.slate); box.position.set(-1.0, .25, 0); box.rotation.z = .5; g.add(box);
      var bump = K.mesh(K.rbox(.1, .18, 1.2, .03), M.slate); bump.position.set(1.13, -.1, 0); g.add(bump);
      return g;
    },
    mastcam: function (K, M) {               // 마스트 카메라 — 기둥(높이 1.2)과 머리(두 눈은 점등 때 켜진다)
      var g = new THREE.Group(); g.userData.lamp = true;
      g.add(K.mesh(K.lathe([[0, -.6], [.1, -.6, .02], [.06, -.5], [.05, .5], [0, .5]], 16), M.steel));
      var head = K.mesh(K.rbox(.3, .24, .52, .04), M.slate); head.position.y = .62; g.add(head);
      [-.12, .12].forEach(function (z) { var e = K.mesh(K.cyl(.06, .06, .06, 20), M.lamp); e.rotation.z = Math.PI / 2; e.position.set(.17, .64, z); g.add(e); });
      return g;
    },
    dish: function (K, M) {                  // 접시 안테나 — 기둥 위 기울인 둥근 접시와 급전 막대. 점등 뒤 여기서 전파 고리
      var g = new THREE.Group();
      g.add(K.mesh(K.cyl(.05, .07, .5, 12), M.steel));
      var head = new THREE.Group(); head.position.y = .3; head.rotation.z = .5; g.add(head);
      M.porcelain.side = THREE.DoubleSide;      // 접시 안쪽(오목한 면)도 보이게 — 이 부품만의 재질이라 다른 부품에 번지지 않는다
      var cup = K.mesh(new THREE.SphereGeometry(.75, 40, 10, 0, Math.PI * 2, 0, .62), M.porcelain); cup.position.y = -.6; head.add(cup);
      var feed = K.mesh(K.cyl(.02, .02, .45, 8), M.ink); feed.position.y = .02; head.add(feed);
      var tip = K.mesh(K.ball(.05), M.ink); tip.position.y = .25; head.add(tip);
      g.userData.emit = new THREE.Vector3(-.15, .62, 0);
      return g;
    },
    wheels: function (K, M) {                // 한쪽 바퀴 묶음 — 바퀴 셋(반지름 0.32)과 흔들 팔(로커·보기)
      var g = new THREE.Group();
      [-.85, 0, .85].forEach(function (x) {
        var t = K.mesh(K.cyl(.32, .32, .22, 32), M.slate); t.rotation.x = Math.PI / 2; t.position.x = x; g.add(t);
        var hub = K.mesh(K.cyl(.12, .12, .24, 20), M.steel); hub.rotation.x = Math.PI / 2; hub.position.x = x; g.add(hub);
      });
      [[-.85, -.2], [-.2, .35], [.85, .35]].forEach(function (a) {      // 팔 셋 — [아래 끝 x(바퀴 높이), 위 끝 x(높이 0.38)], 위 끝이 축으로 모인다
        var x0 = a[0], x1 = a[1], y0 = 0, y1 = .38;
        var len = Math.hypot(x1 - x0, y1 - y0), bar = K.mesh(K.rbox(len, .06, .06, .02), M.steel);
        bar.position.set((x0 + x1) / 2, (y0 + y1) / 2, 0); bar.rotation.z = Math.atan2(y1 - y0, x1 - x0); g.add(bar);
      });
      var piv = K.mesh(K.cyl(.07, .07, .12, 16), M.ink); piv.rotation.x = Math.PI / 2; piv.position.set(.35, .38, 0); g.add(piv);
      return g;
    },
    luno: function (K, M) {                  // 루노호트 1호 — 위가 넓은 통 몸체 · 둥근 뚜껑 · 바퀴 여덟 · 짧은 안테나(0.8 배 — 받침 속에 들어가는 크기)
      var g = new THREE.Group(); g.scale.setScalar(.8);
      g.add(K.mesh(K.lathe([[0, -.22], [.52, -.22, .08], [.7, .14, .04], [.74, .2], [0, .2]], 40), M.porcelain));
      var lid = K.mesh(K.lathe([[0, -.02], [.76, -.02, .02], [.6, .12, .08], [0, .17]], 40), M.steel); lid.position.y = .22; g.add(lid);
      [-1, 1].forEach(function (s) { for (var i = 0; i < 4; i++) { var w = K.mesh(K.cyl(.15, .15, .09, 20), M.slate); w.rotation.x = Math.PI / 2; w.position.set(-.48 + i * .32, -.33, .58 * s); g.add(w); } });
      var ant = K.mesh(K.cyl(.012, .012, .3, 8), M.ink); ant.position.set(.3, .42, .2); ant.rotation.z = -.3; g.add(ant);
      return g;
    },
    lrv: function (K, M) {                   // 아폴로 월면차 — 열린 틀 차대 · 바퀴 넷 · 의자 둘 · 조종대 · 작은 우산 안테나(0.8 배)
      var g = new THREE.Group(); g.scale.setScalar(.8);
      g.add(K.mesh(K.rbox(1.8, .08, .8, .03), M.steel));
      [[-.65, -1], [-.65, 1], [.65, -1], [.65, 1]].forEach(function (p) { var w = K.mesh(K.cyl(.28, .28, .16, 28), M.slate); w.rotation.x = Math.PI / 2; w.position.set(p[0], -.12, .5 * p[1]); g.add(w);
        var f = K.mesh(K.rbox(.6, .03, .2, .01), M.rule, false); f.position.set(p[0], .2, .5 * p[1]); g.add(f); });
      [-.18, .18].forEach(function (z) { var s = K.mesh(K.rbox(.36, .06, .3, .02), M.porcelain); s.position.set(-.1, .1, z); g.add(s);
        var b = K.mesh(K.rbox(.05, .32, .3, .02), M.porcelain); b.position.set(-.28, .25, z); g.add(b); });
      var post = K.mesh(K.cyl(.03, .03, .4, 8), M.ink); post.position.set(.35, .25, 0); g.add(post);
      var mast = K.mesh(K.cyl(.015, .015, .3, 8), M.steel); mast.position.set(.75, .3, -.25); g.add(mast);
      var umb = K.mesh(K.cyl(.02, .26, .08, 20), M.porcelain); umb.position.set(.75, .47, -.25); g.add(umb);
      return g;
    }
  };

  // ── 18 과학 원리 — 선반 · 테레민(상자 · 뚜껑 · 발진기 판 · 세운 막대) · 패러데이 고리 · 테슬라 코일 · 코히러·오실로스코프 상자
  SHAPES['18-science'] = {
    shelf: function (K, M) {                 // 선반 — 6.0 × 0.3 × 2.6, 앞 띠
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(6.0, .3, 2.6, .07), M.porcelain));
      var strip = K.mesh(K.rbox(5.7, .07, .03, .01), M.rule, false); strip.position.set(0, 0, 1.31); g.add(strip);
      return g;
    },
    cabinet: function (K, M) {               // 테레민 상자 — 2.2 × 0.62 × 0.9(닫힌 상자 — 발진기 판이 속에 숨는다), 앞 스피커 구멍 · 손잡이 둘 · 왼쪽 볼륨 고리
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(2.2, .62, .9, .05), M.slate));
      for (var r = 0; r < 3; r++) for (var c = 0; c < 5; c++) { var h = K.mesh(K.cyl(.035, .035, .02, 12), M.ink, false); h.rotation.x = Math.PI / 2; h.position.set(-.55 + c * .1, .12 - r * .1, .455); g.add(h); }
      [.35, .6].forEach(function (x) { var k = K.mesh(K.cyl(.07, .07, .06, 20), M.steel); k.rotation.x = Math.PI / 2; k.position.set(x, -.1, .47); g.add(k); });
      var arm = K.mesh(K.rbox(.3, .05, .05, .02), M.steel); arm.position.set(-1.25, .05, 0); g.add(arm);
      var loop = K.mesh(new THREE.TorusGeometry(.3, .028, 10, 40), M.steel); loop.rotation.x = Math.PI / 2; loop.position.set(-1.68, .05, 0); g.add(loop);
      var sock = K.mesh(K.cyl(.08, .1, .1, 16), M.ink); sock.position.set(1.0, .36, -.15); g.add(sock);
      return g;
    },
    lid: function (K, M) {                   // 뚜껑 — 2.3 × 0.08 × 1.0, 손잡이
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(2.3, .08, 1.0, .03), M.rule));
      var hd = K.mesh(K.rbox(.5, .05, .08, .02), M.steel); hd.position.set(-.3, .065, 0); g.add(hd);
      return g;
    },
    board: function (K, M) {                 // 발진기 판 — 판(점등) 위 발진기 통 둘과 가운데 섞는 칩, 작은 부품들
      var g = new THREE.Group(); g.userData.lamp = true;
      g.add(K.mesh(K.rbox(1.6, .05, .6, .02), M.lamp));
      [-.42, .42].forEach(function (x) { var c = K.mesh(K.cyl(.16, .16, .32, 24), M.steel); c.position.set(x, .18, 0); g.add(c);
        var t = K.mesh(K.cyl(.1, .1, .03, 20), M.ink, false); t.position.set(x, .35, 0); g.add(t); });
      var mix = K.mesh(K.rbox(.22, .08, .16, .02), M.ink); mix.position.set(0, .07, 0); g.add(mix);
      [[-.7, .2], [.7, -.2], [.05, -.22], [-.1, .22]].forEach(function (p) { var b = K.mesh(K.rbox(.08, .05, .05, .01), M.slate, false); b.position.set(p[0], .05, p[1]); g.add(b); });
      return g;
    },
    rod: function (K, M) {                   // 세운 막대(높이 1.6) — 아래 애자, 끝 구슬
      var g = new THREE.Group();
      g.add(K.mesh(K.cyl(.03, .03, 1.6, 12), M.steel));
      var ins = K.mesh(K.lathe([[0, -.12], [.09, -.12, .02], [.06, -.04], [.09, .04, .02], [0, .1]], 20), M.porcelain); ins.position.y = -.72; g.add(ins);
      var tip = K.mesh(K.ball(.06), M.steel); tip.position.y = .82; g.add(tip);
      return g;
    },
    ring: function (K, M) {                  // 패러데이 고리 — 세운 쇠고리(반지름 0.4)와 좌우의 감은 줄 둘, 받침
      var g = new THREE.Group();
      var r = K.mesh(new THREE.TorusGeometry(.4, .09, 14, 48), M.steel); r.position.y = .08; g.add(r);
      [-1, 1].forEach(function (s) { var c = K.mesh(K.cyl(.14, .14, .3, 24), M.rule); c.position.set(.4 * s, .08, 0); g.add(c);   // 고리 좌우에 세운 감은 줄
        for (var i = 0; i < 4; i++) { var w = K.mesh(new THREE.TorusGeometry(.145, .012, 6, 24), M.muted, false); w.rotation.x = Math.PI / 2; w.position.set(.4 * s, -.03 + i * .075, 0); g.add(w); } });
      var base = K.mesh(K.rbox(1.1, .1, .45, .03), M.slate); base.position.y = -.46; g.add(base);
      return g;
    },
    tesla: function (K, M) {                 // 테슬라 코일 — 받침 · 바닥 나선(1차) · 길쭉한 감은 통(2차) · 꼭대기 도넛
      var g = new THREE.Group();
      var base = K.mesh(K.rbox(.9, .14, .9, .04), M.slate); base.position.y = -.63; g.add(base);
      [.22, .3, .38].forEach(function (r) { var p = K.mesh(new THREE.TorusGeometry(r, .018, 6, 32), M.steel, false); p.rotation.x = Math.PI / 2; p.position.y = -.54; g.add(p); });
      var sec = K.mesh(K.cyl(.12, .12, 1.0, 24), M.rule); sec.position.y = -.05; g.add(sec);
      for (var i = 0; i < 9; i++) { var w = K.mesh(new THREE.TorusGeometry(.122, .01, 6, 24), M.muted, false); w.rotation.x = Math.PI / 2; w.position.y = -.48 + i * .11; g.add(w); }
      var top = K.mesh(new THREE.TorusGeometry(.26, .09, 12, 36), M.steel); top.rotation.x = Math.PI / 2; top.position.y = .52; g.add(top);
      return g;
    },
    scope: function (K, M) {                 // 화면 상자 — 오실로스코프 몸통 · 둥근 화면(점등) · 위에 코히러(유리관과 양 끝 전극)
      var g = new THREE.Group(); g.userData.lamp = true;
      g.add(K.mesh(K.rbox(.75, .5, .5, .04), M.slate));
      var scr = K.mesh(K.cyl(.17, .17, .03, 28), M.lamp, false); scr.rotation.x = Math.PI / 2; scr.position.set(-.12, .02, .255); g.add(scr);
      [.18, .3].forEach(function (x) { var k = K.mesh(K.cyl(.04, .04, .04, 12), M.steel, false); k.rotation.x = Math.PI / 2; k.position.set(x, .02, .26); g.add(k); });
      var tube = K.mesh(K.cyl(.05, .05, .5, 16), M.glass, false); tube.rotation.z = Math.PI / 2; tube.position.y = .33; g.add(tube);
      [-1, 1].forEach(function (s) { var e = K.mesh(K.cyl(.035, .035, .1, 12), M.steel); e.rotation.z = Math.PI / 2; e.position.set(.28 * s, .33, 0); g.add(e);
        var st = K.mesh(K.cyl(.02, .02, .1, 8), M.steel); st.position.set(.28 * s, .29, 0); g.add(st); });
      return g;
    }
  };

  // ── 19 마무리 — 계보 위에 관리 체계: 아래 판(02 의 세 부품 축소판) · 가운데 판(방송탑 · 단말) · 열린 틀(방패판 · 계측기) · 선 상자(아직 연구 중)
  SHAPES['19-closing'] = {
    lineage: function (K, M) {               // 아래 판 — 5.0 × 0.4 × 3.0, 02 의 받침(이론)·쌍극자(실증)·송신 장치(실용화)를 0.32 배로 나란히, 모서리 기둥 넷(가운데 판을 받친다)
      var g = new THREE.Group(), s2 = SHAPES['02-history'];
      g.add(K.mesh(K.rbox(5.0, .4, 3.0, .07), M.porcelain));
      [['pedestal', -1.4, .39], ['dipole', 0, .45], ['cabinet', 1.4, .44]].forEach(function (a) { var m = s2[a[0]](K, M); m.scale.setScalar(.32); m.position.set(a[1], a[2], 0); g.add(m); });
      [[-1, -1], [-1, 1], [1, -1], [1, 1]].forEach(function (p) { var c = K.mesh(K.rbox(.14, .8, .14, .03), M.slate); c.position.set(2.2 * p[0], .6, 1.2 * p[1]); g.add(c); });
      return g;
    },
    bcast: function (K, M) {                 // 가운데 판 — 4.4 × 0.3 × 2.6, 방송탑(높이 1.5, 끝 등이 점등)과 세운 단말. 점등 뒤 탑 끝에서 전파 고리
      var g = new THREE.Group(); g.userData.lamp = true;
      g.add(K.mesh(K.rbox(4.4, .3, 2.6, .06), M.rule));
      var mast = K.mesh(K.lathe([[0, -.75], [.16, -.75, .03], [.12, -.6], [.04, .75], [0, .75]], 20), M.steel); mast.position.set(-.6, .9, -.2); g.add(mast);
      [.35, .7, 1.05].forEach(function (y, i) { var a = K.mesh(K.rbox(.7 - i * .15, .04, .04, .01), M.steel); a.position.set(-.6, .15 + y, -.2); g.add(a); });
      var top = K.mesh(K.ball(.08), M.lamp); top.position.set(-.6, 1.68, -.2); g.add(top);
      var ph = K.mesh(K.rbox(.45, .9, .07, .05), M.slate); ph.position.set(1.0, .6, .2); ph.rotation.y = .4; g.add(ph);
      var sc = K.mesh(K.rbox(.4, .82, .012, .01), M.mist, false); sc.position.set(1.0 + .036 * Math.sin(.4), .6, .2 + .036 * Math.cos(.4)); sc.rotation.y = .4; g.add(sc);
      g.userData.emit = new THREE.Vector3(-.6, 1.72, -.2);
      return g;
    },
    frame: function (K, M) {                 // 열린 틀 — 기둥 넷(높이 1.6)과 위 테두리(속이 보이게 판이 아니라 테)
      var g = new THREE.Group();
      [[-1, -1], [-1, 1], [1, -1], [1, 1]].forEach(function (p) { var c = K.mesh(K.rbox(.12, 1.6, .12, .03), M.steel); c.position.set(1.9 * p[0], 0, 1.1 * p[1]); g.add(c); });
      [[0, 1.1, 3.92, .12], [0, -1.1, 3.92, .12]].forEach(function (b) { var m = K.mesh(K.rbox(b[2], .12, b[3], .03), M.steel); m.position.set(b[0], .8, b[1]); g.add(m); });
      [-1.9, 1.9].forEach(function (x) { var m = K.mesh(K.rbox(.12, .12, 2.32, .03), M.steel); m.position.set(x, .8, 0); g.add(m); });
      var hub = K.mesh(K.rbox(.9, .06, .9, .02), M.slate); hub.position.y = .8; g.add(hub);       // 가운데 받침 — 선 상자가 놓인다
      return g;
    },
    guard: function (K, M) {                 // 방패판 — 위가 평평하고 아래가 뾰족한 방패(높이 0.9)를 세운다
      var g = new THREE.Group(), s = new THREE.Shape();
      s.moveTo(-.38, .45); s.lineTo(.38, .45); s.lineTo(.38, 0); s.quadraticCurveTo(.3, -.32, 0, -.45); s.quadraticCurveTo(-.3, -.32, -.38, 0); s.lineTo(-.38, .45);
      var geo = new THREE.ExtrudeGeometry(s, { depth: .08, bevelEnabled: true, bevelThickness: .02, bevelSize: .02, bevelSegments: 2, curveSegments: 12 }); geo.translate(0, 0, -.04);
      g.add(K.mesh(geo, M.porcelain));
      var band = K.mesh(K.rbox(.6, .08, .02, .01), M.rule, false); band.position.set(0, .2, .07); g.add(band);
      var foot = K.mesh(K.rbox(.4, .06, .3, .02), M.slate); foot.position.y = -.5; g.add(foot);
      return g;
    },
    insp: function (K, M) {                  // 계측기 — 상자 · 둥근 눈금판과 바늘 · 옆의 측정봉
      var g = new THREE.Group();
      g.add(K.mesh(K.rbox(.62, .5, .36, .04), M.slate));
      var dial = K.mesh(K.cyl(.17, .17, .02, 28), M.mist, false); dial.rotation.x = Math.PI / 2; dial.position.set(-.08, .04, .185); g.add(dial);
      var needle = K.mesh(K.rbox(.015, .14, .01, .004), M.ink, false); needle.position.set(-.05, .08, .2); needle.rotation.z = -.5; g.add(needle);
      var probe = K.mesh(K.cyl(.025, .025, .55, 10), M.steel); probe.position.set(.42, .1, 0); probe.rotation.z = -.35; g.add(probe);
      var ptip = K.mesh(K.ball(.05), M.ink); ptip.position.set(.51, .36, 0); g.add(ptip);
      return g;
    },
    open: function (K, M) {                  // 선 상자(한 변 0.9) — 모서리 열둘만 있는 빈 상자 + 옅은 유리 속. "아직 연구가 계속" 이라 속이 비어 있다
      var g = new THREE.Group(), h = .45;
      for (var a = -1; a <= 1; a += 2) for (var b = -1; b <= 1; b += 2) {
        var x = K.mesh(K.rbox(.9, .035, .035, .01), M.muted); x.position.set(0, a * h, b * h); g.add(x);
        var y = K.mesh(K.rbox(.035, .9, .035, .01), M.muted); y.position.set(a * h, 0, b * h); g.add(y);
        var z = K.mesh(K.rbox(.035, .035, .9, .01), M.muted); z.position.set(a * h, b * h, 0); g.add(z);
      }
      g.add(K.mesh(K.rbox(.82, .82, .82, .02), M.glass, false));
      return g;
    }
  };
