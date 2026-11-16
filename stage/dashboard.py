"""무대감독 대시보드 서버 — 시안 B(방송 조정실) 페이지 한 장과 실시간 소켓 하나.

설계: `docs/superpowers/specs/2026-09-21-stage-dashboard-design.md`.

- **로봇용 포트(8777)와 다른 포트**(기본 `127.0.0.1:8778`)다. 로봇 포트는 로봇 때문에
  `0.0.0.0` 이어야 하는데, 이 화면은 인증 없이 시연을 멈추고 건너뛸 수 있다 — 위험한
  쪽을 기본으로 두지 않는다. 망에 열려면 `REACHY_DASHBOARD_HOST`.
- 루프백 바인드는 **운영자 자신의 브라우저**에서 오는 사이트 간 소켓을 못 막는다 —
  `/ws` 는 `Origin` 이 이 서버 주소(`Host`)와 같을 때만 받는다(`_check_origin`).
- **연결 하나에 보내는 스레드는 하나**(펌프)다. 명령 결과도 허브 이벤트로 흘려 같은
  펌프가 보낸다 — 두 스레드가 한 소켓에 동시에 쓰지 않게.
- 감독 상태(`Director.snapshot()`)는 펌프가 **락 밖에서** 읽는다. 허브 이벤트를 받는
  자리(감독이 락을 쥔 자리)에서 읽으면 교착이다.
- 경고는 **터미널로만** 낸다(`warn=print`). 허브로 되돌리면 이 서버가 자기 경고를 다시
  페이지로 흘리고, 그 경로가 망가졌을 때 끝없이 되돌아온다.
"""

import json
import pathlib
import queue
import re
import threading
import time
import urllib.parse
from typing import Callable

from websockets.exceptions import ConnectionClosed
from websockets.sync.server import serve as _ws_serve

from stage.console import dispatch as console_dispatch
from stage.handout import render_handout
from stage.say_label import parse_say_label
from stage.ws_quiet import quiet_empty_handshakes

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8778
SNAPSHOT_INTERVAL_S = 0.5
PAGE = pathlib.Path(__file__).with_name("dashboard_page.html")
# 관람객 보조 화면(2026-09-25, 결정 문서 「관람객용 보조 화면」). **읽기 전용** — 전용 소켓 `/ws/audience` 로
# 로봇 대사와 스냅샷의 아래 칸만 흘린다. 조정실 소켓(`/ws`)의 hello 에는 경고·거부 사유·관람객 STT 원문이 담긴
# 이벤트 이력이 실리고 스냅샷에는 연결·거부·카메라 상태가 있다 — 관람객 화면에 나갈 것이 아니다.
AUDIENCE_PAGE = pathlib.Path(__file__).with_name("audience_page.html")
# 교육자료 모션 화면(2026-11-12) — 실제 시연에서는 로봇 2대가 말하고 이 화면은 소리 없이 따라간다(공연 모드,
# `scripts/handout_live/live_follow.js`). **감독과 같은 오리진에서 줘야 한다** — `file://` 로 연 페이지는 `Origin: null` 이라
# `/ws/audience` 의 Origin 검사(`_check_origin`)가 거절한다(그게 맞다 — 검사를 풀지 않고 여기서 준다).
# 이름은 허용 목록이다(경로를 그대로 파일 이름으로 쓰지 않는다 — `/stage/../..` 같은 경로가 파일을 고르지 못하게).
_DESIGN = pathlib.Path(__file__).resolve().parent.parent / "docs" / "design"
MOTION_PAGES = {
    "paper": _DESIGN / "paper-stage.html",        # 일반 — 종이 무대(aimotion 24)
    "webtoon": _DESIGN / "webtoon-stage.html",    # 초등·중고등 — 웹툰 칸(aimotion 157)
    "exploded": _DESIGN / "exploded-stage.html",  # 전문가 — 분해도(aimotion 148)
    # 수준별 카드 화면(19큐 × 4수준 — 감독 수준을 따라 바꾼다, 2026-11-13) — 웹툰·분해도에 아직 없는 큐를 이어 보여 준다.
    # ~~종이 무대를 수준별 대본으로 빌드~~ — 종이 무대 안무가 일반 대본·카드 그림에 손으로 맞춰져 있어 다른 수준에서 멈췄다(02·15큐).
    "hud": _DESIGN / "handout-hud.html",
    # 수준에 맞는 화면을 골라 띄우고 수준이 바뀌면 갈아 끼우는 껍데기(2026-11-13) — 운영자는 이 주소 하나만 연다.
    "auto": pathlib.Path(__file__).with_name("stage_auto.html"),
}
# `/stage/auto` 가 (수준, 지금 큐)로 화면을 고르는 순서 — 앞이 그 수준 전용 화면, 뒤가 그 수준의 카드 화면(19큐 × 4수준).
# 전용 화면이 그 큐를 가졌으면 그것, 아니면 다음 것(2026-11-13 사용자 결정: 빈 큐는 그 수준의 카드 화면으로 잇는다).
# 왜: 웹툰·분해도는 01·02큐 시안뿐이라 06큐에서 수준을 바꾸면 화면이 01큐에 "공연 대기" 로 멈췄다(로봇은 06큐를 말하는데).
STAGE_ORDER = {
    "초등": ("webtoon", "hud"),
    "중고등": ("webtoon", "hud"),
    "일반": ("paper", "hud"),
    "전문가": ("exploded", "hud"),
}
STAGE_DEFAULT = "paper"              # 모르는 수준 — 감독의 기본 수준(일반) 화면
STAGE_LABELS = {"paper": "종이 무대", "webtoon": "웹툰", "exploded": "분해도", "hud": "카드 화면"}
# 빌드된 페이지 데이터의 큐 id(`"id": "06-bands"`). 페이지마다 데이터 모양은 다르지만 큐 id 를 이렇게 적는 것은 같다.
_CUE_ID = re.compile(r'"id":\s*"(\d\d-[a-z0-9-]+)"')


