  // ═════════════════════════════════════════════ 형상 도구 (빌더가 template.html 의 /*__PARTS__*/ 자리에 넣는다)
  // 모델 파일 없이 코드로 부품을 만든다. 부품마다 **자기 중심을 원점**(긴 축 = y)으로 짓는다 — 그래야 표의 rest 로 놓고 제자리에서
  // 돌고 기울 수 있다. 시각을 읽지 않는다(움직임은 전부 엔진이 표로 정한다).
  //
  // profile()·offset 의 필렛 계산은 aimotion 148(https://github.com/kstost/cokacmotion, MIT © 2026 kstost)의 parts.js 에서 옮겼다:
  // 꺾인 단면의 모서리마다 접점 거리 d = r·tan(θ/2)(양옆 변의 48% 까지)의 이차 곡선을 넣어 모든 테두리가 둥근 베벨이 되고,
  // LatheGeometry 의 평균 법선이 매끈하게 비춘다. 단면은 반시계(바깥 위로 → 윗면 안쪽으로)로 적어야 법선이 바깥을 향한다.

  /** HUD 토큰에서 고른 재질 색. 강조는 SIG 하나뿐이다(외곽선·강조 라벨·점등) */
  var PAL = { bg: '#F3F7FA', mist: '#E8F3F8', rule: '#C3D9E6', ink: '#0E2433', muted: '#52636F', sig: '#0B7FB5',
    porcelain: '#F6F8FA', slate: '#33495A', steel: '#B9C3CC', glass: '#DCEAF2' };

  /** [[r, y, fillet], …] → Vector2[] — 모서리 i 를 (P − d·a) 에서 (P + d·b) 로 가는 이차 곡선(조절점 P)으로 바꾼다 */
  function profile(pts) {
    var out = [new THREE.Vector2(pts[0][0], pts[0][1])];
    for (var i = 1; i < pts.length - 1; i++) {
      var p = pts[i - 1], c = pts[i], q = pts[i + 1], f = c[2] || 0;
      if (!f) { out.push(new THREE.Vector2(c[0], c[1])); continue; }
      var ax = c[0] - p[0], ay = c[1] - p[1], bx = q[0] - c[0], by = q[1] - c[1], la = Math.hypot(ax, ay), lb = Math.hypot(bx, by);
      ax /= la; ay /= la; bx /= lb; by /= lb;
      var th = Math.acos(Math.max(-1, Math.min(1, ax * bx + ay * by))), d = Math.min(f * Math.tan(th / 2), .48 * la, .48 * lb);
      var sx = c[0] - ax * d, sy = c[1] - ay * d, ex = c[0] + bx * d, ey = c[1] + by * d, n = Math.max(2, Math.min(9, Math.ceil(th / .19)));
      for (var k = 0; k <= n; k++) { var u = k / n, A = (1 - u) * (1 - u), B = 2 * (1 - u) * u, C = u * u; out.push(new THREE.Vector2(A * sx + B * c[0] + C * ex, A * sy + B * c[1] + C * ey)); }
    }
    var L = pts[pts.length - 1]; out.push(new THREE.Vector2(L[0], L[1]));
    return out;
  }
  function lathe(pts, seg) { return new THREE.LatheGeometry(profile(pts), seg || 64); }
  function rbox(w, h, d, r) { return new RoundedBoxGeometry(w, h, d, 3, Math.min(r == null ? .08 : r, w / 2.2, h / 2.2, d / 2.2)); }
  function cyl(r0, r1, h, seg) { return new THREE.CylinderGeometry(r0, r1, h, seg || 48); }
  function ball(r) { return new THREE.SphereGeometry(r, 40, 24); }

  /**
   * 껍질 외곽선용 법선 — 같은 자리 꼭짓점들의 법선을 평균한다. 상자·원기둥은 모서리에서 법선이 갈라져 있어서, 그대로 밀어 내면
   * 껍질에 틈이 벌어져 외곽선이 끊긴다(위치로 묶어 평균하면 모서리가 둥글게 부풀어 닫힌다).
   */
  function hullNormals(geo) {
    var p = geo.attributes.position, n = geo.attributes.normal, map = {}, out = new Float32Array(p.count * 3), i, k, key;
    for (i = 0; i < p.count; i++) { key = Math.round(p.getX(i) * 1e4) + ',' + Math.round(p.getY(i) * 1e4) + ',' + Math.round(p.getZ(i) * 1e4);
      (map[key] = map[key] || []).push(i); }
    for (key in map) { var ids = map[key], sx = 0, sy = 0, sz = 0;
      for (k = 0; k < ids.length; k++) { sx += n.getX(ids[k]); sy += n.getY(ids[k]); sz += n.getZ(ids[k]); }
      var l = Math.hypot(sx, sy, sz) || 1; for (k = 0; k < ids.length; k++) { out[ids[k] * 3] = sx / l; out[ids[k] * 3 + 1] = sy / l; out[ids[k] * 3 + 2] = sz / l; } }
    return out;
  }
  /** 역방향 껍질: 위치를 매끈한 법선으로 w 만큼 밀어 뒷면만 그린다 → 실루엣 바깥 테두리만 남는다(톤 매핑 없음) */
  function hullMaterial() {
    return new THREE.ShaderMaterial({ uniforms: { uColor: { value: new THREE.Color(PAL.sig) }, uOpacity: { value: 0 }, uW: { value: .06 } },
      vertexShader: 'attribute vec3 hullN; uniform float uW; void main(){ gl_Position = projectionMatrix * modelViewMatrix * vec4(position + hullN * uW, 1.0); }',
      fragmentShader: 'uniform vec3 uColor; uniform float uOpacity; void main(){ gl_FragColor = vec4(uColor, uOpacity); }',
      side: THREE.BackSide, transparent: true, depthWrite: false });
  }

  /**
   * 재질 묶음. 부품마다 따로 만든다(make 를 부품마다 부른다) — 강조 때 "나머지 흐리게" 를 부품 단위 색 섞기로 하기 때문이다.
   * 무광 면은 빛과 구면 조화 LightProbe 로만 채우고, 금속·유리만 환경 반사를 받는다(aimotion 148 의 비용 분리 — 화면 대부분을
   * 덮는 무광 면이 큐브 맵을 매 픽셀 읽지 않게).
   */
  function makeMaterials(envTex) {
    function std(color, rough, metal, env) { var m = new THREE.MeshStandardMaterial({ color: color, roughness: rough, metalness: metal || 0 });
      if (env) { m.envMap = envTex; m.envMapIntensity = .9; } m.userData.base = new THREE.Color(color); return m; }
    return {
      porcelain: std(PAL.porcelain, .62), rule: std(PAL.rule, .55), mist: std(PAL.mist, .6), slate: std(PAL.slate, .5),
      ink: std(PAL.ink, .45), muted: std(PAL.muted, .5), steel: std(PAL.steel, .32, .85, true), dark: std('#26313B', .38, .6, true),
      glass: (function () { var m = std(PAL.glass, .12, .1, true); m.transparent = true; m.opacity = .55; m.depthWrite = false; return m; })(),
      lamp: (function () { var m = std('#AFC2CF', .35); m.emissive = new THREE.Color(PAL.sig); m.emissiveIntensity = 0; return m; })()
    };
  }
  function mesh(geo, mat, cast) { var m = new THREE.Mesh(geo, mat); m.castShadow = cast !== false; return m; }
  /** 모양 함수에 넘기는 도구 상자 */
  var KIT = { profile: profile, lathe: lathe, rbox: rbox, cyl: cyl, ball: ball, mesh: mesh, PAL: PAL };
