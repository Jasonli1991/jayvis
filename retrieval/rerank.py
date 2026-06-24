import threading
from dataclasses import dataclass

from sentence_transformers import CrossEncoder
from retrieval.hybrid import Candidate

_MODEL_NAME = "BAAI/bge-reranker-v2-m3"
_model = None
_lock = threading.Lock()


def _get_model() -> CrossEncoder:
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                import install_manifest
                _dir = install_manifest.hf_model_dir(_MODEL_NAME)
                _pre = _dir.exists()                          # 裝之前原本就有？（有就不記、卸載不碰）
                _model = CrossEncoder(_MODEL_NAME)            # 首次會下載到 HF 快取
                try:
                    install_manifest.record_if_new("model", str(_dir), _pre, name=_MODEL_NAME)
                except Exception:
                    pass
    return _model


@dataclass
class Scored:
    cand: Candidate
    rerank_score: float


def rerank(query: str, candidates: list[Candidate], top_n: int = 5) -> list[Scored]:
    if not candidates:
        return []
    pairs = [(query, c.raw_text) for c in candidates]
    scores = _get_model().predict(pairs)
    scored = [Scored(cand=c, rerank_score=float(s)) for c, s in zip(candidates, scores)]
    scored.sort(key=lambda x: x.rerank_score, reverse=True)
    return scored[:top_n]