def stage_cues(page: pathlib.Path) -> list[str]:
    """그 화면이 가진 큐 id(나온 순서, 중복 없이). 파일이 없으면 [] — 고르는 쪽이 다음 화면으로 넘어간다."""
    try:
        text = page.read_text(encoding="utf-8")
    except OSError:
        return []
    return list(dict.fromkeys(_CUE_ID.findall(text)))
AUDIENCE_SNAPSHOT_KEYS = (
    "cue_index", "cue_id", "cue_count", "state", "speaking_role",
    "question_wait_s", "question_wait_total_s", "mode", "show_running", "course_position",
    # 관람객 수준 이름 — 교육자료가 감독의 수준을 따라간다(2026-10-01 계획 Task 2). 관람객 화면에 내보내도 되는 값이다.
    "level",
)
# 로봇이 보고하는 발화 시작·끝(2026-11-12) — **교육자료 공연 모드가 로봇 발화를 따라가는 시계**다. 실제 시연에서는
# 로봇 2대가 소리를 내고 화면은 소리 없이 따라간다(`scripts/handout_live/live_follow.js`). 싣는 칸은 역할·라벨·순번·큐·턴뿐.
SPEAKING_TYPES = ("speaking_started", "speaking_ended")


def audience_event(ev: dict, points_of: Callable[[str], int | None] | None = None) -> dict | None:
    """허브 이벤트 → 보조 화면 이벤트. **로봇에게 보낸 대사(`sent`/`say`)와 로봇의 발화 시작·끝(`recv`)만** 넘긴다.

    `cue`·`turn` 은 발화 라벨(`cue_id`)을 푼 것이다(`stage/say_label.py`) — 교육자료가 지금 말하는 대목을
    따라가는 데 쓴다. 풀 수 없으면(`points_of` 가 없거나 큐시트에 없는 라벨, 단독 모드) 둘 다 None 이고
    자막(`text`)은 그대로 흐른다. 나머지 이벤트(경고·관람객 STT·연결)는 None — 관람객 화면에 나갈 것이 아니다.
    """
    fields = ev.get("fields") or {}
    label = str(fields.get("cue_id", ""))
    ref = parse_say_label(label, points_of) if points_of is not None else None
    where = {"cue_id": label, "cue": ref.cue if ref else None, "turn": ref.turn if ref else None}
    if ev.get("kind") == "sent" and ev.get("type") == "say":
        return {"kind": "say", "role": ev.get("role"), "text": str(fields.get("text", "")), **where}
    if ev.get("kind") == "recv" and ev.get("type") in SPEAKING_TYPES:
        seq = fields.get("seq")
        return {"kind": ev.get("type"), "role": ev.get("role"), "seq": seq if isinstance(seq, int) else None, **where}
    return None


