"""시스템 프롬프트 파일 선택 — 설정 사다리(환경변수 → config.json → 기본값).

실기에서 앱은 systemd 데몬의 자식이라 셸 export 가 닿지 않는다(§10). 해설 모드를
켜려면 `config.json` 에 `REACHY_PROMPT` 한 줄이면 되고 **앱 재배포가 필요 없다.**
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps/voice_chat/voice_chat"))
import config  # noqa: E402
import session  # noqa: E402

HERE = pathlib.Path(session.__file__).parent


def test_기본값은_prompt_md():
    assert session.prompt_path() == HERE / "prompt.md"


def test_설정으로_해설_프롬프트를_고른다(monkeypatch):
    monkeypatch.setattr(config, "get",
                        lambda n, d: "prompt_exhibit.md" if n == "REACHY_PROMPT" else d)
    assert session.prompt_path() == HERE / "prompt_exhibit.md"


def test_없는_파일이면_경고하고_기본값으로_되돌린다(monkeypatch, capsys):
    """조용히 폴백하면 안 된다 — 해설 모드로 켰다고 믿는데 일반 미니가 돈다."""
    monkeypatch.setattr(config, "get",
                        lambda n, d: "없는프롬프트.md" if n == "REACHY_PROMPT" else d)
    assert session.prompt_path() == HERE / "prompt.md"
    assert "없는프롬프트.md" in capsys.readouterr().out


def test_경로_탈출은_파일명만_취한다(monkeypatch):
    """config.json 은 사람이 손으로 고치는 파일이다. 오타로 앱 밖을 가리키게 두지 않는다."""
    monkeypatch.setattr(config, "get",
                        lambda n, d: "../../../etc/passwd" if n == "REACHY_PROMPT" else d)
    assert session.prompt_path() == HERE / "prompt.md"


def test_해설_프롬프트가_실제로_있고_상한을_넘지_않는다():
    """프롬프트가 부풀면 **예열을 빠뜨렸을 때** 첫 발화가 그만큼 늦는다.

    실측(2026-09-09, gemma4:e4b): 예열 후에는 352토큰이든 9409토큰이든 0.08~0.10s 로
    같지만, 예열이 빠지면 352→0.33s / 3305→2.51s / 9409→8.23s 로 벌어진다.
    상한을 두어 그 꼬리 위험을 묶어 둔다. 한국어는 대략 1.57자/토큰이다.
    """
    p = HERE / "prompt_exhibit.md"
    assert p.exists()
    n = len(p.read_text(encoding="utf-8"))
    assert n <= 4800, f"해설 프롬프트가 상한을 넘었다: {n}자 (약 {n/1.57:.0f}토큰)"
