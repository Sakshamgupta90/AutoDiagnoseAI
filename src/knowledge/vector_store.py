"""Chroma-backed knowledge base.

Two collections:
- `knowledge`: the Zenodo dataset records and flowchart decision steps (trusted).
- `learned`:   what the workshop learns over time. Answers Claude gave without a
               knowledge-base match are stored as `unverified`; fixes confirmed by a
               technician on job close are stored as `confirmed`.

Embeddings use Chroma's built-in local model (all-MiniLM-L6-v2 via ONNX): free,
offline, and still available when Bedrock is unreachable.
"""

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from src.core.config import settings

logger = logging.getLogger(__name__)

KNOWLEDGE = "knowledge"
LEARNED = "learned"

# Fixes confirmed by the workshop's own technicians are the most specific evidence, so they rank
# above generic dataset entries; unverified answers rank below trusted knowledge.
TRUST_WEIGHT = {"verified": 1.0, "confirmed": 1.15, "unverified": 0.85}


@dataclass
class Hit:
    id: str
    text: str
    similarity: float
    collection: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def trust(self) -> str:
        return self.metadata.get("trust", "verified")

    @property
    def score(self) -> float:
        return self.similarity * TRUST_WEIGHT.get(self.trust, 1.0)

    @property
    def source(self) -> str:
        return self.metadata.get("source", "Knowledge base")

    @property
    def category(self) -> str:
        return self.metadata.get("category", "")

    def as_tool_result(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "trust": self.trust,
            "category": self.category,
            "similarity": round(self.similarity, 3),
            "text": self.text,
        }


class VectorStore:
    def __init__(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(path))
        self._ef = DefaultEmbeddingFunction()
        self._lock = threading.Lock()
        self.knowledge = self._collection(KNOWLEDGE)
        self.learned = self._collection(LEARNED)

    def _collection(self, name: str):
        return self._client.get_or_create_collection(
            name=name, embedding_function=self._ef, metadata={"hnsw:space": "cosine"}
        )

    # ---------- writes ----------

    def upsert(self, collection: str, ids: list[str], texts: list[str], metadatas: list[dict[str, Any]]) -> None:
        with self._lock:
            self._get(collection).upsert(ids=ids, documents=texts, metadatas=metadatas)

    def delete(self, collection: str, ids: list[str]) -> None:
        with self._lock:
            self._get(collection).delete(ids=ids)

    def _get(self, collection: str):
        return self.knowledge if collection == KNOWLEDGE else self.learned

    # ---------- reads ----------

    def search(self, query: str, top_k: int | None = None, category: str | None = None) -> list[Hit]:
        """Semantic search over both collections, ranked by trust-weighted similarity."""
        top_k = top_k or settings.SEARCH_TOP_K
        hits: list[Hit] = []
        for name, coll in ((KNOWLEDGE, self.knowledge), (LEARNED, self.learned)):
            count = coll.count()
            if not count:
                continue
            where = {"category": category} if category and name == KNOWLEDGE else None
            with self._lock:
                res = coll.query(query_texts=[query], n_results=min(top_k, count), where=where)
            for i, doc_id in enumerate(res["ids"][0]):
                hits.append(
                    Hit(
                        id=doc_id,
                        text=res["documents"][0][i],
                        similarity=max(0.0, 1.0 - float(res["distances"][0][i])),
                        collection=name,
                        metadata=res["metadatas"][0][i] or {},
                    )
                )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    def related(self, hit: Hit, limit: int = 6) -> list[Hit]:
        """Graph-style expansion: the rest of a flowchart's decision path for a flowchart hit."""
        flowchart = hit.metadata.get("flowchart")
        if not flowchart:
            return []
        with self._lock:
            res = self.knowledge.get(where={"flowchart": flowchart}, limit=limit)
        nodes = [
            Hit(id=i, text=d, similarity=hit.similarity, collection=KNOWLEDGE, metadata=m or {})
            for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])
            if i != hit.id
        ]
        return sorted(nodes, key=lambda h: h.metadata.get("order", 0))

    def counts(self) -> dict[str, int]:
        learned = self.learned.get(include=["metadatas"])
        trusts = [m.get("trust") for m in learned["metadatas"] or []]
        return {
            "knowledge": self.knowledge.count(),
            "learned_unverified": trusts.count("unverified"),
            "learned_confirmed": trusts.count("confirmed"),
        }


_store: VectorStore | None = None
_store_lock = threading.Lock()


def get_store(path: Path | None = None) -> VectorStore:
    global _store
    with _store_lock:
        if _store is None or path is not None:
            _store = VectorStore(Path(path or settings.CHROMA_DIR))
        return _store
