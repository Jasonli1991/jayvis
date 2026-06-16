from retrieval.hybrid import Candidate
from retrieval.rerank import Scored
from retrieval.confidence import decide


def _s(score):
    return Scored(cand=Candidate("x", "t", "obsidian", 0.0, {}), rerank_score=score)


def test_abstain_when_empty():
    d = decide([], threshold=0.3)
    assert d.abstain is True


def test_abstain_when_top_below_threshold():
    d = decide([_s(0.1), _s(0.05)], threshold=0.3)
    assert d.abstain is True


def test_answer_when_top_above_threshold():
    d = decide([_s(0.9), _s(0.2)], threshold=0.3)
    assert d.abstain is False
    assert d.top[0].rerank_score == 0.9
