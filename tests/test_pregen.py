import pathlib
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import scripts.pregen_mc_lines as pregen
import stage.mc_cache as mc_cache_mod
from stage.cues import Cue
from stage.levels import LEVEL_NAMES
from stage.mc_cache import McCacheError, cache_key, load_mc_lines


def test_지시문이_바뀌면_키가_바뀐다():
    """큐시트를 고치면 낡은 캐시가 드러나야 한다 — 안 그러면 옛 대사가 계속 나간다."""
    a = cache_key("c1", "일반", "지시문 A")
    b = cache_key("c1", "일반", "지시문 B")
    assert a != b


def test_수준이_다르면_키가_다르다():
    assert cache_key("c1", "초등", "같은 지시문") != cache_key("c1", "전문가", "같은 지시문")


def test_캐시가_없으면_빈_딕셔너리다(tmp_path):
    assert load_mc_lines(tmp_path / "없는파일.yaml") == {}


# ── `load_mc_lines` — 사람이 손으로 고치는 파일이라 값 타입을 검사한다
# (리뷰 Important 3, `stage/cues.py` 리뷰 A8a 와 같은 함정) ─────────────

def test_빈_파일은_빈_딕셔너리다(tmp_path):
    """아직 아무것도 생성 안 한 상태 — 파일이 없는 것과 같게 본다(에러가 아니다)."""
    p = tmp_path / "mc_lines.yaml"
    p.write_text("", encoding="utf-8")
    assert load_mc_lines(p) == {}


def test_값이_문자열이_아니면_소리_내어_실패한다(tmp_path):
    """`키: true`/`키: 3` 으로 손이 미끄러지면 그 값이 그대로 `machine.speak()`
    까지 흘러가 `Director._estimate` 의 `len()` 에서야 TypeError 로 터진다
    (`stage/cues.py` 가 리뷰 A8a 로 이미 겪은 함정과 같은 자리) — 여기서
    미리 소리 내어 막는다."""
    p = tmp_path / "mc_lines.yaml"
    p.write_text("c1|초등|abcdef123456: true\n", encoding="utf-8")
    with pytest.raises(McCacheError, match="문자열이 아니다"):
        load_mc_lines(p)


def test_최상위가_매핑이_아니면_소리_내어_실패한다(tmp_path):
    p = tmp_path / "mc_lines.yaml"
    p.write_text("- 목록이다\n- 매핑이 아니다\n", encoding="utf-8")
    with pytest.raises(McCacheError, match="매핑이어야"):
        load_mc_lines(p)


def test_REACHY_MC_LINES_PATH로_캐시_경로를_바꾼다(monkeypatch, tmp_path):
    """형제 로더 `cues_path`/`levels_path` 둘 다 환경변수 오버라이드가 있다 —
    이 파일만 하드코딩이면 실기에서 위치를 옮기려 할 때 코드를 고쳐야 한다."""
    custom = tmp_path / "다른곳" / "mc_lines.yaml"
    monkeypatch.setenv("REACHY_MC_LINES_PATH", str(custom))
    assert mc_cache_mod.cache_path() == custom


# ── `scripts/pregen_mc_lines.py` — LLM 은 부르지 않고 캐시 키·폴백·스킵·
# 파일 보존 로직만 단위로 본다. `build_generate` 를 가짜로 갈아끼워 실제
# 추론 서버 왕복을 없애고, `cache_path`(스크립트·`stage.mc_cache` 양쪽 모두)
# 도 `tmp_path` 로 돌려 실제 `data/mc_lines.yaml` 을 절대 건드리지 않는다.

_모든_수준_브리프 = {
    lvl: {"mc_brief": "브리프", "docent_brief": "해설"} for lvl in LEVEL_NAMES
}


def _고정_수준(monkeypatch, *names):
    """`main()` 이 `sys.argv[1:]` 로 도는 수준을 고정한다 — 안 그러면 기본값
    (전 수준)이 돌아 다른 수준의 스킵/생성이 이 테스트의 단언에 섞여 든다."""
    monkeypatch.setattr(sys, "argv", ["pregen_mc_lines.py", *names])


