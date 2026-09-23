import json
import pathlib
import re

PAGE = pathlib.Path(__file__).parent.parent / "stage" / "dashboard_page.html"
IDS = ["conn", "cue-label", "level", "mon-mc", "mon-docent", "tag-mc", "tag-docent",
       "cap-mc", "cap-docent", "rundown", "goto-bar", "goto-confirm", "goto-cancel",
       "btn-prev", "btn-restart", "btn-next", "btn-start", "btn-abort",
       "auto-text", "auto-bar", "log",
       "vid-mc", "vid-docent", "cam-reason-mc", "cam-reason-docent",
       "cam-toggle-mc", "cam-toggle-docent", "standby-toggle-mc", "standby-toggle-docent"]


def _src():
    return PAGE.read_text(encoding="utf-8")


def test_필수_요소가_전부_있다():
    src = _src()
    missing = [i for i in IDS if f'id="{i}"' not in src]
    assert missing == []


def test_같은_호스트의_ws_로_붙는다():
    assert '"/ws"' in _src() or "'/ws'" in _src()


def test_외부_리소스를_부르지_않는다():
    """시연장은 인터넷이 없다 — 외부 폰트·스크립트 하나가 페이지를 멈춘다.

    `src=`/`href=` 에 절대 URL 을 막는 것만으로는 부족하다. CSS `@import` 와
    `url(...)` 도 네트워크를 탄다 — 특히 `//host/...` 처럼 스킴을 생략한
    프로토콜 상대 경로는 `https?://` 정규식을 그냥 통과한다(현재 페이지가
    https 로 열리면 `//host` 는 `https://host` 로 풀린다). 이 검사가 보는
    스킴은 http/https 뿐이다 — 페이지 자신의 `ws://`/`wss://` 문자열(같은
    호스트로 붙는 WebSocket 접속)은 `src=`/`href=`/`url(` 어디에도 들어있지
    않으므로 걸리지 않는다.
    """
    src = _src()
    assert re.findall(r'(?:src|href)\s*=\s*["\']https?://', src) == []
    assert re.findall(r'(?:src|href)\s*=\s*["\']//', src) == []  # 프로토콜 상대 경로
    assert re.search(r'@import', src, re.IGNORECASE) is None
    assert re.search(r'url\(\s*["\']?(?:https?:)?//', src, re.IGNORECASE) is None
    assert "fonts.googleapis" not in src


def test_innerHTML_을_쓰지_않는다():
    """관람객 STT·경고 문자열이 그대로 온다 — textContent 로만 넣는다."""
    assert "innerHTML" not in _src()


def test_HTML_삽입_API_를_전부_막는다():
    """`innerHTML` 하나만 막으면 `outerHTML`·`insertAdjacentHTML`·
    `document.write` 로 같은 구멍(관람객 STT·경고 문자열을 HTML 로 해석시키는
    것)을 다시 낼 수 있다 — 위험 표면 전체를 한 자리에서 막는다."""
    src = _src()
    for token in ("outerHTML", "insertAdjacentHTML", "document.write"):
        assert token not in src, token


def test_콘솔과_같은_명령_문자열을_보낸다():
    src = _src()
    for c in ['"p"', '"r"', '"n"', '"s"', '"a"', '"g "']:
        assert c in src, c


def test_키_자동반복은_거른다():
    """N 을 길게 누르면 브라우저가 keydown 을 반복 발화한다 — 거르지 않으면 sendCmd
    가 여러 번 불려 섹션이 여러 개 건너뛴다(P1, 스펙 결정 2 "실수 한 번이 진행을
    깨지 않는다" 위반)."""
    assert "ev.repeat" in _src()


def test_키_매핑은_물리_코드를_쓴다():
    """`ev.key` 는 한글 입력기(IME)가 켜진 상태면 `ㄴ`·`ㅜ` 같은 자모가 되어 단축키가
    조용히 안 먹는다 — 입력기 상태와 무관한 `ev.code`(KeyN 등)로 매핑한다(P1).

    `ev.code` 라는 글자만 보면 설명 주석에도 나와 코드를 되돌려도 안 걸린다 —
    실제로 그 값을 찾아 쓰는 자리(`KEY_CMD[ev.code]`)를 리터럴로 본다."""
    src = _src()
    assert "KEY_CMD[ev.code]" in src
    assert '"KeyN"' in src


def _css_rule(src: str, selector: str) -> str:
    """`selector { … }` 규칙 본문. 주석 안의 같은 글자에 걸리지 않게 줄 머리의 선택자만 본다."""
    m = re.search(r"\n\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", src)
    assert m, selector
    return m.group(1)


