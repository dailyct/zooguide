"""把 data/knowledge/*.txt 切段、向量化、寫入向量庫。

手動執行：  python -m backend.rag.ingest
"""
import glob
import os
from typing import List

from backend import config
from backend.rag import embeddings
from backend.rag.vector_store import VectorStore

MAX_CHUNK_CHARS = 300


def split_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> List[str]:
    """先依空行切成段落；太長的段落再依句號切開，並把短句合併回 max_chars 以內。"""
    chunks: List[str] = []
    for paragraph in (p.strip() for p in text.split("\n\n")):
        if not paragraph:
            continue
        if len(paragraph) <= max_chars:
            chunks.append(paragraph)
            continue
        current = ""
        for sentence in paragraph.replace("。", "。\n").split("\n"):
            sentence = sentence.strip()
            if not sentence:
                continue
            if current and len(current) + len(sentence) > max_chars:
                chunks.append(current)
                current = sentence
            else:
                current += sentence
        if current:
            chunks.append(current)
    return chunks


def build_items(knowledge_dir: str = config.KNOWLEDGE_DIR) -> List[dict]:
    """讀取知識庫，回傳尚未向量化的片段清單。檔名（不含副檔名）即動物 id。"""
    items = []
    for path in sorted(glob.glob(os.path.join(knowledge_dir, "*.txt"))):
        animal_id = os.path.splitext(os.path.basename(path))[0]
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        for i, chunk in enumerate(split_text(text)):
            items.append({"id": f"{animal_id}-{i}", "text": chunk, "metadata": {"animal_id": animal_id}})
    return items


def ingest(store: VectorStore, knowledge_dir: str = config.KNOWLEDGE_DIR) -> int:
    """重建整個向量庫，回傳片段數量。"""
    items = build_items(knowledge_dir)
    if not items:
        store.replace_all([], embeddings.embedder_name())
        return 0
    vectors = embeddings.embed_documents([it["text"] for it in items])
    for it, vec in zip(items, vectors):
        it["vector"] = vec
    store.replace_all(items, embeddings.embedder_name())
    return len(items)


if __name__ == "__main__":
    count = ingest(VectorStore(config.VECTOR_DB_PATH))
    print(f"已寫入 {count} 個知識片段 → {config.VECTOR_DB_PATH}（向量來源：{embeddings.embedder_name()}）")
