import config
from db.connection import get_conn
from retrieval.hybrid import hybrid_search
from chunks import citation_of
from llm import generate

_SYSTEM = (
    f"你是 {config.OWNER_NAME} 的分析助理。根據提供的『筆記/commit 片段』綜合回答問題，"
    "可做合理推論與彙整，但**必須明確標註依據**，並說明資料不足或不確定之處；"
    "**不要編造超出所給資料的事實**。用繁體中文、結構化（重點條列）。"
)


def _open_conn():
    return get_conn()


def _source_label(c) -> str:
    return citation_of({"source_type": c.source_type, **c.meta})


def analyze(query: str, owner: str = None, model: str = None,
            k: int = 40, max_context: int = 24000) -> dict:
    owner = owner or config.OWNER_KEY
    model = model or config.MODEL_CODE
    conn = _open_conn()
    try:
        cands = hybrid_search(conn, query, owner=owner, out_k=k)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not cands:
        return {"answer": "找不到相關資料，無法分析。", "sources": []}

    blocks, sources, total = [], [], 0
    for c in cands:
        label = _source_label(c)
        piece = f"[{label}]\n{c.raw_text}"
        if total + len(piece) > max_context:
            break
        blocks.append(piece)
        sources.append(label)
        total += len(piece)

    context = "\n\n---\n\n".join(blocks)
    answer = generate(
        model=model,
        system=_SYSTEM,
        messages=[{"role": "user", "content": f"分析問題：{query}\n\n可用資料：\n{context}"}],
        max_output_tokens=4096,
    )
    return {"answer": answer, "sources": sources}