def _media_block(src: str, needle: str) -> str:
    """`@media (...needle...) { ... }` 블록 전체 본문(중첩 규칙 포함).

    `_css_rule` 처럼 첫 `}` 에서 끊으면 media 블록 안의 개별 규칙(`.foo { … }`)의
    닫는 중괄호에서 잘려 블록 전체를 못 본다 — 중첩 깊이를 세어 짝이 맞는 곳까지 읽는다.
    """
    i = src.index(needle)
    start = src.index("{", i)
    depth = 0
    j = start
    while True:
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    return src[start + 1 : j]


def test_로그와_런다운은_창_높이에_맞춰_안쪽에서_스크롤한다():
    """body 가 `min-height: 100vh` 면 로그·런다운이 길어질수록 페이지가 늘어나 최신 로그가
    창 밖으로 밀려났다(사용자 요청: 이벤트 로그는 세로 스크롤, 브라우저 크기에 맞게).
    body 높이를 창에 고정하고, 두 목록은 `contain: size` 로 내용 길이를 패널 높이에서 떼어
    안쪽에서 스크롤한다 — 런다운 19행이 하단 줄 높이를 정하면 같은 줄의 로그도 그만큼 늘어난다."""
    src = _src()
    body = _css_rule(src, "body")
    assert "height: 100vh;" in body
    assert "min-height: 100vh" not in body
    for sel in (".log", ".rundown-list"):
        rule = _css_rule(src, sel)
        assert "overflow-y: auto" in rule, sel
        assert "contain: size" in rule, sel


def test_레벨_버튼_클릭은_콘솔과_같은_l_접두어_명령을_보낸다():
    """관람객 수준 버튼은 확인 단계 없이 바로 `l <이름>` 을 보낸다(계약:
    level-switch-contract.md — "l <수준이름>", 콘솔과 같은 명령 문자열). 이 리터럴이
    없으면 버튼이 서버가 모르는 명령을 보내거나 아예 아무것도 보내지 않는다."""
    assert 'sendCmd("l " + name)' in _src()


def test_hello의_levels_배열을_읽어_버튼을_짓는다():
    """수준 이름 4개(levels.yaml 순서)는 hello.levels 로 온다(계약). 이 필드를 실제로
    읽는 코드가 있어야 4버튼 세그먼트 컨트롤이 지어지고, 없으면(구버전 서버) 폴백
    분기(평문 표시)로 빠질 수 있다."""
    assert "msg.levels" in _src()


def test_snapshot의_level_pending을_읽어_대기_표시를_한다():
    """대기 중인 수준은 snapshot.level_pending 으로 온다(계약, 없으면 null). 이 필드를
    실제로 읽어야 테두리 강조와 "→ 이름 (다음 큐부터)" 문구가 나타나고, null 일 때
    감춘다."""
    assert "s.level_pending" in _src()


def test_레벨_버튼에는_키보드_단축키를_두지_않는다():
    """레벨 변경은 확인 단계 없이 즉시 나간다(계약) — 그런 조작에 실수로 눌리기 쉬운
    키보드 경로까지 얹으면 위험이 배가된다.

    **긍정 단언으로 본다** — `'"l"' not in ...` 같은 부정 단언만 두면(수준 리뷰 Minor 4,
    함정 ④) KEY_CMD 에 아무 키나(예: 수준 단축키를 다른 글자로 붙여도) 걸리지 않는다.
    지금 다섯 키(P/R/N/S/A)로 리터럴 통째 비교해, 키가 하나라도 더 붙으면(레벨이든
    다른 무엇이든) 실패한다."""
    src = _src()
    m = re.search(r"var KEY_CMD = \{([^}]*)\}", src)
    assert m
    key_cmd = json.loads("{" + m.group(1) + "}")
    assert key_cmd == {"KeyP": "p", "KeyR": "r", "KeyN": "n", "KeyS": "s", "KeyA": "a"}


