"""고정 대사를 미리 합성해 TTS 캐시에 굽는다 — `./reachy.sh bake`.

계획 `docs/superpowers/plans/2026-09-25-tts-result-cache.md`. 캐시 프록시(`tts_cache_proxy.py`)는
여기서 구운 소리만 내보낸다.

**캐시 키는 로봇이 실제로 보내는 요청과 바이트 단위로 같아야 한다.** 그래서 문장 분할·요청 본문·
역할 목소리를 여기서 다시 짜지 않고 **로봇 앱의 함수를 그대로 부른다**:

- 문장 분할: `clauses.split_sentences`(로봇 `session.speak` 가 쓰는 것 — 감독 쪽
  `stage/speech_text.split_sentences` 와 **다른 구현**이다)
- 요청 본문: `tts._qwen_body`(화자·배속·어조·stream·response_format)
- 역할 목소리: `main.apply_role_voice`(설정 사다리 — 설정 파일 값이 있으면 그것이 이긴다)

도구에서 다시 짜면 앱과 갈라지고, 갈라진 줄 모른 채 "구웠다" 를 본다(docs/lessons.md 「측정·예열
도구는 앱이 실제로 쓰는 경로를 태운다」). 그래도 로봇 쪽 설정이 굽기와 달라지면 프록시가
"고정 대사인데 캐시 키가 다르다" 로 경고한다.

사용:
    .venv/bin/python scripts/bake_tts.py [--upstream http://127.0.0.1:8098] [--cache-dir …]
        [--check] [--level 일반] [--limit N] [--force] [--prune]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "voice_chat" / "voice_chat"))

import clauses as robot_clauses  # noqa: E402
import main as robot_main  # noqa: E402
import tts as robot_tts  # noqa: E402

from stage.cues import (  # noqa: E402
    QA_ACK_EMOTIONS,
    QA_ACK_LINES,
    QUESTION_PROMPT_EMOTION,
    QUESTION_PROMPTS,
    SOLO_ACK_EMOTIONS,
    SOLO_ACK_LINES,
    load_cues,
)
from tts_cache_proxy import INDEX_NAME, cache_key, default_cache_dir, is_cacheable  # noqa: E402

# `main.apply_role_voice` 가 넣는 환경변수. **역할을 바꿀 때마다 먼저 지운다** — 그 함수는
# "이미 값이 있으면 덮지 않는다"(운영자가 정한 값을 지키려는 규칙)라, 안 지우면 사회자 다음에
# 부른 도슨트가 사회자 목소리로 구워진다.
_ROLE_ENV = ("TTS_QWEN_VOICE", "TTS_QWEN_SPEED", "TTS_QWEN_INSTRUCT")
SYNTH_TIMEOUT_S = 120.0


@dataclass(frozen=True)
class Line:
    """로봇이 소리 내 읽는 고정 대사 한 줄."""

    role: str        # "mc" | "docent" — 어느 로봇(목소리)이 읽나
    text: str
    where: str       # 사람이 읽는 출처("02-history 1턴 일반")
    level: str | None
    emotion: str


def fixed_lines(cues=None) -> list[Line]:
    """무대에서 고정으로 나가는 대사 전부 — 큐시트 + 감독의 고정 멘트.

    도슨트 설명만 수준별이고 사회자 대사는 수준 공통이다. 1인 모드(한 대가 양쪽을 읽는다)의
    다른 목소리 조합은 굽지 않는다 — 폴백이라 캐시 없이 합성으로 돈다.
    """
    out: list[Line] = []
    for c in cues if cues is not None else load_cues():
        out.append(Line("mc", c.mc, f"{c.id} 오프닝", None, c.mc_emotion))
        for i, t in enumerate(c.points):
            if t.ask:
                out.append(Line("mc", t.ask, f"{c.id} {i}턴 질문", None, t.ask_emotion))
            for lv, a in t.answers.items():
                out.append(Line("docent", a, f"{c.id} {i}턴 {lv}", lv, t.answer_emotion))
        if c.mc_after:
            out.append(Line("mc", c.mc_after, f"{c.id} 받아치기", None, c.mc_after_emotion))
    for text, emo in zip(QA_ACK_LINES, QA_ACK_EMOTIONS):
        out.append(Line("mc", text, "질문 확인 멘트", None, emo))
    for text in QUESTION_PROMPTS:
        out.append(Line("mc", text, "재질문", None, QUESTION_PROMPT_EMOTION))
    # 단독 모드의 확인 멘트(2026-09-25) — 사회자 목소리. 답은 생성이라 굽지 않는다.
    for text, emo in zip(SOLO_ACK_LINES, SOLO_ACK_EMOTIONS):
        out.append(Line("mc", text, "단독 확인 멘트", None, emo))
    return out


def use_role(role: str) -> None:
    """로봇 앱이 그 역할로 뜰 때와 같은 목소리 설정을 만든다."""
    for k in _ROLE_ENV:
        os.environ.pop(k, None)
    robot_main.apply_role_voice(role)


def bodies_for(line: Line) -> list[tuple[str, dict]]:
    """이 대사를 로봇이 말할 때 TTS 에 보내는 요청들 — (문장, 본문).

    로봇 경로 그대로다: `session.speak` 가 `text.strip()` 뒤 `clauses.split_sentences` 로 나눠 두 문장
    이상이면 문장마다, 한 문장이면 통째로 `Speaker.speak` 에 넘기고, 워커가 `_qwen_body` 를 만든다.
    감정 어조는 로봇처럼 `set_emotion` 을 먼저 부른다(스위치가 꺼져 있으면 효과가 없다).
    """
    use_role(line.role)
    robot_tts.set_emotion(line.emotion)
    text = (line.text or "").strip()
    if not text:
        return []
    sentences = robot_clauses.split_sentences(text)
    parts = sentences if len(sentences) > 1 else [text]
    out = []
    for s in parts:
        s = s.strip()
        if s:
            out.append((s, robot_tts._qwen_body(s, None, stream=robot_tts.QWEN_STREAM)))
    return out


def plan(lines: list[Line], level: str | None = None) -> list[dict]:
    """구울 항목 — 키가 같은 문장은 한 번만. 각 항목에 어디서 쓰이는지를 모은다."""
    by_key: dict[str, dict] = {}
    for line in lines:
        if level and line.level and line.level != level:
            continue
        for sentence, body in bodies_for(line):
            key = cache_key(body)
            e = by_key.get(key)
            if e is None:
                e = by_key[key] = {
                    "key": key, "text": sentence, "role": line.role,
                    "voice": body.get("voice"), "speed": body.get("speed"),
                    "instructions": body.get("instructions"),
                    "levels": [], "where": [], "body": body,
                }
            if line.level and line.level not in e["levels"]:
                e["levels"].append(line.level)
            e["where"].append(line.where)
    return list(by_key.values())


def write_index(cache_dir: pathlib.Path, entries: list[dict]) -> None:
    """프록시가 드리프트를 잡는 색인 — **지금 대본의 고정 대사 전부**(구웠든 안 구웠든).

    원자적으로 바꾼다 — 프록시가 반쯤 쓴 색인을 읽으면 드리프트 경고가 틀린다.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    data = {"entries": [{k: v for k, v in e.items() if k != "body"} for e in entries]}
    tmp = cache_dir / (INDEX_NAME + ".part")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, cache_dir / INDEX_NAME)


