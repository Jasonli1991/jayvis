import math
from embeddings import embed_query, embed_texts, EMBED_DIM


def test_embed_query_dim_and_normalized():
    v = embed_query("projy 用 pgvector")
    assert len(v) == EMBED_DIM == 1024
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 1e-2  # L2 normalized


def test_semantic_closer_than_unrelated():
    q = embed_query("如何用向量資料庫做檢索")
    near = embed_query("pgvector 向量相似度搜尋")
    far = embed_query("今天午餐吃什麼")
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    assert dot(q, near) > dot(q, far)
