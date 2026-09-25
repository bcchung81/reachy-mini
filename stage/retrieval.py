"""관람객 질문과 가장 가까운 **다른** 섹션 찾기 — 질문 답의 근거를 큐시트 전체로 넓힌다.

왜 필요한가(2026-09-24): 관람객 질문 답의 근거가 **지금 섹션의 브리프 하나**뿐이었다.
관람객은 앞에서 들은 것을 되묻는다("아까 마르코니가 누구라고 했죠?"). 근거에 없으면 모델은
일반 지식으로 채우거나 "모른다" 로 물러난다 — 소형 LLM 은 사전 지식이 얇아 앞쪽이 환각이 된다.
서울의 박물관 세 곳에 배치된 sLLM 도슨트 연구도 전 해설 코퍼스 검색(RAG)을 기본으로 두고,
한계로 "배경지식이 부족하면 답의 충실도가 떨어진다" 를 들었다(docs/lessons.md 해당 항목).

왜 벡터 DB 가 아닌가: 큐가 19개다. 임베딩 모델·인덱스·서버를 더하면 실패 경로만 는다.
**글자 2-gram 겹침에 IDF 가중**이면 고유명사("마르코니", "타이타닉", "테레민")가 알아서 무겁고
흔한 말끝("예요", "나요")은 가볍다. 결정적이라 테스트가 리터럴로 선다.

원칙: **지금 섹션보다 확실히 더 가까울 때만** 다른 섹션을 붙이고, 붙여도 **하나만**이다.
엉뚱한 근거는 없는 근거보다 나쁘다 — 모델이 그것을 답에 섞는다.

단독 모드(2026-09-25, `nearest`)는 규칙이 다르다 — 지금 섹션이라는 기본 근거가 없어서 근거를 놓치면 곧바로
"모른다" 나 환각이 된다. 둘까지 주고 문턱을 조금 낮췄다(근거와 수치는 `nearest` docstring).
"""

import math
import re

from stage.cues import Cue

# 다른 섹션을 근거로 붙일 최소 점수 — **"한 섹션에만 나오는 2-gram 몇 개 분량"** 으로 잡는다.
# 그런 2-gram 하나의 IDF 가 log(N) 이라 문턱은 `MIN_RARE_GRAMS × log(N)` 이다.
# ~~절대값 4.0~~ 으로 두었더니 IDF 가 큐 수에 따라 변해서, 큐가 적은 시트(짧은 코스·테스트의
# 2큐)에서는 고유명사가 네 번 겹쳐도 문턱을 못 넘었다 — 검색이 조용히 영영 안 켜진다.
# 1.5 개 분량이면 19큐에서 약 4.4점: 흔한 말끝만 겹치는 질문("그건 왜 그런가요?" 2.3점)은
# 떨어지고 고유명사 질문("마르코니가 누구…" 11.9점)은 넘는다(`tests/test_stage_retrieval.py`).
MIN_RARE_GRAMS = 1.5
# 단독 모드의 근거 검색(`CueIndex.nearest`) — 규칙과 수치의 근거는 그 docstring 에 있다(실측 2026-09-25).
MIN_RARE_GRAMS_SOLO = 1.25
SOLO_MAX_SECTIONS = 2
SOLO_SECOND_MIN_SHARE = 0.5

_KEEP = re.compile(r"[0-9A-Za-z가-힣]+")


def _grams(text: str) -> set[str]:
    """글자 2-gram 집합. 띄어쓰기를 무시하려고 낱말을 붙인 뒤 자른다 — STT 는 띄어쓰기가 흔들린다."""
    s = "".join(_KEEP.findall(text.lower()))
    return {s[i : i + 2] for i in range(len(s) - 1)}


def _cue_text(cue: Cue, level: str) -> str:
    """그 섹션이 **그 수준에서** 말한 것과 확인된 근거 — 관람객이 되물을 수 있는 전부."""
    _, brief = cue.brief_for(level)
    parts = [cue.title, cue.topic, cue.mc, cue.mc_after, brief]
    for p in cue.points_for(level):
        parts += [p.ask, p.answer]
    return " ".join(x for x in parts if x)


