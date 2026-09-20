import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import scripts.pregen_mc_lines as pregen
from stage.cues import Cue
from stage.levels import LEVEL_NAMES
from stage.mc_cache import cache_key, load_mc_lines


def test_지시문이_바뀌면_키가_바뀐다():
    """큐시트를 고치면 낡은 캐시가 드러나야 한다 — 안 그러면 옛 대사가 계속 나간다."""
    a = cache_key("c1", "일반", "지시문 A")
    b = cache_key("c1", "일반", "지시문 B")
    assert a != b


def test_수준이_다르면_키가_다르다():
    assert cache_key("c1", "초등", "같은 지시문") != cache_key("c1", "전문가", "같은 지시문")


def test_캐시가_없으면_빈_딕셔너리다(tmp_path):
    assert load_mc_lines(tmp_path / "없는파일.yaml") == {}


# ── `scripts/pregen_mc_lines.py` — LLM 은 부르지 않고 캐시 키·폴백·스킵
# 로직만 단위로 본다. `build_generate` 를 가짜로 갈아끼워 실제 추론 서버
# 왕복을 없애고, `cache_path` 도 `tmp_path` 로 돌려 실제 `data/mc_lines.yaml`
# 을 절대 건드리지 않는다.

_모든_수준_브리프 = {
    lvl: {"mc_brief": "브리프", "docent_brief": "해설"} for lvl in LEVEL_NAMES
}


def _고정_수준(monkeypatch, *names):
    """`main()` 이 `sys.argv[1:]` 로 도는 수준을 고정한다 — 안 그러면 기본값
    (전 수준)이 돌아 다른 수준의 스킵/생성이 이 테스트의 단언에 섞여 든다."""
    monkeypatch.setattr(sys, "argv", ["pregen_mc_lines.py", *names])


def test_이미_캐시에_있는_키는_다시_생성하지_않는다(monkeypatch, tmp_path):
    """캐시 히트를 재생성하면 사람이 이미 읽고 고친 문장이 조용히 새 것으로
    덮인다 — `key in out` 스킵이 그것을 막는다."""
    _고정_수준(monkeypatch, "일반")
    cue = Cue("c1", "제목", "mc", "옛 지시문", "partner", briefs=_모든_수준_브리프)
    monkeypatch.setattr(pregen, "load_cues", lambda: [cue])
    monkeypatch.setattr(pregen, "load_levels", lambda: {lvl: lvl for lvl in LEVEL_NAMES})
    key = cache_key("c1", "일반", "브리프")
    monkeypatch.setattr(pregen, "load_mc_lines", lambda: {key: "이미 고친 대사"})
    out_path = tmp_path / "mc_lines.yaml"
    monkeypatch.setattr(pregen, "cache_path", lambda: out_path)

    calls: list[str] = []
    monkeypatch.setattr(
        pregen, "build_generate",
        lambda level: (lambda role, brief, hist: calls.append(brief) or "새 대사"),
    )

    pregen.main()

    assert calls == [], f"이미 캐시에 있는 키를 다시 생성했다: {calls}"
    written = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert written[key] == "이미 고친 대사", "캐시 히트 값을 덮어썼다"


def test_mc_brief가_없으면_건너뛰고_생성을_부르지_않는다(monkeypatch, tmp_path, capsys):
    """이 섹션이 아직 그 수준으로 안 옮겨졌으면(`briefs` 에 항목이 없으면)
    `brief_for` 가 mc_brief 로 빈 문자열을 준다 — 빈 지시문으로 LLM 을
    불러 의미 없는 대사를 만들지 않고 건너뛴다."""
    _고정_수준(monkeypatch, "일반")
    cue = Cue("c1", "제목", "mc", "옛 지시문", "partner")  # briefs 없음
    monkeypatch.setattr(pregen, "load_cues", lambda: [cue])
    monkeypatch.setattr(pregen, "load_levels", lambda: {lvl: lvl for lvl in LEVEL_NAMES})
    monkeypatch.setattr(pregen, "load_mc_lines", lambda: {})
    out_path = tmp_path / "mc_lines.yaml"
    monkeypatch.setattr(pregen, "cache_path", lambda: out_path)

    calls: list[str] = []
    monkeypatch.setattr(
        pregen, "build_generate",
        lambda level: (lambda role, brief, hist: calls.append(brief) or "생성됨"),
    )

    pregen.main()

    assert calls == [], f"mc_brief 가 없는데도 생성을 불렀다: {calls}"
    assert "건너뜀" in capsys.readouterr().out
    written = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert written == {}


def test_새_항목은_생성해서_캐시_키로_저장한다(monkeypatch, tmp_path):
    """캐시 미스는 생성해서 `cache_key(cue.id, level, mc_brief)` 로 저장돼야
    한다 — 키가 틀리면 `Director._begin_cue` 가 영영 못 찾는다."""
    _고정_수준(monkeypatch, "일반")
    cue = Cue("c1", "제목", "mc", "옛 지시문", "partner", briefs=_모든_수준_브리프)
    monkeypatch.setattr(pregen, "load_cues", lambda: [cue])
    monkeypatch.setattr(pregen, "load_levels", lambda: {lvl: lvl for lvl in LEVEL_NAMES})
    monkeypatch.setattr(pregen, "load_mc_lines", lambda: {})
    out_path = tmp_path / "mc_lines.yaml"
    monkeypatch.setattr(pregen, "cache_path", lambda: out_path)
    monkeypatch.setattr(
        pregen, "build_generate",
        lambda level: (lambda role, brief, hist: f"[{brief}] 로 만든 여는 대사"),
    )

    pregen.main()

    key = cache_key("c1", "일반", "브리프")
    written = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert written[key] == "[브리프] 로 만든 여는 대사"