def test_좁은_폭에서는_수준_캡션과_대기_문구를_숨기고_cue_label은_말줄임한다():
    """헤더 오른쪽 묶음(수준 버튼+대기 문구+연결 배지)이 약 500px 로 늘어나면, 줄어들지
    못하는 `.cue-label`(nowrap)이 "관람객 수준" 캡션 위에 겹쳤다(1024px 실측, 수준
    리뷰 Minor 2). `.cue-label` 이 줄어들 수 있어야 하고(min-width:0 + 말줄임), 좁은
    폭에서는 캡션·대기 문구를 접어 자리를 낸다 — 수준 버튼(조작)과 연결 배지(경고)는
    시연 중 언제나 보여야 하므로 이 media 블록 안에서 숨기지 않는다."""
    src = _src()
    label_rule = _css_rule(src, ".cue-label")
    assert "min-width: 0" in label_rule
    assert "overflow: hidden" in label_rule
    assert "text-overflow: ellipsis" in label_rule

    media = _media_block(src, "max-width: 1180px")
    assert ".level-caption" in media and "display: none" in media
    assert ".level-pending-text" in media
    # 버튼·연결 배지는 좁은 폭에서도 항상 보인다 — 이 media 블록에 그 선택자가
    # 등장하지 않는다는 것이 "숨기지 않는다" 는 뜻이다.
    assert ".level-btn" not in media
    assert "#conn" not in media and ".conn" not in media


def test_자막은_고정_높이에서_스크롤해_하단을_창_밖으로_밀지_않는다():
    """자막이 `min-height` 였을 때 도슨트 해설(최대 280자)이 6~7줄로 늘어나 칸이 커지고,
    런다운·제어·로그를 창 밖으로 밀어 페이지 스크롤이 생겼다(사용자 요청: 전체화면에서
    세로 스크롤 없이). 높이를 정하고 안쪽에서 스크롤한다."""
    rule = _css_rule(_src(), ".caption")
    assert "height: clamp(" in rule
    assert "overflow-y: auto" in rule
    assert "min-height" not in rule


def test_모드_토글이_있고_m_명령을_보낸다():
    """운영 모드(팟캐스트/단독) 토글 — 계약: hello.modes, snapshot.mode/solo_available,
    명령 "m <모드>". 요소 id 3개(컨테이너·안내문·단독 배너)가 있어야 하고, 명령 접두
    `"m "`(sendCmd("m " + name))·감독이 새로 보내는 두 필드를 실제로 읽는 코드가 있어야
    구버전 서버에서도 안 던지고, 단독을 지원하지 않는 로봇 앱에서 버튼이 잠긴다."""
    src = _src()
    for i in ("mode", "mode-note", "solo-banner"):
        assert f'id="{i}"' in src, i
    assert '"m "' in src          # sendCmd("m " + name)
    assert "solo_available" in src
    assert "msg.modes" in src


def test_단독에서는_키보드_단축키도_진행_명령을_보내지_않는다():
    """수준 리뷰 I1: disabled 속성은 버튼 클릭만 막을 뿐, 키보드 지름길(KEY_CMD)은
    그것과 무관하게 그대로 sendCmd 를 불러 applySoloLockdown 의 버튼 잠금을 우회했다
    (감독이 거절해 로그에 경고만 쌓이는, applySoloLockdown 자신의 주석이 막으려던
    바로 그 상황을 키보드로는 재현했다). p/r/n/s 는 단독에서 막되 즉시 중단(a)은
    살려 둔다 — 그래서 리터럴은 keydown 리스너 "본문 안"에서 확인한다(다른 자리에
    같은 문자열이 있어도 소용없다)."""
    src = _src()
    body = _media_block(src, 'addEventListener("keydown"')
    assert 'cmd !== "a"' in body
    assert 'latestSnapshot.mode === "solo"' in body


def test_단독_불가_안내는_사회자_없음과_앱_미지원을_가른다():
    """최종 리뷰 M4: `solo_available` 이 거짓인 이유는 둘이다(감독의 거절 경고도 둘) — 사회자
    로봇이 안 붙었거나, 붙었는데 그 앱이 단독을 모른다. 안내가 늘 "로봇 앱 업데이트 후" 면
    사회자가 끊긴 것을 앱 문제로 오인해 엉뚱한 곳을 본다. 가르는 기준은 snapshot.connected
    에 "mc" 가 있느냐다 — 리터럴은 renderModeState 본문 안에서 본다. 두 문구를 따로 찾으면
    갈래가 뒤바뀌어도(사회자가 있는데 "연결 후") 통과한다 — 삼항식을 통째로 본다."""
    body = _media_block(_src(), "function renderModeState(s)")
    assert 'var mcConnected = Array.isArray(s.connected) && s.connected.indexOf("mc") !== -1;' in body
    assert ('note.textContent = mcConnected ? "단독: 로봇 앱 업데이트 후" : "단독: 사회자 로봇 연결 후";'
            in body)