def _캐시_경로_고정(monkeypatch, out_path):
    """`pregen.main()` 자신이 부르는 `cache_path()` 와, `load_mc_lines()` 의
    기본 인자가 부르는 `stage.mc_cache.cache_path()` 는 **서로 다른 이름
    바인딩**이다(`from ... import cache_path` 가 각 모듈에 별도 복사를
    만든다) — 하나만 갈아끼우면 다른 하나는 여전히 진짜 `data/mc_lines.yaml`
    을 본다. 실제 파일로 이어붙임/보존을 검증하려면 둘 다 바꿔야 한다."""
    monkeypatch.setattr(pregen, "cache_path", lambda: out_path)
    monkeypatch.setattr(mc_cache_mod, "cache_path", lambda: out_path)


def test_mc_brief가_없으면_건너뛰고_생성을_부르지_않는다(monkeypatch, tmp_path, capsys):
    """이 섹션이 아직 그 수준으로 안 옮겨졌으면(`briefs` 에 항목이 없으면)
    `brief_for` 가 mc_brief 로 빈 문자열을 준다 — 빈 지시문으로 LLM 을
    불러 의미 없는 대사를 만들지 않고 건너뛴다. 아무것도 새로 만든 게
    없으면 파일도 손대지 않는다(없던 파일은 그대로 없다)."""
    _고정_수준(monkeypatch, "일반")
    cue = Cue("c1", "제목", "mc", "옛 지시문", "partner")  # briefs 없음
    monkeypatch.setattr(pregen, "load_cues", lambda: [cue])
    monkeypatch.setattr(pregen, "load_levels", lambda: {lvl: lvl for lvl in LEVEL_NAMES})
    out_path = tmp_path / "mc_lines.yaml"  # 아직 존재하지 않는다
    _캐시_경로_고정(monkeypatch, out_path)

    calls: list[str] = []
    monkeypatch.setattr(
        pregen, "build_generate",
        lambda level: (lambda role, brief, hist: calls.append(brief) or "생성됨"),
    )

    pregen.main()

    assert calls == [], f"mc_brief 가 없는데도 생성을 불렀다: {calls}"
    assert "건너뜀" in capsys.readouterr().out
    assert not out_path.exists(), "새로 만든 게 없는데 파일을 만들었다"


def test_이미_캐시에_있는_키는_다시_생성하지_않고_파일도_안_건드린다(monkeypatch, tmp_path):
    """캐시 히트를 재생성하면 사람이 이미 읽고 고친 문장이 조용히 새 것으로
    덮인다 — `key in out` 스킵이 그것을 막는다. 더 나아가, **바이트 하나도
    안 바뀌어야 한다** — 사람이 파일에 남긴 주석은 이 정도로 강하게
    확인해야 "안 사라진다" 고 말할 수 있다(리뷰 Minor — `yaml.safe_dump`
    로 통째 재작성하면 히트뿐인 실행에서도 주석이 날아간다).
    """
    _고정_수준(monkeypatch, "일반")
    cue = Cue("c1", "제목", "mc", "옛 지시문", "partner", briefs=_모든_수준_브리프)
    monkeypatch.setattr(pregen, "load_cues", lambda: [cue])
    monkeypatch.setattr(pregen, "load_levels", lambda: {lvl: lvl for lvl in LEVEL_NAMES})
    key = cache_key("c1", "일반", "브리프")
    out_path = tmp_path / "mc_lines.yaml"
    원본 = f"# 사람이 손으로 확인한 문장이다 — 건드리지 마라\n{key}: 이미 고친 대사\n"
    out_path.write_text(원본, encoding="utf-8")
    _캐시_경로_고정(monkeypatch, out_path)

    calls: list[str] = []
    monkeypatch.setattr(
        pregen, "build_generate",
        lambda level: (lambda role, brief, hist: calls.append(brief) or "새 대사"),
    )

    pregen.main()

    assert calls == [], f"이미 캐시에 있는 키를 다시 생성했다: {calls}"
    assert out_path.read_text(encoding="utf-8") == 원본, (
        "캐시 히트뿐인 실행인데 파일이 바뀌었다 — 사람이 남긴 주석이 위험해진다"
    )


