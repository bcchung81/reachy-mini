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