def test_단독으로_들어가면_열려_있던_이동_확인_바를_닫는다():
    """수준 리뷰 I2: 런다운 행을 눌러 이동 확인 바가 열린 채 단독으로 전환되면,
    확인·취소 버튼과 런다운 행이 함께 잠겨 운영자가 그 바를 닫을 방법이 없는 막다른
    골목이 됐다. applySoloLockdown 이 단독으로 들어갈 때 스스로 바를 닫아야 한다 —
    리터럴은 그 함수 본문 안에서 확인한다."""
    src = _src()
    body = _media_block(src, "function applySoloLockdown(isSolo)")
    assert "closeGotoBar()" in body


def test_대사_자막에_감정_배지를_그린다():
    """대사마다 감정 태그가 생겼다(계획 §12) — 감독이 `say` 에 `emotion` 을 실어 보내고
    그 송신 기록이 `sent` 이벤트로 그대로 온다. 운영자가 지금 대사가 어떤 감정으로
    나가는지 한눈에 보려면 자막 칸에 배지가 붙어야 한다.

    리터럴은 **자막을 그리는 함수 본문 안**에서 본다 — 파일 어딘가에 `fields.emotion`
    이라는 글자만 있으면 통과하는 검사는 배지가 실제로 그려지는지 아무것도 안 지킨다.
    배지 모양은 헤더의 수준·모드 배지와 같은 값이어야 한다(한 화면에 배지 방언을 둘로
    만들지 않는다)."""
    src = _src()
    sent = _media_block(src, "function renderSent(msg)")
    assert "fields.emotion" in sent

    cap = _media_block(src, "function setCaption(cap, text, emotion)")
    assert 'badge.className = "emotion-badge"' in cap
    # 감독이 준 문자열이다 — 배지도 자막 본문과 같이 textContent 로만 넣는다.
    assert "badge.textContent = name" in cap

    rule = _css_rule(src, ".emotion-badge")
    assert "font-size: 11px" in rule        # .level-btn/.mode-btn 과 같은 크기
    assert "border-radius: 999px" in rule   # 같은 알약 모양


def test_감정이_없거나_설명이면_배지를_그리지_않는다():
    """`설명` 은 "특별한 감정 없음"(`stage/cues.py::DEFAULT_EMOTION`)이라 거의 모든 줄에
    붙는다 — 그리면 배지가 늘 켜져 있는 장식이 되어 진짜 감정(놀람·아쉬움)이 눈에 안
    띈다. 필드가 아예 없는 경우(감정을 모르는 옛 감독, 관람객 질문 답)도 같다.

    문자열이 아닌 값(`null`·숫자)이 와도 그냥 안 그린다 — 자막은 시연 내내 도는 경로라
    여기서 던지면 그 뒤 대사가 화면에서 통째로 멈춘다."""
    body = _media_block(_src(), "function shownEmotion(value)")
    assert 'typeof value !== "string"' in body
    assert '"설명"' in body
    assert 'return ""' in body


def test_다음_대사에_감정이_없으면_앞_배지가_남지_않는다():
    """자막 칸은 대사마다 덮어쓴다 — 배지 엘리먼트를 남겨 둔 채 텍스트만 갈아 끼우면
    감정이 없는 다음 대사에 앞 대사의 배지가 그대로 붙어 있고, 운영자는 그것을 지금
    감정으로 읽는다. 그릴 때마다 칸을 비우고 다시 짓는다."""
    body = _media_block(_src(), "function setCaption(cap, text, emotion)")
    assert "removeChild" in body


def test_로그의_say_줄에도_감정이_남는다():
    """자막은 다음 대사가 곧 덮어쓴다 — 시연이 끝난 뒤 "이 대사에 왜 저 모션이 났나" 를
    되짚을 수 있는 기록은 이벤트 로그뿐이다. 배지와 **같은 규칙**(없거나 `설명` 이면 안
    적는다)이어야 하므로 같은 함수(`shownEmotion`)를 쓴다 — 규칙을 두 벌로 적으면 한쪽만
    고쳐져 화면과 로그가 엇갈린다."""
    body = _media_block(_src(), "function describeEvent(msg)")
    assert "shownEmotion(fields.emotion)" in body


def _px(rule: str, prop: str) -> int:
    m = re.search(prop + r"\s*:\s*(\d+)px", rule)
    assert m, (prop, rule)
    return int(m.group(1))


