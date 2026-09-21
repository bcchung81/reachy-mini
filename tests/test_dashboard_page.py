import pathlib
import re

PAGE = pathlib.Path(__file__).parent.parent / "stage" / "dashboard_page.html"
IDS = ["conn", "cue-label", "level", "mon-mc", "mon-docent", "tag-mc", "tag-docent",
       "cap-mc", "cap-docent", "rundown", "goto-bar", "goto-confirm", "goto-cancel",
       "btn-prev", "btn-restart", "btn-next", "btn-start", "btn-abort",
       "auto-text", "auto-bar", "log"]


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