def audience_snapshot(snap: dict | None) -> dict | None:
    """스냅샷에서 보조 화면이 쓰는 칸만 — 허용 목록이다(새 칸이 생겨도 저절로 새지 않는다)."""
    if snap is None:
        return None
    return {k: snap.get(k) for k in AUDIENCE_SNAPSHOT_KEYS}


class DashboardServer:
    def __init__(self, hub, director, camera=None, dispatch: Callable = console_dispatch,
                 page: pathlib.Path = PAGE, interval: float = SNAPSHOT_INTERVAL_S,
                 warn: Callable[[str], None] = print,
                 audience_page: pathlib.Path = AUDIENCE_PAGE,
                 motion_pages: dict[str, pathlib.Path] | None = None) -> None:
        self._hub = hub
        self._director = director
        self._camera = camera
        self._dispatch = dispatch
        self._page = page
        self._audience_page = audience_page
        self._motion_pages = dict(MOTION_PAGES if motion_pages is None else motion_pages)
        self._manifest_cache: dict[str, tuple[float, list[str]]] = {}   # 화면 이름 → (mtime, 가진 큐)
        self._manifest_warned = False
        self._interval = interval
        self._warn = warn
        # 큐 id → 포인트 수. 라벨을 풀 때 처음 한 번 감독에게 묻는다(큐시트는 기동 뒤 안 바뀐다).
        self._points: dict[str, int] | None = None
        # 연결마다 송신 스레드가 있어 같은 순간에 `_points_of` 를 부른다 — 잠그지 않으면 실패 경고가 연결 수만큼 난다.
        self._points_lock = threading.Lock()

    # ── HTTP ──────────────────────────────────────────────────────
    def process_request(self, connection, request):
        # `request.path` 는 쿼리까지 담는다 — 그대로 비교하면 캐시 무효화용 `/?v=2` 나
        # `/ws?x=1` 이 404 가 된다. 경로만 본다.
        split = urllib.parse.urlsplit(request.path)
        path = split.path
        if path in ("/ws", "/ws/audience"):
            # 보조 화면 소켓도 같은 검사를 거친다 — 읽기 전용이라 조작 위험은 없지만, 다른 사이트가 시연 내용을
            # 몰래 받아 가는 창구가 될 이유도 없다.
            return self._check_origin(connection, request)  # None 이면 핸드셰이크로 넘어간다
        if path in ("/", "/index.html"):
            return self._serve_file(connection, self._page, "대시보드 페이지")
        if path == "/audience":
            return self._serve_file(connection, self._audience_page, "관람객 보조 화면")
        if path == "/handout":
            return self._serve_handout(connection, split.query)
        if path == "/stage/manifest":
            return self._serve_stage_manifest(connection)
        if path.startswith("/stage/"):
            page = self._motion_pages.get(path[len("/stage/"):])
            if page is None:
                return connection.respond(404, "not found")
            return self._serve_file(connection, page, f"교육자료 모션 화면({page.name})")
        return connection.respond(404, "not found")

    @staticmethod
    def _html(connection, status: int, body: str):
        resp = connection.respond(status, body)
        # `respond` 는 text/plain 을 붙인다 — 브라우저가 HTML 로 그리게 바꾼다.
        # `Headers` 는 같은 이름을 여러 번 담을 수 있어 대입만 하면 text/plain 이
        # 남은 채 한 줄이 더 붙는다 — 지우고 넣는다.
        del resp.headers["Content-Type"]
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
        return resp

    def _serve_file(self, connection, page: pathlib.Path, what: str):
        try:
            # 요청마다 읽는다 — 시연 중 페이지 파일을 고쳐도 새로고침으로 반영되고,
            # 파일이 사라졌으면 기동 때가 아니라 그 요청에서 500 + 경고로 드러난다.
            body = page.read_text(encoding="utf-8")
        except OSError as exc:
            self._warn(f"{what}를 못 읽었다({page}: {exc})")
            return connection.respond(500, "page missing")
        return self._html(connection, 200, body)

    def _level_labels(self) -> dict:
        names = self._director.level_names()
        fn = getattr(self._director, "level_labels", None)
        labels = fn() if callable(fn) else {}
        return {n: labels.get(n, n) for n in names}

    def stage_manifest(self) -> dict:
        """`/stage/auto` 가 화면을 고를 재료 — 수준별 순서·화면마다 가진 큐·이름. 가진 큐는 **빌드된 페이지에서** 읽는다
        (웹툰·분해도가 19큐로 늘면 여기를 안 고쳐도 따라온다). 파일이 바뀌면 다시 읽는다(mtime)."""
        cache = self._manifest_cache
        cues, missing = {}, []
        for name, page in self._motion_pages.items():
            if name == "auto":
                continue
            try:
                mt = page.stat().st_mtime
            except OSError:
                missing.append(name)
                continue
            if cache.get(name, (None,))[0] != mt:
                cache[name] = (mt, stage_cues(page))
            cues[name] = cache[name][1]
        if missing and not self._manifest_warned:
            # 한 번만 — 화면이 0.5초마다 묻는 것이 아니라 열 때 묻지만, 여러 창이 열면 같은 줄이 쌓인다.
            self._manifest_warned = True
            self._warn(f"교육자료 화면 파일이 없다({', '.join(missing)}) — 그 수준은 다음 화면으로 넘어간다"
                       " (.venv/bin/python -m scripts.handout_<이름>.build)")
        return {"order": {lv: list(names) for lv, names in STAGE_ORDER.items()}, "default": STAGE_DEFAULT,
                "labels": STAGE_LABELS, "cues": cues}

    def _serve_stage_manifest(self, connection):
        resp = connection.respond(200, json.dumps(self.stage_manifest(), ensure_ascii=False))
        del resp.headers["Content-Type"]
        resp.headers["Content-Type"] = "application/json; charset=utf-8"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    def _serve_handout(self, connection, query: str):
        """수준별 교육자료(`stage/handout.py`). 수준은 `?level=`, 없으면 **지금 감독의 수준**이다.

        모르는 수준은 400 — 조용히 기본 수준으로 바꿔 주면 초등 자료를 달라고 한 교사가 일반 자료를 받는다.
        """
        levels = self._director.level_names()
        courses = self._director.course_names()
        q = urllib.parse.parse_qs(query)
        asked = (q.get("level") or [""])[0].strip()
        # 별칭을 푼다(2026-11-16): 고르는 수준이 셋이 된 뒤에도 교사 손에 옛 `?level=초등` 주소가 남아 있다 —
        # 400 으로 막지 않고 합친 수준(중고등 대본)의 자료를 준다. 모르는 이름의 400 은 그대로다.
        canon = getattr(self._director, "canonical_level", None)
        if asked and callable(canon):
            asked = canon(asked)
        course = (q.get("course") or [""])[0].strip()
        if not asked or not course:
            snap = self._safe_snapshot() or {}
            asked = asked or snap.get("level") or (levels[0] if levels else "")
            course = course or snap.get("course") or (courses[0] if courses else "")
        if asked not in levels:
            return connection.respond(
                400, f"모르는 관람객 수준이다: {asked!r} — 고를 수 있는 것: {', '.join(levels)}"
            )
        if course not in courses:
            return connection.respond(
                400, f"모르는 코스다: {course!r} — 고를 수 있는 것: {', '.join(courses)}"
            )
        # 코스의 큐만 — "오늘 들은 이야기" 다. 전체면(None) 큐시트 전체.
        ids = self._director.course_ids(course)
        cues = tuple(c for c in self._director.cues() if ids is None or c.id in ids)
        try:
            body = render_handout(cues, asked, levels, course=course if len(courses) > 1 else None,
                                  labels=self._level_labels())
        except Exception as exc:  # noqa: BLE001 — 교육자료가 깨져도 서버는 산다. 원인은 터미널에
            self._warn(f"교육자료를 만들지 못했다({type(exc).__name__}: {exc})")
            return connection.respond(500, "handout failed")
        return self._html(connection, 200, body)

    def _check_origin(self, connection, request):
        """다른 사이트가 연 소켓(CSWSH)을 막는다. 통과면 None, 아니면 403 응답.

        **`127.0.0.1` 바인드로는 못 막는다.** 운영자 브라우저에 열린 아무 탭(광고·검색
        결과 속 스크립트)이나 `new WebSocket("ws://127.0.0.1:8778/ws")` 을 열 수 있고,
        브라우저는 웹소켓에 동일 출처 정책을 걸지 않는다 — 그 탭이 `a`·`n`·`g` 를 보내면
        인증 없는 이 화면이 시연을 멈추고 건너뛴다. 브라우저가 스스로 붙이는(페이지가
        못 바꾸는) `Origin` 이 이 서버의 주소(`Host`)와 같을 때만 받는다.

        `Origin` 이 **없으면** 받는다 — 브라우저가 아닌 클라이언트(테스트, 스크립트)다.
        브라우저는 웹소켓에 늘 `Origin` 을 붙이므로 이 예외로 사이트 간 공격이 새지 않는다.
        같은 헤더가 둘 이상이면 어느 쪽을 믿을지 정할 수 없으니 거절한다.
        """
        origins = request.headers.get_all("Origin")
        if not origins:
            return None
        hosts = request.headers.get_all("Host")
        ok = (
            len(origins) == 1
            and len(hosts) == 1
            # 호스트 이름은 대소문자를 가리지 않는다. `Origin: null`(sandbox·file://)은
            # netloc 이 비어 여기서 걸린다.
            and urllib.parse.urlsplit(origins[0]).netloc.lower() == hosts[0].lower()
        )
        if ok:
            return None
        self._warn(
            f"대시보드 소켓을 거절했다 — 다른 사이트에서 온 연결이다(Origin={origins}, Host={hosts}). "
            "운영자 브라우저의 다른 탭이 시연을 조작하려 했을 수 있다"
        )
        return connection.respond(403, "cross-origin dashboard connection refused")

    # ── WebSocket ─────────────────────────────────────────────────
    def handler(self, ws) -> None:
        # 경로로 가른다 — `process_request` 가 `/ws`·`/ws/audience` 만 핸드셰이크로 넘긴다.
        if urllib.parse.urlsplit(ws.request.path).path == "/ws/audience":
            self._audience(ws)
            return
        # **구독을 이력보다 먼저 한다.** 거꾸로면 이력을 읽은 뒤·구독하기 전에 난
        # 이벤트가 어디에도 안 실린다(조용히 빠진다). 이 순서면 그 틈의 이벤트가
        # 이력과 큐 양쪽에 실려 한 번 겹칠 수는 있어도 빠지지는 않는다.
        sub = self._hub.subscribe()
        viewer = self._camera.add_viewer(self._deliver_maker(sub)) if self._camera is not None else None
        stop = threading.Event()
        try:
            # hello 는 펌프를 띄우기 **전에** 이 스레드가 보낸다 — 펌프가 뜬 뒤에는
            # 펌프만 보낸다(한 소켓에 송신자는 언제나 하나).
            ws.send(self._dumps({
                "kind": "hello",
                "cues": self._director.cue_list(),
                # 헤더의 관람객 수준 버튼(levels.yaml 순서). 파일을 따로 읽지 않고 감독에게
                # 받는다 — 버튼 이름과 감독이 받아들이는 이름(`l <수준>`)이 한 곳에서 나온다.
                "levels": self._director.level_names(),
                # 버튼 글자(2026-11-16 — 내부 이름 "중고등" 을 '초중등' 으로 보인다). 보내는 명령은 여전히 내부 이름이다.
                # 이름표를 모르는 감독(테스트의 가짜 감독·옛 감독)이면 이름 그대로 — 버튼이 사라지지 않는다.
                "level_labels": self._level_labels(),
                # 헤더의 운영 모드 토글(podcast/solo 순서). 수준과 같은 이유로 감독에게
                # 받는다 — 버튼 이름과 `m <모드>` 가 받아들이는 이름이 한 곳에서 나온다.
                "modes": self._director.mode_names(),
                # 코스(전체/하이라이트, 2026-09-25) — courses.yaml 순서. 버튼 이름과 `k <코스>` 가 받는 이름이 한 곳에서.
                "courses": self._director.course_names(),
                "history": self._hub.history(),
                "snapshot": self._safe_snapshot(),
            }))
            threading.Thread(target=self._pump, args=(ws, sub, stop), daemon=True).start()
            for raw in ws:
                # `rtc` 모양만 여기서 가로챈다 — 그 외(깨진 JSON 포함)는 전부 `_on_command`
                # 로 넘겨 그쪽의 "규약에 안 맞는다" 경고 하나로만 걸러지게 한다. 여기서 JSON
                # 파싱 실패를 따로 warn 하면 같은 상황(깨진 메시지)에 경고 문구가 둘로
                # 갈라져 기존 계약(`_on_command` 의 "규약" 경고)이 깨진다.
                try:
                    obj = json.loads(raw)
                except (ValueError, TypeError):
                    obj = None
                if isinstance(obj, dict) and "rtc" in obj and self._camera is not None and viewer is not None:
                    rtc = obj["rtc"]
                    # `{"rtc": null}`/`{"rtc": 1}` 같은 비-dict 값을 그대로 넘기면
                    # `CameraRelay.on_viewer_rtc` 안의 `.get(...)` 가 AttributeError 를
                    # 내 이 핸들러 밖으로 새고, websockets 가 트레이스백만 남긴다(리뷰
                    # M7) — 위 `ConnectionClosed` 주석이 막으려던 것과 같은 부류의
                    # 노이즈다. `_on_command` 의 규약 위반 처리(경고하고 그 메시지만
                    # 버린다, 연결은 유지)와 같은 원칙으로 여기서도 그 자리에서 거른다.
                    if not isinstance(rtc, dict):
                        self._warn(
                            f"대시보드의 rtc 가 객체가 아니다({type(rtc).__name__}) — 버린다"
                        )
                        continue
                    self._camera.on_viewer_rtc(viewer, rtc)
                    continue
                self._on_command(raw)
        except ConnectionClosed:
            # 페이지가 close 프레임 없이 사라졌다(노트북 절전·Wi-Fi 끊김·브라우저 강제
            # 종료) — `for raw in ws` 가 ConnectionClosedError 를 낸다. 여기서 새면
            # websockets 가 "connection handler failed" 트레이스백을 찍는데, 운영자가 할
            # 일이 없는 정상 경로라 터미널의 진짜 경고를 묻어 버린다. 페이지는 스스로
            # 다시 붙는다. 펌프가 송신 실패로 1011 을 보내고 닫은 경우도 여기로 온다
            # (그 경고는 펌프가 이미 냈다).
            pass
        finally:
            stop.set()
            self._hub.unsubscribe(sub)
            if self._camera is not None and viewer is not None:
                self._camera.remove_viewer(viewer)

    def _audience(self, ws) -> None:
        """관람객 보조 화면 연결 하나 — **읽기 전용**. 받은 메시지는 버린다(명령은 조정실 `/ws` 에서만).

        조정실 핸들러와 같은 순서(구독 → hello → 펌프)다. hello 에는 이벤트 이력 대신 **마지막 대사 하나**만
        싣는다 — 새로고침해도 지금 자막이 바로 보이고, 이력 속 경고·STT 원문은 나가지 않는다.
        """
        sub = self._hub.subscribe()
        stop = threading.Event()
        try:
            # 마지막 대사 하나 + (그 뒤에 왔다면) 마지막 발화 시작 — 공연 도중에 붙은 화면이 지금 몇 초째인지 안다.
            # 경과(`age_s`)는 **서버가** 잰다: 화면 PC 와 감독 PC 의 시계가 달라도 어긋나지 않게.
            last_say, last_started = None, None
            for ev in reversed(self._hub.history()):
                got = audience_event(ev, self._points_of)
                if got is None:
                    continue
                if got["kind"] == "speaking_started" and last_started is None and last_say is None:
                    last_started = {**got, "age_s": round(max(0.0, time.time() - float(ev.get("t") or time.time())), 3)}
                if got["kind"] == "say":
                    last_say = got
                    break
            ws.send(self._dumps({
                "kind": "hello",
                "cues": [{"id": c["id"], "title": c["title"]} for c in self._director.cue_list()],
                "say": last_say,
                "started": last_started,
                "snapshot": audience_snapshot(self._safe_snapshot()),
            }))
            threading.Thread(target=self._pump, args=(ws, sub, stop, True), daemon=True).start()
            warned = False
            for _raw in ws:
                if not warned:
                    # 관람객 기기에서 명령을 보내려 했을 수 있다 — 조용히 삼키지 않고 한 번 알린다.
                    self._warn("관람객 보조 화면 소켓은 읽기 전용이다 — 받은 메시지를 버린다(명령은 조정실에서)")
                    warned = True
        except ConnectionClosed:
            pass
        finally:
            stop.set()
            self._hub.unsubscribe(sub)

    @staticmethod
    def _deliver_maker(sub):
        def deliver(ev: dict) -> None:
            try:
                sub.queue.put_nowait(ev)
            except queue.Full:
                # `mark_dropped()` — 이 `deliver` 는 카메라 릴레이를 거쳐 로봇 연결
                # 스레드에서도 불린다. 허브의 `publish` 도 같은 `sub.dropped` 를 다른
                # 스레드에서 올릴 수 있어, 락 없는 `+= 1` 은 카운트를 잃는다
                # (`stage/dashboard_hub.py::Subscription.mark_dropped` 가 락을 쥔다).
                sub.mark_dropped()
        return deliver

    def _pump(self, ws, sub, stop: threading.Event, audience: bool = False) -> None:
        """이 연결의 유일한 송신자. 이벤트는 오는 대로, 스냅샷은 `interval` 마다.

        `audience` 면 관람객 보조 화면용으로 거른다 — 대사(`say`)만, 스냅샷은 허용 칸만.
        """
        last = 0.0
        dropped_seen = 0
        while not stop.is_set():
            try:
                ev = sub.queue.get(timeout=self._interval)
            except queue.Empty:
                ev = None
            # 구독 큐가 넘쳐 허브가 버린 이벤트. 상태 칸은 다음 스냅샷으로 다시 맞춰지지만
            # 대사·경고 줄은 로그에서 **빠진 채** 남는다 — 페이지만 보면 모른다. 늘어난
            # 만큼만 한 번 알린다(같은 수를 주기마다 되풀이하지 않게). 보내기 **전에**
            # 알려, 버린 뒤 처음 도착한 이벤트보다 경고가 늦지 않게 한다.
            dropped = sub.dropped
            if dropped > dropped_seen:
                self._warn(
                    f"대시보드 구독 큐가 넘쳐 이벤트 {dropped - dropped_seen}개를 버렸다"
                    f"(이 연결 누적 {dropped}) — 페이지 로그에서 빠졌다. 상태는 다음 스냅샷으로 맞춰진다"
                )
                dropped_seen = dropped
            if audience and ev is not None:
                ev = audience_event(ev, self._points_of)
            try:
                if ev is not None:
                    ws.send(self._dumps(ev))
                if time.monotonic() - last >= self._interval:
                    snap = self._safe_snapshot()
                    if audience:
                        snap = audience_snapshot(snap)
                    if snap is not None:
                        ws.send(self._dumps({"kind": "snapshot", **snap}))
                    last = time.monotonic()
            except ConnectionClosed:
                return  # 연결이 닫혔다. 핸들러가 정리한다.
            except Exception as exc:  # noqa: BLE001
                # **조용히 return 하면 안 된다.** 이 스레드가 이 연결의 유일한 송신자라,
                # 여기서 말없이 끝나면 소켓은 열린 채 페이지가 그 자리에서 굳는다(재접속도
                # 안 한다 — 끊긴 게 아니므로). 가장 흔한 원인은 직렬화 실패(문자열이 아닌
                # dict 키는 `default=str` 로도 못 넘긴다). 알리고 1011 로 닫아 핸들러가
                # 정리하고 페이지가 다시 붙게 한다.
                self._warn(
                    f"대시보드 송신 실패({type(exc).__name__}: {exc}) — 이 연결을 닫는다"
                    "(페이지는 다시 붙는다)"
                )
                ws.close(1011, "dashboard send failed")
                return

    def _points_of(self, cue_id: str) -> int | None:
        """그 큐의 포인트 수 — 발화 라벨의 마지막 도슨트(`:docent`)를 몇 번째로 읽을지 정한다.

        감독이 큐시트를 못 주면 **한 번만 알리고** 라벨을 못 읽을 뿐 자막은 계속 흐른다(교육자료·보조 화면이
        죽을 이유가 아니다).
        """
        with self._points_lock:
            if self._points is None:
                try:
                    self._points = {c.id: len(c.points) for c in self._director.cues()}
                except Exception as exc:  # noqa: BLE001
                    self._warn(
                        f"라벨을 읽으려 감독에게 큐시트를 물었으나 실패했다({type(exc).__name__}: {exc}) — "
                        "자막은 그대로 흐르고 큐·대목 정보만 빠진다"
                    )
                    self._points = {}
            points = self._points
        return points.get(cue_id)

    def _safe_snapshot(self) -> dict | None:
        try:
            snap = self._director.snapshot()
        except Exception as exc:  # noqa: BLE001
            self._warn(f"대시보드 스냅샷 실패({type(exc).__name__}: {exc}) — 다음 주기에 다시 읽는다")
            return None
        if self._camera is not None:
            snap = {**snap, "cameras": self._camera.snapshot()}
        return snap

    def _on_command(self, raw) -> None:
        try:
            # 콘솔(`run_console`)과 같게 `strip().lower()` — 같은 문자열이 두 길에서
            # 다르게 해석되면 명령 경로를 하나로 둔 의미가 없다. 큐 id 는 전부 소문자다.
            cmd = str(json.loads(raw)["cmd"]).strip().lower()
        except (ValueError, KeyError, TypeError):
            self._warn(f"대시보드 명령이 규약에 안 맞는다 — 버린다: {str(raw)[:80]!r}")
            return
        # **운영자 조작을 터미널 로그에도 남긴다**(2026-09-24). 페이지는 허브의 `command`
        # 이벤트로 보지만 `start-director.log` 에는 아무것도 안 남아, 문제 보고를 받고
        # 로그를 읽을 때 "누가 언제 멈췄나" 를 재구성할 수 없었다. 콘솔(`run_console`)과
        # 같은 모양의 한 줄이다.
        self._warn(f"[운영] 대시보드 {cmd}")
        lines: list[str] = []
        ok = True
        try:
            # `camera=self._camera` 를 안 넘기면 `console.dispatch` 의 `c` 분기가
            # 항상 `camera is None` 으로 보고 거절한다 — 대시보드의 카메라 켜기/끄기
            # 버튼이 조용히 아무 일도 안 하게 된다(실기에서 직접 눌러 보고서야
            # 드러났다, 13개 태스크 리뷰·최종 리뷰 모두 이 호출부를 안 봤다).
            self._dispatch(self._director, cmd, lines.append, camera=self._camera)
        except Exception as exc:  # noqa: BLE001 — 콘솔과 같다: 거절은 보여주고 계속
            ok = False
            lines.append(f"거절됨: {exc}")
            # 페이지에만 보이면 안 된다 — 콘솔은 거절을 터미널에 찍고, 문제 보고를 받으면
            # 터미널 로그부터 읽는다. 대시보드에서 누른 것도 같은 자리에 남긴다.
            self._warn(f"대시보드 명령 {cmd!r} 거절됨: {exc}")
        # 결과는 이 소켓에 직접 쓰지 않고 허브로 흘린다 — 여기서 `ws.send` 하면 펌프와
        # 두 스레드가 한 소켓에 쓰게 되고, 다른 대시보드는 누가 무엇을 눌렀는지 못 본다.
        self._hub.publish("command", cmd=cmd, ok=ok, lines=lines)

    @staticmethod
    def _dumps(obj) -> str:
        return json.dumps(obj, ensure_ascii=False, default=str)


def start_dashboard(hub, director, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                    camera=None, warn: Callable[[str], None] = print):
    """대시보드를 띄운다. **실패해도 감독·콘솔은 그대로 돈다** — 경고하고 None."""
    ds = DashboardServer(hub, director, camera=camera, warn=warn)
    try:
        quiet_empty_handshakes()   # 브라우저가 미리 열어 둔 빈 연결의 스택을 거른다(stage/ws_quiet.py)
        srv = _ws_serve(ds.handler, host, port, process_request=ds.process_request)
    # `bind()` 는 0~65535 밖의 포트(`REACHY_DASHBOARD_PORT=99999`)에 OSError 가 아니라
    # OverflowError 를 낸다 — OSError 만 잡으면 그 하나로 감독이 기동에서 죽었다(최종
    # 리뷰 Y4). 막힌 포트와 같은 실패다: 경고하고 None.
    except (OSError, OverflowError) as exc:
        warn(f"대시보드를 띄우지 못했다({host}:{port} — {exc}) — 감독과 콘솔은 그대로 돈다")
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    warn(f"대시보드 — http://{host}:{port}/")
    return srv