def test_왼쪽_열과_카메라_두_대는_1024px_폭에서_한_줄에_들어간다():
    """태블릿 가로(1024px)에서 왼쪽 열(런다운+제어)과 카메라 두 대가 옆으로 나란히
    남아야 한다 — 안 그러면 줄바꿈이 나 카메라가 창 높이 맞춤에 눌려 찌그러진다.
    왼쪽 열 고정 폭 + 두 열 사이 간격 + 카메라 두 대의 최소 폭 + 카메라 사이 간격 +
    페이지 좌우 여백(×2)이 1024 이하여야 한다."""
    src = _src()
    grid = _css_rule(src, ".stage-grid")
    grid_gap = _px(grid, "gap")
    pad = re.search(r"padding\s*:\s*\d+px\s+(\d+)px", grid)
    assert pad, grid
    side = int(pad.group(1))

    left_col = _css_rule(src, ".left-col")
    m = re.search(r"flex\s*:\s*\d+\s+\d+\s+(\d+)px", left_col)
    assert m, left_col
    left_width = int(m.group(1))

    monitors = _css_rule(src, ".monitors")
    cam_gap = _px(monitors, "gap")

    monitor_col = _css_rule(src, ".monitor-col")
    cam_min = _px(monitor_col, "min-width")

    total = left_width + grid_gap + 2 * cam_min + cam_gap + 2 * side
    assert total <= 1024, (left_width, grid_gap, cam_min, cam_gap, side, total)


def test_더_좁아서_줄바꿈되면_패널이_납작해지지_않는다():
    """900px 보다 좁으면 왼쪽 열과 오른쪽 열이 한 줄에 안 들어간다 — 그때 옆으로
    우겨넣지 않고 세로로 쌓는다(`.stage-grid` 를 column 으로). 쌓인 패널이 창 높이
    맞춤에 눌려 찌그러지지 않게 최소 높이를 주고 페이지 스크롤로 넘긴다."""
    src = _src()
    blocks = re.findall(r"@media\s*\(max-width:\s*(\d+)px\)\s*\{(.*?)\n  \}", src, re.S)
    narrow = [body for w, body in blocks if int(w) < 1000 and ".panel" in body]
    assert narrow, blocks
    assert re.search(r"\.stage-grid\s*\{[^}]*flex-direction:\s*column", narrow[0]), narrow[0]
    assert re.search(r"\.panel\s*\{[^}]*min-height:\s*2\d\dpx", narrow[0]), narrow[0]


def test_카메라_video_요소가_있다():
    src = _src()
    assert 'id="vid-mc"' in src and "<video" in src
    assert 'id="vid-docent"' in src


def test_카메라_켜기_끄기_버튼이_c_명령을_보낸다():
    src = _src()
    assert re.search(r'sendCmd\(\s*"c\s*"\s*\+\s*"mc"', src) or "sendCmd(\"c \" + role" in src


def test_대기모드_버튼이_z_명령을_보낸다():
    src = _src()
    assert "sendCmd(\"z \" + role" in src or re.search(r'sendCmd\(\s*"z\s*"', src)


def test_rtc_메시지_kind를_처리한다():
    src = _src()
    assert '"rtc"' in src and "RTCPeerConnection" in src


def test_스냅샷의_cameras_사유를_칸에_표시한다():
    src = _src()
    assert "s.cameras" in src or "snap.cameras" in src


def test_카메라_라벨과_탤리는_영상_위에_쌓인다():
    """`.cam-video` 는 `position: absolute; inset: 0` 로 CAM 칸 전체를 덮고, DOM 순서상
    `.cam-label`/`.tally` **뒤**에 온다. 절대위치 형제는 z-index 가 같으면(둘 다 auto)
    DOM 순서로 겹쳐 나중에 오는 쪽(영상)이 위로 온다 — 영상이 뜨는 순간(`video.hidden =
    false`) 운영자가 한눈에 보는 카메라 라벨과 방송 탤리(OFFLINE/ON AIR)가 가려진다(리뷰
    Important). `.cam-controls` 가 이미 쓰는 `z-index: 1` 과 같은 값으로 라벨·탤리를
    그 위에 고정한다 — `.cam-video` 자체는 명시 z-index 가 없으면 auto 라 1보다 낮게 쌓여
    손대지 않아도 된다."""
    src = _src()
    label_rule = _css_rule(src, ".cam-label")
    assert re.search(r"z-index\s*:\s*[1-9]\d*", label_rule), label_rule
    tally_rule = _css_rule(src, ".tally")
    assert re.search(r"z-index\s*:\s*[1-9]\d*", tally_rule), tally_rule
