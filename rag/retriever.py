from db.connection import get_conn
from retrieval.orchestrator import answer_context, RetrievalResult


def _open_conn():
    return get_conn()


def retrieve_result(query: str, expand_graph: bool = False) -> RetrievalResult:
    conn = _open_conn()
    try:
        return answer_context(conn, query, expand_graph=expand_graph)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def retrieve(query: str, top_k: int = 5) -> str:
    """Backward-compatible: returns formatted context string ('' when abstaining)."""
    return retrieve_result(query).context