class CueIndex:
    """수준별 2-gram 색인. 큐시트는 기동 뒤 안 바뀌므로 수준마다 한 번만 만든다."""

    def __init__(self, cues: tuple[Cue, ...]) -> None:
        self._cues = cues
        self._by_level: dict[str, tuple[list[set[str]], dict[str, float]]] = {}

    def _index(self, level: str):
        if level not in self._by_level:
            docs = [_grams(_cue_text(c, level)) for c in self._cues]
            n = len(docs)
            df: dict[str, int] = {}
            for d in docs:
                for g in d:
                    df[g] = df.get(g, 0) + 1
            idf = {g: math.log(n / k) for g, k in df.items()}
            self._by_level[level] = (docs, idf)
        return self._by_level[level]

    def scores(self, question: str, level: str) -> list[float]:
        docs, idf = self._index(level)
        q = _grams(question)
        return [sum(idf.get(g, 0.0) for g in q & d) for d in docs]

    def _threshold(self, rare_grams: float = MIN_RARE_GRAMS) -> float:
        return rare_grams * math.log(len(self._cues)) if len(self._cues) > 1 else math.inf

    def nearest(self, question: str, level: str) -> list[Cue]:
        """큐시트 **전체**에서 질문에 가까운 섹션 — 많아야 `SOLO_MAX_SECTIONS` 개, 가까운 순.

        단독 모드(2026-09-25)의 근거다. 거기에는 "지금 섹션" 이 없다 — 사회자가 혼자 관람객 말을 받으므로
        무엇을 물을지 모른다. `related`(하나, 지금 섹션보다 확실히 가까울 때만)와 규칙이 다른 이유는 실측이다
        (`tests/test_stage_retrieval.py` 의 단독 재현율 묶음, 28문항):

        - **하나만 주면 엉뚱한 섹션이 잦다** — "헤르츠가 뭐예요?" 가 헤르츠 실험을 체험하는 모스 섹션으로,
          "1세대 이동통신은 언제예요?" 가 사물인터넷으로 갔다(맞음 21/28). 둘째까지 주면 정답이 근거 안에
          드는 것이 26/28 이다. 둘째는 첫째 점수의 `SOLO_SECOND_MIN_SHARE` 이상일 때만 — 멀리 떨어진
          둘째는 근거가 아니라 소음이다.
        - **문턱을 조금 낮춘다**(`MIN_RARE_GRAMS_SOLO`). "전자파는 몸에 해로워요?"(4.3점)가 1.5 개 분량
          문턱(4.4점) 바로 아래라 근거 없이 "모른다" 로 답했다. 인사말 오탐은 늘지만 지시문이 걸러 낸다
          (`Director._solo_brief`) — 근거는 전부 검수한 브리프라 섞여도 사실이 틀리지 않고, 놓치면 환각이나
          "모른다" 가 된다(교훈 대장 「글자 2-gram 검색은 사회자 인사말에도 걸린다」).

        동점이면 앞 섹션이 먼저다(결정적).
        """
        scores = self.scores(question, level)
        if not scores:
            return []
        threshold = self._threshold(MIN_RARE_GRAMS_SOLO)
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        out: list[Cue] = []
        for i in order[:SOLO_MAX_SECTIONS]:
            if scores[i] < threshold:
                break
            if out and scores[i] < SOLO_SECOND_MIN_SHARE * scores[order[0]]:
                break
            out.append(self._cues[i])
        return out

    def related(self, question: str, level: str, current_id: str) -> Cue | None:
        """지금 섹션보다 질문에 **확실히 더 가까운** 다른 섹션 하나. 없으면 None."""
        scores = self.scores(question, level)
        cur = next((i for i, c in enumerate(self._cues) if c.id == current_id), None)
        cur_score = scores[cur] if cur is not None else 0.0
        best, best_score = None, 0.0
        for i, (c, s) in enumerate(zip(self._cues, scores)):
            if c.id == current_id:
                continue
            if s > best_score:
                best, best_score = c, s
        if best is None or best_score < self._threshold() or best_score <= cur_score:
            return None
        return best
