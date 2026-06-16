import os
import hashlib
import chromadb
from chromadb.utils import embedding_functions
from config import OBSIDIAN_PATH, CHROMA_PATH

# 只索引這些資料夾（排除 Raw/Inbox 未處理素材）
INCLUDE_DIRS = [
    "01_Wiki",
    "02_Outputs/Projects",
    "02_Outputs/Q&A",
    "03_Meta/Prompts",
    "04_Archive/Projects",
]

CHUNK_SIZE = 800    # chars
CHUNK_OVERLAP = 100


def _get_client():
    os.makedirs(CHROMA_PATH, exist_ok=True)
    return chromadb.PersistentClient(path=CHROMA_PATH)


def _get_collection(client):
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    return client.get_or_create_collection("knowledge_base", embedding_function=ef)


def _chunk(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _file_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def build_index():
    """掃描 Obsidian vault，將所有 markdown 向量化存入 ChromaDB。"""
    client = _get_client()
    col = _get_collection(client)

    indexed, skipped = 0, 0

    for include_dir in INCLUDE_DIRS:
        target = os.path.join(OBSIDIAN_PATH, include_dir)
        if not os.path.exists(target):
            continue

        for root, _, files in os.walk(target):
            for fname in files:
                if not fname.endswith(".md"):
                    continue

                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, OBSIDIAN_PATH)
                file_hash = _file_hash(fpath)

                with open(fpath, encoding="utf-8") as f:
                    text = f.read()

                chunks = _chunk(text)

                for i, chunk in enumerate(chunks):
                    doc_id = f"{rel_path}::chunk{i}"

                    # 若內容未變，跳過
                    existing = col.get(ids=[doc_id])
                    if existing["ids"] and existing["metadatas"][0].get("hash") == file_hash:
                        skipped += 1
                        continue

                    col.upsert(
                        ids=[doc_id],
                        documents=[chunk],
                        metadatas=[{"source": rel_path, "hash": file_hash, "chunk": i}],
                    )
                    indexed += 1

    print(f"索引完成：新增/更新 {indexed} 筆，跳過 {skipped} 筆（未變更）")


if __name__ == "__main__":
    build_index()
