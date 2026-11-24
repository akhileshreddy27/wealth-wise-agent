"""Knowledge base for the RAG chatbot, built from the learning modules.

Each lesson (`content/*.md`) is split at its `## ` headings into chunks. Search is hybrid:
- BM25 keyword search, which always works and needs no API key;
- semantic search with Gemini embeddings (when a key is set), cached in `data/embeddings.json`
  and rebuilt automatically when the lessons change.
The two rankings are merged with reciprocal rank fusion (RRF).
"""
import hashlib
import json
import logging
import math
import re
import threading
from collections import Counter
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from wealthwise.config import DATA_DIR, settings

log = logging.getLogger(__name__)
CONTENT_DIR = Path(__file__).resolve().parent / "content"
EMBEDDINGS_FILE = DATA_DIR / "embeddings.json"


@dataclass
class Chunk:
    id: str            # "<module>#<section-slug>"
    module_id: str
    module_title: str
    section: str
    text: str


# ---------- lessons ----------

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@lru_cache
def load_modules() -> list[dict]:
    """modules.json metadata plus each lesson's title and markdown."""
    meta = json.loads((CONTENT_DIR / "modules.json").read_text(encoding="utf-8"))["modules"]
    modules = []
    for mod in meta:
        markdown = (CONTENT_DIR / mod["file"]).read_text(encoding="utf-8")
        title = markdown.splitlines()[0].lstrip("# ").strip()
        modules.append({**mod, "title": title, "markdown": markdown})
    return modules


def chunk_lessons(modules: list[dict]) -> list[Chunk]:
    chunks = []
    for mod in modules:
        for block in re.split(r"^## ", mod["markdown"], flags=re.M)[1:]:
            section, _, body = block.partition("\n")
            chunks.append(Chunk(f"{mod['id']}#{slugify(section)}", mod["id"], mod["title"],
                                section.strip(), body.strip()))
    return chunks


# ---------- BM25 ----------

STOPWORDS = set("a an and are as at be by can do does for from how i if in is it its me my of on or should so "
                "than that the their this to was what when where which who why will with you your".split())


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.docs = [Counter(tokenize(d)) for d in docs]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_len = sum(self.lengths) / max(len(self.docs), 1)
        df = Counter(term for d in self.docs for term in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.k1, self.b = k1, b

    def scores(self, query: str) -> list[float]:
        terms = tokenize(query)
        out = []
        for doc, length in zip(self.docs, self.lengths):
            s = 0.0
            for t in terms:
                if t in doc:
                    tf = doc[t]
                    s += self.idf[t] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * length / self.avg_len))
            out.append(s)
        return out


# ---------- the knowledge base ----------

def rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    """Reciprocal rank fusion: items ranked high by any ranking float to the top."""
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            fused[idx] = fused.get(idx, 0.0) + 1 / (k + rank + 1)
    return fused


class KnowledgeBase:
    def __init__(self, chunks: list[Chunk], embed=None):
        """`embed(texts, task) -> list[vector]`; None means keyword search only."""
        self.chunks = chunks
        self.bm25 = BM25([f"{c.module_title} {c.section} {c.text}" for c in chunks])
        self.embed = embed
        self.vectors = self._load_vectors() if embed else None

    def _content_hash(self) -> str:
        joined = "\n".join(f"{c.id}\n{c.text}" for c in self.chunks) + settings.embedding_model
        return hashlib.sha256(joined.encode()).hexdigest()[:16]

    def _load_vectors(self) -> np.ndarray | None:
        key = self._content_hash()
        try:
            if EMBEDDINGS_FILE.exists():
                cached = json.loads(EMBEDDINGS_FILE.read_text())
                if cached.get("hash") == key:
                    return np.array(cached["vectors"], dtype=np.float32)
            texts = [f"{c.module_title}: {c.section}\n{c.text}" for c in self.chunks]
            vectors = self.embed(texts, "RETRIEVAL_DOCUMENT")
            EMBEDDINGS_FILE.write_text(json.dumps({"hash": key, "vectors": vectors}))
            return _normalise(np.array(vectors, dtype=np.float32))
        except Exception as e:  # no network, quota hit, bad key: fall back to keywords
            log.warning("Embeddings unavailable, using keyword search only: %s", e)
            return None

    @property
    def mode(self) -> str:
        return "hybrid" if self.vectors is not None else "keyword"

    def search(self, query: str, k: int = 4) -> list[dict]:
        bm25 = self.bm25.scores(query)
        rankings = [[i for i in sorted(range(len(bm25)), key=lambda i: -bm25[i]) if bm25[i] > 0][:20]]
        if self.vectors is not None:
            try:
                q = _normalise(np.array(self.embed([query], "RETRIEVAL_QUERY")[0], dtype=np.float32))
                sims = _normalise(self.vectors) @ q
                rankings.append([int(i) for i in np.argsort(-sims)[:20]])
            except Exception as e:
                log.warning("Query embedding failed, keyword search only: %s", e)
        fused = rrf(rankings)
        best = sorted(fused, key=lambda i: -fused[i])[:k]
        return [{**asdict(self.chunks[i]), "score": round(fused[i], 4)} for i in best]


def _normalise(v: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(norms == 0, 1, norms)


_kb_lock = threading.Lock()


def get_knowledge_base() -> KnowledgeBase:
    """Built once (embedding the lessons on first use); the lock stops two requests building it twice."""
    with _kb_lock:
        return _build_knowledge_base()


@lru_cache
def _build_knowledge_base() -> KnowledgeBase:
    from wealthwise.ai.gemini import embed  # imported here so the knowledge base works without the AI layer

    return KnowledgeBase(chunk_lessons(load_modules()), embed if settings.ai_enabled else None)
