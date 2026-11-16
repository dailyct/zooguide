import json
import os

from backend import config
from backend.rag import embeddings, ingest, retriever
from backend.rag.vector_store import VectorStore


def test_split_text_keeps_short_paragraphs_and_splits_long_ones():
    assert ingest.split_text("第一段。\n\n第二段。") == ["第一段。", "第二段。"]
    long_paragraph = "這是一個句子。" * 100
    chunks = ingest.split_text(long_paragraph, max_chars=50)
    assert len(chunks) > 1
    assert all(len(c) <= 50 for c in chunks)
    assert "".join(chunks) == long_paragraph


def test_split_text_ignores_blank_input():
    assert ingest.split_text("") == []
    assert ingest.split_text("\n\n  \n\n") == []


def test_build_items_covers_every_knowledge_file():
    items = ingest.build_items()
    animal_ids = {it["metadata"]["animal_id"] for it in items}
    files = {f[:-4] for f in os.listdir(config.KNOWLEDGE_DIR) if f.endswith(".txt")}
    assert animal_ids == files
    assert len({it["id"] for it in items}) == len(items), "片段 id 不能重複"


def test_local_embedding_is_normalized_and_deterministic():
    a = embeddings.embed_query("老虎為什麼有條紋")
    b = embeddings.embed_query("老虎為什麼有條紋")
    assert a == b
    assert abs(sum(v * v for v in a) - 1.0) < 1e-9
    assert embeddings.embedder_name().startswith("local-hash")


def test_retrieve_finds_the_right_animal_without_a_filter():
    cases = {
      "老虎為什麼有條紋？": "tiger",
      "雄獅的鬃毛有什麼用？": "lion",
      "貓熊都吃什麼？": "panda",
      "大象的鼻子可以做什麼？": "elephant",
      "企鵝怎麼孵蛋？": "penguin",
      "獼猴為什麼互相梳毛？": "monkey",
    }
    for question, expected in cases.items():
        top = retriever.retrieve(question, k=1)[0]
        assert top["metadata"]["animal_id"] == expected, question


def test_retrieve_respects_animal_filter():
    results = retriever.retrieve("牠們吃什麼？", k=5, animal_id="panda")
    assert results
    assert all(r["metadata"]["animal_id"] == "panda" for r in results)
    assert retriever.retrieve("anything", animal_id="no-such-animal") == []


def test_vector_store_persists_and_survives_a_corrupt_file(tmp_path):
    path = str(tmp_path / "store.json")
    store = VectorStore(path)
    store.replace_all([{"id": "a", "text": "hello", "vector": [1.0, 0.0], "metadata": {"animal_id": "x"}}], "test")
    reloaded = VectorStore(path)
    assert len(reloaded) == 1 and reloaded.embedder == "test"

    with open(path, "w", encoding="utf-8") as f:
        f.write("{ not json")
    assert len(VectorStore(path)) == 0


def test_vector_store_skips_vectors_of_a_different_dimension():
    store = VectorStore(os.path.join(config.VECTOR_DB_PATH + ".unused"))
    store.items = [{"id": "a", "text": "t", "vector": [1.0, 0.0, 0.0], "metadata": {}}]
    assert store.search([1.0, 0.0], k=3) == []


def test_store_is_rebuilt_when_the_embedder_changes():
    store = retriever.get_store()
    original = len(store)
    assert original > 0
    store.replace_all(store.items[:1], "some-other-embedder")
    retriever.reset()
    assert len(retriever.get_store()) == original  # 向量來源不同 → 自動重建

    with open(config.VECTOR_DB_PATH, encoding="utf-8") as f:
        assert json.load(f)["embedder"] == embeddings.embedder_name()
