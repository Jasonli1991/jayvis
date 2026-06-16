from dataclasses import dataclass
from retrieval.rerank import Scored


@dataclass
class Decision:
    abstain: bool
    top: list[Scored]
    reason: str


def decide(scored: list[Scored], threshold: float = 0.3) -> Decision:
    if not scored:
        return Decision(abstain=True, top=[], reason="no_candidates")
    top_score = scored[0].rerank_score
    if top_score < threshold:
        return Decision(abstain=True, top=scored,
                        reason=f"top_score {top_score:.3f} < {threshold}")
    kept = [s for s in scored if s.rerank_score >= threshold] or scored[:1]
    return Decision(abstain=False, top=kept, reason="ok")
