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
