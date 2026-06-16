from retrieval.hybrid import Candidate
from retrieval.rerank import rerank


def _c(id, text):
    return Candidate(id=id, raw_text=text, source_type="obsidian", rrf_score=0.0, meta={})


def test_rerank_puts_relevant_first():
    cands = [
        _c("irrelevant", "午餐菜單與天氣"),
        _c("relevant", "projy 改用 pgvector 做向量檢索的原因"),
    ]
    out = rerank("為什麼 projy 用 pgvector", cands, top_n=2)
    assert out[0].cand.id == "relevant"
    assert out[0].rerank_score >= out[1].rerank_score
