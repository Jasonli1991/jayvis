import os
from dataclasses import dataclass, field

from retrieval.hybrid import hybrid_search
from retrieval.rerank import rerank
from retrieval.confidence import decide
from chunks import citation_of
import obsidian_graph


# KB 問答排除的 source_type：對話/動作記憶走另一條 recall，不混進 KB 檢索。
# 其餘 source_type（obsidian / git / manual 自我說明…）都可被 KB 問答撈到。
KB_EXCLUDE_SOURCE_TYPES = ("conversation", "action")


@dataclass
class RetrievalResult:
    abstain: bool
    context: str
    citations: list[str]
    reason: str
    source_types: list[str] = field(default_factory=list)


def _citation_for_scored(s) -> str:
    m = s.cand.meta
    fake = {"source_type": s.cand.source_type, **m}
    return citation_of(fake)


def answer_context(conn, query: str, owner: str = "owner", expand_graph: bool = False) -> RetrievalResult:
    threshold = float(os.environ.get("RETRIEVAL_THRESHOLD", "0.3"))
    candidates = hybrid_search(conn, query, owner=owner, out_k=20,
                               exclude_source_types=KB_EXCLUDE_SOURCE_TYPES)
    scored = rerank(query, candidates, top_n=5)
    decision = decide(scored, threshold=threshold)
    if decision.abstain:
        return RetrievalResult(abstain=True, context="", citations=[], reason=decision.reason, source_types=[])
    blocks, citations = [], []
    for s in decision.top:
        cite = _citation_for_scored(s)
        citations.append(cite)
        blocks.append(f"[來源：{cite}]\n{s.cand.raw_text}")
    context = "\n\n---\n\n".join(blocks)
    if expand_graph:
        matched = [s.cand.meta.get("doc_path") for s in decision.top
                   if s.cand.source_type == "obsidian" and s.cand.meta.get("doc_path")]
        if matched:
            extra = obsidian_graph.expand_context(conn, matched)
            if extra:
                context = context + "\n\n---\n\n" + extra
    return RetrievalResult(
        abstain=False, context=context, citations=citations, reason="ok",
        source_types=[s.cand.source_type for s in decision.top])
