import os
import threading

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from sentence_transformers import SentenceTransformer

EMBED_DIM = 1024
_MODEL_NAME = "BAAI/bge-m3"
_model = None
_lock = threading.Lock()


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                import install_manifest
                _dir = install_manifest.hf_model_dir(_MODEL_NAME)
                _pre = _dir.exists()                          # 裝之前原本就有？（有就不記、卸載不碰）
                _model = SentenceTransformer(_MODEL_NAME)     # 首次會下載到 HF 快取
                try:
                    install_manifest.record_if_new("model", str(_dir), _pre, name=_MODEL_NAME)
                except Exception:
                    pass
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    vecs = _get_model().encode(
        texts, normalize_embeddings=True, batch_size=16, show_progress_bar=False
    )
    return [v.tolist() for v in vecs]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