def synth(upstream: str, body: dict) -> bytes:
    """업스트림(CrispASR)에 **직접** 합성을 요청해 PCM 을 다 받는다. 프록시를 거치지 않는다 —
    굽기는 원본 소리를 만드는 일이다."""
    req = urllib.request.Request(
        upstream.rstrip("/") + "/v1/audio/speech",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=SYNTH_TIMEOUT_S) as r:
        ctype = (r.headers.get("Content-Type") or "").lower()
        data = r.read()
    if "pcm" not in ctype:
        raise RuntimeError(f"PCM 이 아닌 응답이다({ctype!r}) — 스트리밍 PCM 을 모르는 서버인가")
    if not data:
        raise RuntimeError("빈 응답")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description="고정 대사를 TTS 캐시에 굽는다")
    ap.add_argument("--upstream", default="http://127.0.0.1:8098", help="CrispASR 주소(프록시가 아니라)")
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--check", action="store_true", help="합성하지 않고 적중/전체만 센다")
    ap.add_argument("--level", default=None, help="도슨트 설명을 이 수준만(사회자 대사는 늘 포함)")
    ap.add_argument("--limit", type=int, default=0, help="이번에 최대 N개만 굽는다(시험용)")
    ap.add_argument("--force", action="store_true", help="있는 것도 다시 굽는다")
    ap.add_argument("--prune", action="store_true", help="지금 대본에 없는 캐시 파일을 지운다")
    args = ap.parse_args()

    cache_dir = pathlib.Path(args.cache_dir).expanduser() if args.cache_dir else default_cache_dir()
    if not robot_tts.QWEN_STREAM:
        print("⚠ TTS_QWEN_STREAM 이 꺼져 있다 — 로봇이 wav 로 요청하므로 캐시가 쓰이지 않는다(스트리밍 PCM 만 캐시)")
    entries = plan(fixed_lines(), args.level)
    skipped = [e for e in entries if not is_cacheable(e["body"])]
    entries = [e for e in entries if is_cacheable(e["body"])]
    present = [e for e in entries if (cache_dir / f"{e['key']}.pcm").is_file()]
    missing = [e for e in entries if e not in present] if not args.force else list(entries)

    by_group: dict[str, list[int]] = {}
    for e in entries:
        groups = ["사회자"] if e["role"] == "mc" else (e["levels"] or ["도슨트"])
        for g in groups:
            hit = 1 if (cache_dir / f"{e['key']}.pcm").is_file() else 0
            t = by_group.setdefault(g, [0, 0])
            t[0] += hit
            t[1] += 1
    summary = " · ".join(f"{g} {h}/{n}" for g, (h, n) in by_group.items())
    print(f"TTS 캐시 {cache_dir}: 고정 대사 {len(entries)}문장 중 {len(present)}개 구움 ({summary})")
    if skipped:
        print(f"   ⚠ 스트리밍 PCM 이 아닌 요청 {len(skipped)}개는 캐시 대상이 아니다")

    if args.check:
        if len(present) < len(entries):
            print(f"   ⚠ {len(entries) - len(present)}문장이 캐시에 없다 — 그 대사는 실시간 합성으로 나간다."
                  " ./reachy.sh bake 로 굽는다")
        return 0

    write_index(cache_dir, entries)

    if args.prune:
        keep = {f"{e['key']}.pcm" for e in plan(fixed_lines())}
        orphans = [p for p in cache_dir.glob("*.pcm") if p.name not in keep]
        for p in orphans:
            p.unlink()
        print(f"   지금 대본에 없는 캐시 {len(orphans)}개를 지웠다")

    todo = missing[: args.limit] if args.limit else missing
    if not todo:
        print("   구울 것이 없다")
        return 0
    print(f"   {len(todo)}문장을 굽는다(업스트림 {args.upstream})")
    t0 = time.time()
    audio_s = 0.0
    failed = 0
    for i, e in enumerate(todo, 1):
        t1 = time.time()
        try:
            data = synth(args.upstream, e["body"])
        except (urllib.error.URLError, OSError, TimeoutError, RuntimeError) as exc:
            failed += 1
            print(f"   ✗ [{i}/{len(todo)}] {e['where'][0]} — {type(exc).__name__}: {exc}")
            continue
        part = cache_dir / f".{e['key']}.pcm.part"
        part.write_bytes(data)
        os.replace(part, cache_dir / f"{e['key']}.pcm")   # 반쯤 쓴 파일이 캐시로 보이지 않게
        secs = len(data) / 2 / robot_tts.QWEN_PCM_RATE
        audio_s += secs
        took = time.time() - t1
        eta = (time.time() - t0) / i * (len(todo) - i)
        print(f"   [{i}/{len(todo)}] {took:4.1f}s(소리 {secs:4.1f}s) {e['role']:6} {e['text'][:30]!r}"
              f"  남은 약 {eta / 60:.0f}분", flush=True)
    total = time.time() - t0
    print(f"   끝 — {len(todo) - failed}개 구움, 실패 {failed}, 소리 {audio_s / 60:.1f}분을 {total / 60:.1f}분에"
          f"(RTF {total / audio_s:.2f})" if audio_s else f"   끝 — 실패 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