def test_새_항목은_기존_내용을_보존한_채_이어_붙인다(monkeypatch, tmp_path):
    """캐시 미스는 생성해서 `cache_key(cue.id, level, mc_brief)` 로 저장돼야
    한다 — 키가 틀리면 `Director._begin_cue` 가 영영 못 찾는다. 그리고
    **기존 줄(사람이 남긴 주석 포함)은 한 글자도 안 건드리고 뒤에 이어
    붙어야** 한다 — `yaml.safe_dump(전체, ...)` 로 통째 재작성하면 새
    항목 하나 때문에 기존 주석·순서가 매번 사라진다.
    """
    _고정_수준(monkeypatch, "일반")
    cue = Cue("c1", "제목", "mc", "옛 지시문", "partner", briefs=_모든_수준_브리프)
    monkeypatch.setattr(pregen, "load_cues", lambda: [cue])
    monkeypatch.setattr(pregen, "load_levels", lambda: {lvl: lvl for lvl in LEVEL_NAMES})
    out_path = tmp_path / "mc_lines.yaml"
    기존 = "# 사람이 남긴 주석 — 그대로 남아야 한다\nc0|일반|000000000000: 옛 대사\n"
    out_path.write_text(기존, encoding="utf-8")
    _캐시_경로_고정(monkeypatch, out_path)
    monkeypatch.setattr(
        pregen, "build_generate",
        lambda level: (lambda role, brief, hist: f"[{brief}] 로 만든 여는 대사"),
    )

    pregen.main()

    text = out_path.read_text(encoding="utf-8")
    assert text.startswith(기존), f"기존 줄(주석 포함)을 건드렸다:\n{text}"
    key = cache_key("c1", "일반", "브리프")
    written = yaml.safe_load(text)
    assert written[key] == "[브리프] 로 만든 여는 대사"
    assert written["c0|일반|000000000000"] == "옛 대사", "기존 항목이 사라졌다"


def test_생성_중_예외가_나도_이미_만든_항목은_파일에_남는다(monkeypatch, tmp_path):
    """76회 왕복 중 하나만 실패해도 그 전에 만든 것까지 통째로 사라지면
    사전 생성의 의미가 없다 — 건별로 즉시 파일에 이어 붙여야 한다."""
    _고정_수준(monkeypatch, "일반")
    ok_cue = Cue("c1", "성공", "mc", "옛 지시문", "partner", briefs=_모든_수준_브리프)
    boom_cue = Cue(
        "c2", "실패", "mc", "옛 지시문", "partner",
        briefs={lvl: {"mc_brief": "터지는 브리프", "docent_brief": "해설"} for lvl in LEVEL_NAMES},
    )
    monkeypatch.setattr(pregen, "load_cues", lambda: [ok_cue, boom_cue])
    monkeypatch.setattr(pregen, "load_levels", lambda: {lvl: lvl for lvl in LEVEL_NAMES})
    out_path = tmp_path / "mc_lines.yaml"
    _캐시_경로_고정(monkeypatch, out_path)

    def gen(role, brief, hist):
        if brief == "터지는 브리프":
            raise RuntimeError("추론 서버가 죽었다")
        return f"[{brief}] 로 만든 여는 대사"

    monkeypatch.setattr(pregen, "build_generate", lambda level: gen)

    with pytest.raises(RuntimeError):
        pregen.main()

    key1 = cache_key("c1", "일반", "브리프")
    written = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert written[key1] == "[브리프] 로 만든 여는 대사", (
        "c2 생성이 터졌는데 그 전에 성공한 c1 까지 사라졌다"
    )


def test_고아_키_개수를_보고한다(monkeypatch, tmp_path, capsys):
    """지금 큐시트에 없는 낡은 키가 새 항목 옆에 쌓이면 사람이 어느 줄이
    현행인지 못 가린다 — 지우지는 않되 개수는 보고해야 한다."""
    _고정_수준(monkeypatch, "일반")
    cue = Cue("c1", "제목", "mc", "옛 지시문", "partner", briefs=_모든_수준_브리프)
    monkeypatch.setattr(pregen, "load_cues", lambda: [cue])
    monkeypatch.setattr(pregen, "load_levels", lambda: {lvl: lvl for lvl in LEVEL_NAMES})
    out_path = tmp_path / "mc_lines.yaml"
    현재_키 = cache_key("c1", "일반", "브리프")
    고아_키 = "없어진_큐|일반|abcdef012345"
    out_path.write_text(
        yaml.safe_dump({현재_키: "현재 대사", 고아_키: "낡은 대사"}, allow_unicode=True),
        encoding="utf-8",
    )
    _캐시_경로_고정(monkeypatch, out_path)
    monkeypatch.setattr(pregen, "build_generate", lambda level: (lambda r, b, h: "안 씀"))

    pregen.main()

    assert "고아 1개" in capsys.readouterr().out
