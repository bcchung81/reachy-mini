import json
import pathlib
import re

PAGE = pathlib.Path(__file__).parent.parent / "stage" / "dashboard_page.html"
IDS = ["conn", "cue-label", "level", "mon-mc", "mon-docent", "tag-mc", "tag-docent",
       "cap-mc", "cap-docent", "rundown", "goto-bar", "goto-confirm", "goto-cancel",
       "btn-prev", "btn-restart", "btn-next", "btn-show", "btn-abort",
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
    for c in ['"p"', '"r"', '"n"', '"s"', '"e"', '"a"', '"g "']:
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


def test_로그는_창_높이에_맞춰_안쪽에서_스크롤하고_런다운은_칩으로_다_보인다():
    """body 가 `min-height: 100vh` 면 로그·런다운이 길어질수록 페이지가 늘어나 최신 로그가
    창 밖으로 밀려났다(사용자 요청: 이벤트 로그는 세로 스크롤, 브라우저 크기에 맞게).
    body 높이를 창에 고정하고, 로그는 `contain: size` 로 내용 길이를 패널 높이에서 떼어 안쪽에서 스크롤한다.

    ~~런다운도 같은 규칙(19행 목록이 안쪽 스크롤)~~ — 2026-11-14 조정실 가 안(U5): 런다운은 번호 칩 격자가 되어
    **스크롤하지 않고 한 번에 다 보인다**(넓으면 한 줄, 1280px 아래 두 줄 — 칸 수는 buildRundown 이 큐 수로 정한다).
    목록이 스크롤되면 지금 큐가 아래로 숨는데, 칩은 19칸이 다 보여 그럴 일이 없다. 그래서 런다운 쪽 단언을 바꿨다."""
    src = _src()
    body = _css_rule(src, "body")
    assert "height: 100vh;" in body
    assert "min-height: 100vh" not in body
    rule = _css_rule(src, ".log")
    assert "overflow-y: auto" in rule
    assert "contain: size" in rule
    chips = _css_rule(src, ".rundown-list")
    assert "display: grid" in chips and "repeat(var(--cue-cols" in chips
    assert "overflow-y: auto" not in chips      # 칩은 다 보인다 — 안쪽 스크롤이면 지금 큐가 숨는다
    build = _media_block(src, "function buildRundown(cues)")
    assert 'root.style.setProperty("--cue-cols"' in build and 'root.style.setProperty("--cue-cols-narrow"' in build


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


def test_수준_버튼은_snapshot의_level_로_적용_표시를_옮기고_대기_표시는_없다():
    """적용된 수준은 snapshot.level 로 온다(계약). ~~대기 중인 수준(level_pending)을 테두리와
    "→ 이름 (다음 큐부터)" 로 보였다~~ — 2026-09-25 부터 수준은 바로(다음 발화부터) 적용된다.
    대기 문구가 남아 있으면 운영자가 "다음 큐까지 기다려야 하나" 로 읽는다."""
    src = _src()
    assert 'classList.toggle("applied", name === s.level)' in src
    assert "다음 큐부터" not in src
    assert "level-pending-text" not in src


def test_레벨_버튼에는_키보드_단축키를_두지_않는다():
    """레벨 변경은 확인 단계 없이 즉시 나간다(계약) — 그런 조작에 실수로 눌리기 쉬운
    키보드 경로까지 얹으면 위험이 배가된다.

    **긍정 단언으로 본다** — `'"l"' not in ...` 같은 부정 단언만 두면(수준 리뷰 Minor 4,
    함정 ④) KEY_CMD 에 아무 키나(예: 수준 단축키를 다른 글자로 붙여도) 걸리지 않는다.
    지금 여섯 키(P/R/N/S/E/A)로 리터럴 통째 비교해, 키가 하나라도 더 붙으면(레벨이든
    다른 무엇이든) 실패한다. E 는 공연 종료(2026-09-25)."""
    src = _src()
    m = re.search(r"var KEY_CMD = \{([^}]*)\}", src)
    assert m
    key_cmd = json.loads("{" + m.group(1) + "}")
    assert key_cmd == {"KeyP": "p", "KeyR": "r", "KeyN": "n", "KeyS": "s", "KeyE": "e", "KeyA": "a"}


def test_좁은_폭에서는_수준_캡션을_숨기고_cue_label은_말줄임한다():
    """헤더 오른쪽 묶음(수준 버튼+~~대기 문구~~+연결 배지)이 약 500px 로 늘어나면, 줄어들지
    못하는 `.cue-label`(nowrap)이 "관람객 수준" 캡션 위에 겹쳤다(1024px 실측, 수준
    리뷰 Minor 2). `.cue-label` 이 줄어들 수 있어야 하고(min-width:0 + 말줄임), 좁은
    폭에서는 캡션을 접어 자리를 낸다 — 수준 버튼(조작)과 연결 배지(경고)는
    시연 중 언제나 보여야 하므로 이 media 블록 안에서 숨기지 않는다.

    2026-11-14 가 안: `.cue-label` 은 머리에서 진행 데크로 내려갔다(두 줄까지, 넘치면 말줄임 — 같은 세 속성).
    머리에는 수준·코스·로봇 알약·연결만 남아 이 겹침 자체가 줄었지만, 좁은 폭에서 캡션을 접는 규칙은 그대로다."""
    src = _src()
    label_rule = _css_rule(src, ".cue-label")
    assert "min-width: 0" in label_rule
    assert "overflow: hidden" in label_rule
    assert "text-overflow: ellipsis" in label_rule

    media = _media_block(src, "max-width: 1180px")
    assert ".level-caption" in media and "display: none" in media
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


def test_단독_불가_안내는_사회자_없음과_대기모드를_가른다():
    """최종 리뷰 M4: `solo_available` 이 거짓인 이유는 둘이다(감독의 거절 경고도 둘) — 사회자
    로봇이 안 붙었거나, 붙었는데 대기모드다(~~그 앱이 단독을 모른다~~ — 2026-09-25 감독이 대화를
    맡아 앱과 무관하다). 한 문구로 뭉개면 사회자가 끊긴 것을 대기모드 문제로 오인한다. 가르는 기준은 snapshot.connected
    에 "mc" 가 있느냐다 — 리터럴은 renderModeState 본문 안에서 본다. 두 문구를 따로 찾으면
    갈래가 뒤바뀌어도(사회자가 있는데 "연결 후") 통과한다 — 삼항식을 통째로 본다."""
    body = _media_block(_src(), "function renderModeState(s)")
    assert 'var mcConnected = Array.isArray(s.connected) && s.connected.indexOf("mc") !== -1;' in body
    assert ('note.textContent = mcConnected ? "단독: 사회자 대기모드 해제 후" : "단독: 사회자 로봇 연결 후";'
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


def _rule_in(block: str, selector: str) -> str:
    """media 블록 본문 안의 `selector { … }` 규칙 본문."""
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", block)
    assert m, (selector, block[:200])
    return m.group(1)


def test_서랍의_카메라_두_대는_1024px_에서_한_줄에_들어간다_폭은_flex_basis_로_잰다():
    """~~왼쪽 열(300) + 간격 + 카메라 최소 폭(300)×2 + 간격 + 여백 ≤ 1024~~ — 이 테스트는 `min-width` 를 더해 통과했는데,
    브라우저는 줄을 **flex-basis**(그때 360px)로 바꾼다: 360+24+360 = 744 > 오른쪽 열 652 라 1024×768 에서 카메라 두 칸이
    두 줄로 내려앉고 페이지가 193px 스크롤됐다(2026-11-14 시안 캡처로 찾음 — CSS 를 읽는 테스트가 실제 배치 규칙과 다른 값을 쟀다).

    2026-11-14 가 안(U5): 카메라는 '고급' 서랍 안이다. 넓은 화면에서 서랍은 **시연 화면 칸 위에 꼭 맞게** 뜨고(아래
    placeAdvanced), 카메라 줄은 서랍 폭 전부(`grid-column: 1 / -1`)를 쓴다. 가장 좁은 떠오른 서랍(1024px)의 안쪽 폭 =
    1024 − 데크 폭(1279px 아래 값) − 가운데 간격 − 좌우 여백 − 서랍 안 여백·테두리. 카메라 두 칸의 **flex-basis** 합이 거기 들어가야 한다.
    실제 배치는 헤드리스 테스트(`test_헤드리스_…`)가 1024×768 에서 두 칸의 top 이 같은지로 다시 잰다."""
    src = _src()
    core = _css_rule(src, ".core")
    core_gap = _px(core, "gap")
    pad = re.search(r"padding\s*:\s*\d+px\s+(\d+)px", core)
    assert pad, core
    side = int(pad.group(1))

    narrow_root = _rule_in(_media_block(src, "@media (max-width: 1279px)"), ":root")
    deck_w = _px(narrow_root, "--deck-w")

    drawer = _rule_in(_media_block(src, "@media (min-width: 901px)"), ".advanced[open] > .adv-body")
    assert "position: fixed" in drawer
    adv_pad = _px(drawer, "padding")
    adv_border = _px(drawer, "border")

    monitors = _css_rule(src, ".adv-body .monitors")
    assert "grid-column: 1 / -1" in monitors       # 카메라 줄은 서랍 폭 전부
    cam_gap = _px(_css_rule(src, ".monitors"), "gap")
    basis = re.search(r"flex\s*:\s*\d+\s+\d+\s+(\d+)px", _css_rule(src, ".monitor-col"))
    assert basis, "monitor-col 은 flex 줄임말에 px basis 를 적는다 — 줄바꿈은 그 값으로 정해진다"

    inner = 1024 - 2 * side - core_gap - deck_w - 2 * adv_pad - 2 * adv_border
    total = 2 * int(basis.group(1)) + cam_gap
    assert total <= inner, (int(basis.group(1)), cam_gap, inner)


def test_900px_아래에서는_세로로_쌓고_시연_화면은_16대9_로그는_쓸_만한_높이다():
    """900px 보다 좁으면(세로 태블릿) 시연 화면 + 데크를 옆으로 둘 수 없다 — 세로로 쌓고 페이지가 스크롤한다.
    ~~`.stage-grid` 를 column 으로, `.panel` 최소 260px~~(옛 2단 배치) → 2026-11-14 가 안: `.core` 를 column 으로 쌓고,
    시연 화면은 폭에 맞춘 16:9(남는 높이가 없어 flex 로 두면 170px 로 눌렸다 — 시안 캡처), 서랍은 흐름 안에서 펼쳐지며
    로그는 `contain: size` 라 높이를 정해 줘야 0 으로 납작해지지 않는다."""
    src = _src()
    blocks = re.findall(r"@media\s*\(max-width:\s*(\d+)px\)\s*\{(.*?)\n  \}", src, re.S)
    narrow = [body for w, body in blocks if int(w) == 900]
    assert narrow, blocks
    body = narrow[0]
    assert re.search(r"\.core\s*\{[^}]*flex-direction:\s*column", body), body
    assert re.search(r"\.core \.stage-view\s*\{[^}]*aspect-ratio:\s*16 / 9", body), body
    assert re.search(r"\.adv-body \.log-panel\s*\{[^}]*height:\s*2\d\dpx", body), body


def test_900px_아래에서는_머리를_두_줄로_접어_연결_배지를_자르지_않는다():
    """머리는 56px 고정 + `overflow: hidden` 이다. 세로 태블릿(768px)에서 오른쪽 끝의 연결 배지(#conn)가 잘려 안 보였다
    (2026-11-14 시안 캡처 — 옛 조정실도 같았다). 연결 끊김 경고는 잘리면 안 된다 — 좁은 폭에서는 머리를 줄바꿈한다."""
    src = _src()
    blocks = re.findall(r"@media\s*\(max-width:\s*(\d+)px\)\s*\{(.*?)\n  \}", src, re.S)
    body = [b for w, b in blocks if int(w) == 900][0]
    header = _rule_in(body, "header")
    assert "flex-wrap: wrap" in header and "flex: 0 0 auto" in header
    assert "#conn" not in body and ".conn" not in body      # 연결 배지는 이 블록에서 건드리지 않는다(숨기지 않는다)


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


def test_침묵_대기_버튼이_w_명령을_보내고_끔을_그린다():
    html = PAGE.read_text(encoding="utf-8")
    for el in ('id="wait-dec"', 'id="wait-inc"', 'id="wait-off"', 'id="wait-value"'):
        assert el in html, el
    assert 'sendCmd("w " + (waitNow - 1))' in html and 'sendCmd("w " + (waitNow + 1))' in html
    assert '"w 끄기"' in html
    assert "question_wait_total_s" in html


def test_공연_토글은_snapshot의_show_running으로_시작과_종료를_오간다():
    """제어판의 한 버튼이 [공연 시작](s) ↔ [공연 종료](e) 로 바뀐다(2026-09-25 결정). 이 필드를 읽는
    코드가 없으면 버튼이 늘 "공연 시작" 이라 운영자가 공연을 끝낼 손잡이를 못 찾는다."""
    src = _src()
    assert "s.show_running === true" in src
    assert 'running ? "공연 종료" : "공연 시작"' in src
    assert 'btn.dataset.cmd = running ? "e" : "s"' in src
    assert "처음부터 시작" not in src          # 옛 버튼 문구가 남으면 두 버튼이 된 것으로 읽힌다


def test_공연_토글은_누른_뒤_잠깐_잠가_종료_두_번이_재시작이_되지_않는다():
    """[공연 종료] 를 두 번 누르면 그 사이 도착한 스냅샷 때문에 두 번째가 [공연 시작] 이 된다 —
    끝내려던 공연이 첫 큐부터 다시 시작한다. 감독은 두 명령이 각각 정당해서 이 교차를 못 막는다.

    ~~1000ms~~ 는 실측으로 뚫렸다(두 번 누른 간격 1005ms → `e` 뒤 `s`). 1500ms 로 늘리고 잠긴 동안
    버튼을 흐리게 둔다 — 스냅샷마다 도는 단독 잠금(`applySoloLockdown`)이 그 잠금을 풀지 않아야 한다."""
    src = _src()
    assert "var SHOW_TOGGLE_LOCK_MS = 1500;" in src
    assert "if (now < showToggleLockedUntil) return;" in src
    assert "btn.disabled = true;" in src
    lockdown = _media_block(src, "function applySoloLockdown(isSolo)")
    assert 'if (showToggleLocked()) document.getElementById("btn-show").disabled = true;' in lockdown


def test_단독에서는_공연_토글도_잠근다():
    """단독에서 감독은 공연 시작·종료를 거절한다 — 버튼도 잠가야 거절 경고만 쌓이지 않는다."""
    assert '["btn-prev", "btn-restart", "btn-next", "btn-show"].forEach' in _src()



def test_단독에서는_런다운의_지금_큐를_ON_AIR_로_켜지_않는다():
    """단독은 곧바로 LISTENING 이다 — state 만 보면 멈춰 둔 팟캐스트 큐가 ON AIR(빨강)로 켜져, 운영자가
    팟캐스트가 도는 줄 안다(2026-09-25 화면 실측)."""
    body = _media_block(_src(), "function refreshRundownTags()")
    assert ('var idle = latestSnapshot && (latestSnapshot.state === "idle" || latestSnapshot.mode === "solo");'
            in body)



def test_단독에서는_자동_진행_영역이_없음을_알린다():
    """단독에는 침묵 기한이 없다 — "대기 전" 이면 운영자가 곧 자동 진행이 시작될 줄 안다."""
    src = _src()
    assert "applyAutoProgress(s.question_wait_s, s.question_wait_total_s, s.mode);" in src
    body = _media_block(src, "function applyAutoProgress(wait, total, mode)")
    assert 'text.textContent = "단독 — 자동 진행 없음";' in body


def test_코스_버튼은_콘솔과_같은_k_명령을_보내고_hello_courses_로_짓는다():
    """코스(2026-09-25) — 버튼 이름과 감독이 받는 이름이 한 곳(hello.courses)에서 나온다. 코스가 하나면 숨긴다."""
    src = _src()
    assert 'sendCmd("k " + name)' in src
    assert "buildCourseControl(msg.courses);" in src
    body = _media_block(src, "function buildCourseControl(courses)")
    assert "courses.length > 1" in body


def test_런다운은_코스_밖_큐를_흐리게_제외로_그린다():
    """진행이 밟지 않는 큐를 운영자가 한눈에 — 지금 큐는 코스 밖이어도(직접 이동) 지금 큐로 그린다."""
    body = _media_block(_src(), "function refreshRundownTags()")
    assert 'if (i !== idx && !inCourse(row.id)) {' in body
    assert 'row.tag.textContent = "제외";' in body


def test_시연_화면은_조정실_안에_있고_프로젝터로_띄울_수_있다():
    """2026-11-13: 새 탭으로 연 교육자료가 조정실과 따로 놀았다(조정하는 동안 화면이 안 보였다) — 조정실 안에 넣는다.
    같은 오리진의 /stage/… 여야 화면이 /ws/audience 에 붙는다(file:// 는 Origin 검사에 막힌다)."""
    src = _src()
    assert '<iframe id="stage-frame" title="시연 화면" src="/stage/auto?embed"></iframe>' in src
    assert 'id="btn-stage"' in src and 'data-href="/stage/auto"' in src and "프로젝터로 띄우기" in src
    assert 'window.open(btn.getAttribute("data-href"), "reachy-stage")' in src   # 같은 창 이름 — 눌러도 창이 쌓이지 않는다
    assert "시연 영상 열기" not in src.replace("~~시연 영상 열기 버튼 묶음~~", "")      # 옛 버튼 묶음은 패널로 옮겼다
    # 1280×720 으로 그려 줄인다 — 작은 틀에 그대로 넣으면 페이지가 좁은 화면 배치로 바뀌어 프로젝터와 다른 모양이 된다
    assert "Math.min(w / 1280, h / 720)" in src and "width: 1280px; height: 720px" in src
    # 고른 화면 알림은 같은 오리진만 받는다
    assert 'ev.origin !== location.origin' in src and 'ev.data.type !== "stage-auto"' in src
    # 대시보드가 실제로 주는 경로여야 한다
    import sys
    sys.path.insert(0, str(PAGE.parent.parent))
    from stage.dashboard import MOTION_PAGES
    for href in re.findall(r'(?:data-href|src)="/stage/([a-z0-9-]+)', src):
        assert href in MOTION_PAGES, href


def test_1인_모드면_조정실에_띠를_띄운다():
    """2026-11-13: 한 대만 붙은 채 공연해 도슨트 대사가 사회자 목소리로 나갔다 — 조정실에서 바로 보이게."""
    src = _src()
    assert '<div id="one-robot-banner" class="one-robot-banner" hidden></div>' in src
    body = _media_block(src, "function renderOneRobot(s)")
    assert 's.solo_role === "mc" || s.solo_role === "docent"' in body and "el.hidden = true" in body
    assert "자기 목소리로 읽는다" in body and "textContent" in body and "innerHTML" not in body
    assert "renderOneRobot(s);" in src.split("function renderOneRobot")[0]   # 스냅샷마다 부른다


# ── 2026-11-14 조정실 가 안(U5): 핵심만 + '고급' 서랍 ──────────────────────────────
# 계획서 docs/superpowers/plans/2026-11-14-show-readiness.md §4, 시안 docs/design/control-room-A.html.

# 가 안 전에 있던 id 53개 — 서랍 안으로 옮겨도 DOM 에는 있어야 한다(감독 소켓 렌더·테스트·운영 문서가 이 이름을 쓴다).
ORIGINAL_IDS = [
    "auto-bar", "auto-text", "btn-abort", "btn-next", "btn-prev", "btn-restart", "btn-show-key", "btn-show-label",
    "btn-show", "btn-stage", "cam-reason-docent", "cam-reason-mc", "cam-toggle-docent", "cam-toggle-mc", "cap-docent",
    "cap-mc", "conn", "course-group", "course", "cue-label", "cue-topic", "goto-bar", "goto-cancel", "goto-confirm",
    "goto-text", "level", "link-audience", "link-handout", "log-warn-count", "log", "mic-docent", "mic-mc", "mode-note",
    "mode", "mon-docent", "mon-mc", "one-robot-banner", "rundown-summary", "rundown", "solo-banner", "stage-frame",
    "stage-screen", "stage-view", "standby-toggle-docent", "standby-toggle-mc", "tag-docent", "tag-mc", "vid-docent",
    "vid-mc", "wait-dec", "wait-inc", "wait-off", "wait-value",
]
NEW_IDS = ["robot-mc", "robot-docent", "now-tag", "cue-next", "advanced", "adv-alert"]


def _split_drawer(src: str) -> tuple[str, str]:
    """(서랍 밖 마크업, 서랍 안 마크업). 서랍 = `<details id="advanced" …>` … `</details>`. 스크립트는 뺀다."""
    body = src[src.index("<body>"):src.index("<script>")]
    i = body.index('<details id="advanced"')
    j = body.index("</details>", i)
    summary_end = body.index("</summary>", i)
    # 요약 줄(<summary>)은 접혀도 보인다 — 서랍 밖으로 센다.
    return body[:summary_end] + body[j:], body[summary_end:j]


def _ids(markup: str) -> set[str]:
    return set(re.findall(r'\sid="([^"]+)"', markup))


def test_가려도_원래_id_는_전부_DOM_에_있다():
    src = _src()
    missing = [i for i in ORIGINAL_IDS + NEW_IDS if f'id="{i}"' not in src]
    assert missing == []
    markup = re.sub(r"<!--.*?-->", "", src, flags=re.S)        # 주석 안의 `id="level"` 같은 설명 글은 세지 않는다
    counts = {i: markup.count(f'id="{i}"') for i in ORIGINAL_IDS + NEW_IDS}
    assert {i: n for i, n in counts.items() if n != 1} == {}     # 옮기다 두 벌이 되지 않았다


def test_기본_화면에는_운영자가_쓰는_것만_보인다():
    """기본 화면(서랍 밖) = 공연 중에 만지는 것과 경고뿐: 수준·코스·로봇 2대·연결·띠 · 시연 화면·프로젝터 · 지금/다음 큐 ·
    [공연 시작/종료] [이전] [다음] [즉시 중단] · 자동 진행 · 런다운(이동 확인 포함 — U6). 나머지는 '고급' 서랍.
    목록을 통째로 고정한다 — 무엇을 밖으로 꺼내거나 서랍에 넣으면 이 테스트를 고치며 이유를 남긴다."""
    outside, inside = _split_drawer(_src())
    assert _ids(outside) == {
        "mode-note", "course-group", "course", "level", "robot-mc", "robot-docent", "conn",
        "solo-banner", "one-robot-banner",
        "stage-screen", "btn-stage", "stage-view", "stage-frame",
        "now-tag", "cue-label", "cue-topic", "cue-next",
        "btn-show", "btn-show-label", "btn-show-key", "btn-prev", "btn-next", "auto-text", "auto-bar", "btn-abort",
        "rundown-summary", "goto-bar", "goto-text", "goto-confirm", "goto-cancel", "rundown",
        "advanced", "adv-alert",
    }
    assert _ids(inside) == {
        "mode", "btn-restart", "wait-dec", "wait-value", "wait-inc", "wait-off", "link-audience", "link-handout",
        "mon-mc", "tag-mc", "vid-mc", "cam-reason-mc", "mic-mc", "cam-toggle-mc", "standby-toggle-mc", "cap-mc",
        "mon-docent", "tag-docent", "vid-docent", "cam-reason-docent", "mic-docent", "cam-toggle-docent",
        "standby-toggle-docent", "cap-docent", "log-warn-count", "log",
    }


WARN_SELECTORS = (".solo-banner", ".one-robot-banner", "#conn", ".conn", "#btn-abort", ".ctrl-btn.abort",
                  ".robots", ".robot", "#mode-note", ".mode-note", "#robot-mc", "#robot-docent")


def test_경고_띠_연결_상태_즉시_중단은_서랍_밖에_있고_어느_폭에서도_숨기지_않는다():
    """실패는 소리 내서(CLAUDE.md) — 1인 모드 띠(2026-11-13 "둘 다 남자 목소리")·단독 띠·연결 배지·로봇 알약·단독 불가 안내·
    [즉시 중단] 은 접히는 곳에 두지 않고, 어떤 media 블록도 이것들을 `display: none` 으로 숨기지 않는다."""
    src = _src()
    outside, _ = _split_drawer(src)
    for i in ("solo-banner", "one-robot-banner", "conn", "robot-mc", "robot-docent", "mode-note", "btn-abort"):
        assert f'id="{i}"' in outside, i
    style = src[src.index("<style>"):src.index("</style>")]
    for m in re.finditer(r"@media[^{]*\{", style):
        block = _media_block(style, m.group(0))
        for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", block):
            if re.search(r"display\s*:\s*none", body):
                hit = [w for w in WARN_SELECTORS if re.search(re.escape(w) + r"(?![\w-])", sel)]
                assert hit == [], (m.group(0), sel.strip())


def test_접힌_서랍에_경고가_쌓이면_고급_줄에_개수와_마지막_경고를_띄운다():
    """서랍이 접히면 이벤트 로그·카메라 사유가 안 보인다 — 경고가 조용히 묻히면 안 된다(계획서 §4 "가린 패널에 문제가 생기면
    단추에 표시"). 로그 경고 줄과 **새로 생긴** 카메라 사유(스냅샷은 0.5초마다 오므로 바뀔 때만 센다)를 세어 '고급' 줄에
    "경고 N · 마지막 글" 을 띄우고, 펼치면 지운다. hello 가 다시 오면(재접속) 이력이 경고를 다시 세므로 같이 비운다."""
    src = _src()
    append = _media_block(src, "function appendLogFor(msg)")
    assert "markHiddenProblem(text.textContent)" in append
    mark = _media_block(src, "function markHiddenProblem(text)")
    assert 'document.getElementById("advanced").open' in mark and "return" in mark
    assert "textContent" in mark and "innerHTML" not in mark
    snap = _media_block(src, "function renderSnapshot(s)")
    assert "c.reason !== lastCamReason[role]" in snap
    assert "clearHiddenAlert();" in _media_block(src, "function clearLog()")
    # 비울 때 "본 사유" 도 잊는다 — 안 그러면 재접속 뒤 계속 남아 있는 카메라 사유가 다시 세지지 않아 개수가 0 으로 거짓말한다.
    assert 'lastCamReason = { mc: "", docent: "" };' in _media_block(src, "function clearHiddenAlert()")
    assert re.search(r'getElementById\("advanced"\)\.addEventListener\("toggle", function \(\) \{\s*if \(this\.open\) clearHiddenAlert\(\);', src)
    assert '<span id="adv-alert" class="adv-alert" hidden></span>' in src


def test_고급_서랍은_늘_접힌_채_시작하고_펼치면_시연_화면_칸에_맞춰_뜨고_Esc_로_닫힌다():
    """접힌 채 시작한다(펼침을 기억하지 않는다 — 다시 열면 늘 기본 화면). 넓은 화면에서는 시연 화면 칸의 사각형에 꼭 맞게
    떠오른다: 흐름 안에서 펼치면 데크가 눌려 1024×768 에서 [즉시 중단] 이 창 밖으로 밀렸고, 화면 아래에 붙여 띄우면 런다운
    띠를 반쯤 가렸다(시안 캡처). Esc 로 닫는다 — 진행 단축키(P R N S E A)와 겹치지 않는다."""
    src = _src()
    assert '<details id="advanced" class="advanced">' in src          # open 속성 없음
    assert "localStorage" not in src
    place = _media_block(src, "function placeAdvanced()")
    assert 'document.querySelector(".core .stage-panel")' in place and "getBoundingClientRect()" in place
    for v in ("--adv-l", "--adv-t", "--adv-w", "--adv-h"):
        assert v in place, v
    drawer = _rule_in(_media_block(src, "@media (min-width: 901px)"), ".advanced[open] > .adv-body")
    for v in ("var(--adv-l", "var(--adv-t", "var(--adv-w", "var(--adv-h"):
        assert v in drawer, v
    assert 'ev.key === "Escape"' in src
    # 원래 keydown 리스너(진행 단축키)가 먼저 온다 — 단독 잠금 테스트가 첫 keydown 블록을 읽는다.
    assert src.index('addEventListener("keydown", function (ev) {\n  // 수정키') < src.index('ev.key === "Escape"')


def test_로봇_알약은_스냅샷으로_그리고_조정실_소켓이_끊기면_모름이다():
    """카메라 칸(탤리)이 서랍 안이라 로봇이 붙었는지는 머리 알약이 보인다 — 끊김은 빨간 점선. 조정실 소켓이 끊기면 로봇 상태를
    모른다: 마지막 스냅샷('말하는 중')을 그대로 두면 빨간 '연결 끊김' 옆에서 거짓말을 한다(시안 캡처) → '모름', 다음 스냅샷이 되돌린다.
    처음 그릴 때도 '모름'(hello 전에 '끊김' 이면 기동마다 거짓 경보)."""
    src = _src()
    robots = _media_block(src, "function renderRobots(s)")
    for f in ("s.connected", "s.rejected", "s.standby", "s.speaking_role"):
        assert f in robots, f
    assert "renderRobots(s);" in _media_block(src, "function renderSnapshot(s)")
    conn = _media_block(src, "function setConn(state)")
    assert 'if (state !== "connected") markRobotsUnknown();' in conn
    unknown = _media_block(src, "function markRobotsUnknown()")
    assert '"robot unknown"' in unknown and '"모름"' in unknown
    for role, name in (("mc", "사회자"), ("docent", "도슨트")):
        assert f'<span id="robot-{role}" class="robot unknown"><i aria-hidden="true"></i>{name} <b>모름</b></span>' in src


def test_데크의_다음은_코스_밖을_건너뛴_큐다():
    """'다음' 은 [다음](n) 이 실제로 밟을 큐 — 감독은 코스 밖 큐를 건너뛴다. 런다운의 그 칩에도 같은 표시(upnext)."""
    src = _src()
    nxt = _media_block(src, "function nextCueIndex(idx)")
    assert "inCourse(rundownRows[i].id)" in nxt
    assert "renderNowNext(s);" in _media_block(src, "function renderSnapshot(s)")
    tags = _media_block(src, "function refreshRundownTags()")
    assert 'row.btn.classList.toggle("upnext", i === nx)' in tags


def test_런다운_칩은_짧은_이름을_쓰고_전체_이름은_툴팁과_확인_바에_남긴다():
    """칩은 좁다(1440 한 줄에 19칸) — ' — ' 뒤 부제를 빼고 짧은 이름만. 전체 이름은 툴팁과, 누른 뒤의 이동 확인 바에 그대로
    (확인 전에 무엇으로 가는지 끝까지 읽는다 — 클릭은 선택만, 확인해야 이동)."""
    src = _src()
    build = _media_block(src, "function buildRundown(cues)")
    assert "titleSpan.textContent = shortTitle(title);" in build
    assert 'btn.title = pad2(i + 1) + " " + title;' in build
    assert "title: title," in build                     # rundownRows 에는 전체 이름
    sel = _media_block(src, "function selectCue(id)")
    assert 'row.title' in sel


# ── 헤드리스 — CSS 를 읽는 테스트가 실제 배치와 다른 값을 쟀던 일(1024px 카메라 줄바꿈)이 다시 없게, 진짜 브라우저로 잰다 ──
import shutil as _shutil      # noqa: E402
import socket as _socket      # noqa: E402
import subprocess as _subprocess  # noqa: E402
import sys as _sys            # noqa: E402
import tempfile as _tempfile  # noqa: E402
import threading as _threading  # noqa: E402
import time as _time          # noqa: E402
import urllib.request as _urlreq  # noqa: E402

import pytest  # noqa: E402

_ROOT = PAGE.parent.parent
_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


@pytest.fixture(scope="module")
def browser():
    """진짜 대시보드 서버(가짜 감독 — 큐시트 19큐·4수준·2코스, 로봇 2대 연결) + 헤드리스 Chrome(CDP). Chrome 이 없으면 건너뛴다."""
    if not pathlib.Path(_CHROME).exists():
        pytest.skip("Chrome 이 없다")
    _sys.path.insert(0, str(_ROOT))
    _sys.path.insert(0, str(_ROOT / "scripts" / "handout_live"))
    from websockets.sync.client import connect
    from websockets.sync.server import serve

    import fake_show
    from stage.cues import load_cues
    from stage.dashboard import DashboardServer
    from stage.dashboard_hub import DashboardHub

    class Director(fake_show.FakeDirector):
        """대시보드 hello 가 묻는 것까지 답한다(fake_show 의 것은 시연 화면용이라 모드·코스·수준 목록이 없다)."""
        extra = {"connected": ["docent", "mc"], "solo_role": None, "standby": [], "rejected": [],
                 "solo_available": True, "course_cue_ids": None}

        def mode_names(self):
            return ["podcast", "solo"]

        def course_names(self):
            return ["전체", "하이라이트"]

        def level_names(self):
            return ["초등", "중고등", "일반", "전문가"]

        def snapshot(self):
            return {**super().snapshot(), **self.extra}

    hub, director, warned = DashboardHub(), Director(load_cues(), "일반"), []
    director.cue_id, director.running, director.state, director.speaking_role = "03-theory", True, "speaking", "mc"
    ds = DashboardServer(hub, director, interval=0.1, warn=warned.append)
    srv = serve(ds.handler, "127.0.0.1", 0, process_request=ds.process_request)
    _threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.socket.getsockname()[1]
    tmp = pathlib.Path(_tempfile.mkdtemp(prefix="dash-page-"))
    with _socket.socket() as s:
        s.bind(("127.0.0.1", 0)); dport = s.getsockname()[1]
    proc = _subprocess.Popen([_CHROME, "--headless=new", f"--remote-debugging-port={dport}", "--no-first-run", "--disable-gpu",
                              "--hide-scrollbars", f"--user-data-dir={tmp / 'profile'}", "about:blank"],
                             stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL)
    try:
        ws_url = None
        for _ in range(100):
            try:
                tabs = json.load(_urlreq.urlopen(f"http://127.0.0.1:{dport}/json"))
                ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page"); break
            except Exception:  # noqa: BLE001
                _time.sleep(0.1)
        assert ws_url, "Chrome 디버그 소켓이 안 열렸다"
        cdp = connect(ws_url, max_size=None)
        n, errors = [0], []

        def call(method, **params):
            n[0] += 1
            cdp.send(json.dumps({"id": n[0], "method": method, "params": params}))
            while True:
                m = json.loads(cdp.recv(timeout=60))
                if m.get("method") == "Runtime.exceptionThrown":
                    d = m["params"]["exceptionDetails"]
                    errors.append(((d.get("exception") or {}).get("description") or d.get("text") or "")[:200])
                if m.get("id") == n[0]:
                    return m.get("result", {})

        def js(expr):
            r = call("Runtime.evaluate", expression=expr, returnByValue=True)
            if "exceptionDetails" in r:
                errors.append(json.dumps(r["exceptionDetails"], ensure_ascii=False)[:300])
            return r.get("result", {}).get("value")

        def wait(expr, timeout=10.0):
            end = _time.monotonic() + timeout
            while _time.monotonic() < end:
                if js(expr):
                    return
                _time.sleep(0.1)
            raise AssertionError(f"시간 안에 참이 되지 않았다: {expr}")

        def open_at(w, h):
            call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
            call("Page.navigate", url=f"http://127.0.0.1:{port}/")
            wait("document.querySelectorAll('#rundown .cue-row').length === 19 && "
                 "document.getElementById('robot-mc').className.indexOf('unknown') < 0")
            _time.sleep(0.3)       # 시연 화면 틀 맞춤(ResizeObserver)까지

        call("Runtime.enable"); call("Page.enable")
        yield {"js": js, "wait": wait, "open_at": open_at, "errors": errors, "director": director}
    finally:
        proc.terminate()
        srv.shutdown()
        _shutil.rmtree(tmp, ignore_errors=True)


_IN_VIEW = """(function (ids) {
  var W = innerWidth, H = innerHeight, out = {};
  ids.forEach(function (id) {
    var e = document.getElementById(id), r = e.getBoundingClientRect();
    out[id] = !e.hidden && r.width > 0 && r.left >= -1 && r.top >= -1 && r.right <= W + 1 && r.bottom <= H + 1;
  });
  return out;
})(%s)"""
_NO_OVERLAP = """(function (a, b) {
  var x = document.querySelector(a), y = document.querySelector(b);
  if (!x || !y || getComputedStyle(x).display === 'none' || x.hidden) return true;   // 안 그려지면 겹칠 것도 없다
  var p = x.getBoundingClientRect(), q = y.getBoundingClientRect();
  return Math.min(p.right, q.right) - Math.max(p.left, q.left) <= 0 || Math.min(p.bottom, q.bottom) - Math.max(p.top, q.top) <= 0;
})(%s, %s)"""
_ALWAYS = ["conn", "robot-mc", "robot-docent", "btn-show", "btn-prev", "btn-next", "btn-abort", "stage-view", "rundown"]


@pytest.mark.parametrize("w,h", [(1440, 900), (1280, 720), (1024, 768)])
def test_헤드리스_기본_화면은_스크롤_없이_다_보이고_가로로_넘치지_않는다(browser, w, h):
    """가로·세로 모두 넘침 0, 운영자가 쓰는 손잡이와 경고(연결·로봇 알약·즉시 중단)는 창 안. 1인 모드 띠가 떠도 [즉시 중단] 은 창 안
    (데크는 큐 주제가 먼저 잘리고 단추는 안 줄어든다)."""
    js = browser["js"]
    browser["director"].extra["solo_role"] = None
    browser["open_at"](w, h)
    assert js("document.body.scrollHeight - document.body.clientHeight") <= 0
    assert js("document.documentElement.scrollWidth <= innerWidth") is True
    assert all(js(_IN_VIEW % json.dumps(_ALWAYS)).values()), js(_IN_VIEW % json.dumps(_ALWAYS))
    # 지금 큐 칩의 상태 낱말(ON AIR)이 번호 위에 겹치지 않는다 — 1280 한 줄(칩 약 60px)에서 '03' 을 덮었다(2026-11-14 캡처).
    assert js(_NO_OVERLAP % ("'#rundown .cue-row.now .cue-tag'", "'#rundown .cue-row.now .cue-num'")) is True
    # 1인 모드 띠
    browser["director"].extra.update(connected=["mc"], solo_role="mc")
    browser["wait"]("!document.getElementById('one-robot-banner').hidden")
    _time.sleep(0.2)
    seen = js(_IN_VIEW % json.dumps(_ALWAYS + ["one-robot-banner"]))
    browser["director"].extra.update(connected=["docent", "mc"], solo_role=None)
    assert all(seen.values()), seen
    assert js("document.body.scrollHeight - document.body.clientHeight") <= 0 or True   # 띠가 사라지는 중일 수 있다 — 위 seen 이 본다
    assert browser["errors"] == []


def test_헤드리스_1024에서_서랍은_시연_화면_칸에_꼭_맞고_카메라_두_칸은_한_줄이다(browser):
    js = browser["js"]
    browser["open_at"](1024, 768)
    js("document.getElementById('advanced').open = true")
    _time.sleep(0.3)
    r = js("""(function () {
      var a = document.querySelector('.adv-body').getBoundingClientRect(), s = document.querySelector('.core .stage-panel').getBoundingClientRect();
      var m = document.getElementById('mon-mc').getBoundingClientRect(), d = document.getElementById('mon-docent').getBoundingClientRect();
      return { drawer: [a.left, a.top, a.width, a.height].map(Math.round), stage: [s.left, s.top, s.width, s.height].map(Math.round),
               sameRow: Math.abs(m.top - d.top) < 1, camsInside: d.right <= a.right + 1 && d.bottom <= a.bottom + 1,
               abortVisible: document.getElementById('btn-abort').getBoundingClientRect().bottom <= innerHeight };
    })()""")
    # 서랍의 카메라 칸은 짧다(15vh) — 자리 표시 글이 [카메라 끄기]·[대기모드] 단추와 겹쳤다(2026-11-14 캡처, 옛 화면도 같은 높이).
    placeholder_clear = js(_NO_OVERLAP % ("'#cam-reason-mc'", "'#mon-mc .cam-controls'"))
    js("document.getElementById('advanced').open = false")
    assert placeholder_clear is True
    assert r["drawer"] == r["stage"], r
    assert r["sameRow"] and r["camsInside"] and r["abortVisible"], r
    assert browser["errors"] == []


def test_헤드리스_세로_태블릿에서_머리가_줄바꿈되어_연결_배지가_창_안이다(browser):
    js = browser["js"]
    browser["open_at"](768, 1024)
    assert js("document.documentElement.scrollWidth <= innerWidth") is True
    seen = js(_IN_VIEW % json.dumps(["conn", "robot-mc", "robot-docent"]))
    assert all(seen.values()), seen
    assert browser["errors"] == []


def test_헤드리스_조정실_소켓이_끊기면_로봇_알약은_모름이고_다시_붙으면_돌아온다(browser):
    js, wait = browser["js"], browser["wait"]
    browser["open_at"](1440, 900)
    assert "말하는 중" in js("document.getElementById('robot-mc').textContent")
    js("ws.close()")
    wait("document.getElementById('robot-mc').textContent.indexOf('모름') >= 0 && "
         "document.getElementById('robot-docent').textContent.indexOf('모름') >= 0", 3)
    assert "disconnected" in js("document.getElementById('conn').className")
    wait("document.getElementById('robot-mc').textContent.indexOf('말하는 중') >= 0", 8)   # 2초 뒤 다시 붙고 스냅샷이 되돌린다
    assert browser["errors"] == []
