"""종이 무대 교육자료(`scripts/handout_paper`) — 틀·장면 코드의 불변식. 브라우저 없이 도는 것만 둔다.

화면 확인은 `docs/design/paper-stage.html?cue=NN&t=초`(한 순간 멈춤)와 `?check=1`(19장을 모두 지어 '대사에 없는 낱말'
경고를 body[data-warn] 에 적는다)로 한다.
"""
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAPER = ROOT / "scripts" / "handout_paper"


def test_모든_큐에_장면이_있다():
    # 장면이 없는 큐는 로봇·카드만 나온 채 조용히 지나간다 — 큐를 늘리면 여기서 걸린다.
    ids = [c["id"] for c in yaml.safe_load((ROOT / "data" / "cues.yaml").read_text())]
    have = set(re.findall(r"SC\['([^']+)'\]\s*=", (PAPER / "scenes.js").read_text()))
    assert [i for i in ids if i not in have] == []


def test_틀과_장면은_외부_리소스를_부르지_않는다():
    # 전시장은 오프라인이다. 주석의 출처 링크 말고는 http 주소가 없어야 한다.
    for name in ("template.html", "scenes.js"):
        src = re.sub(r"<!--.*?-->", "", (PAPER / name).read_text(), flags=re.S)
        assert not re.search(r"""(src|href)\s*=\s*["']https?:|url\(\s*["']?https?:|import\s""", src), name


def test_글자는_캔버스에_그리지_않는다():
    # 화면의 글은 DOM textContent 로만 넣는다(검증된 카드·대사 그대로 — innerHTML·fillText 금지).
    for name in ("template.html", "scenes.js"):
        src = (PAPER / name).read_text()
        assert "innerHTML" not in src and "fillText" not in src, name


def test_빌더는_캐시와_큐시트가_다르면_멈춘다():
    # 조용히 빠진 채 만들지 않는다 — 대조 줄이 사라지면 뒤집힌 문장이 그대로 들어간다(docs/lessons.md).
    src = (PAPER / "build.py").read_text()
    assert "sys.exit" in src and "got.sort(" in src
