"""Hybrid retrieval over the unified knowledge base - domain-agnostic.

Two kinds of documents are indexed: unified items, and standalone notes
(shop-wide policies belong to no single item). Scoring blends TF-IDF
cosine similarity with raw token overlap - robust for short mixed-language
queries - plus a deterministic exact-ID path: numbers and codes are where
fuzzy search is least trustworthy, so "F-101" or "KB-118" always wins
exactly. Swapping TF-IDF for a real embedding model is a two-line change.
"""

import re
from dataclasses import dataclass
from typing import List

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class Hit:
    kind: str      # "product" | "note"
    ref: dict
    score: float


def _searchable(p: dict) -> str:
    parts = [p.get("canonical_name") or ""]
    parts += [str(v) for v in (p.get("attributes") or {}).values() if v]
    parts += [p.get("quality_note") or "", p.get("moq_note") or ""]
    for s in p.get("sources", []):
        if s.get("source") == "posts":
            parts.append(s.get("fields", {}).get("title", ""))
            parts.append(s.get("text", ""))
    return " ".join(x for x in parts if x)


class HybridIndex:
    def __init__(self, products: List[dict], notes: List[dict]):
        self.docs = [("product", p, _searchable(p)) for p in products]
        self.docs += [("note", n, n["text"]) for n in notes]
        self.texts = [d[2] for d in self.docs]
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self.matrix = self.vectorizer.fit_transform(self.texts)
        # precomputed once: re-tokenizing 10k+ docs on every query is wasteful
        self.doc_tokens = [set(re.findall(r"[a-z0-9]+", t.lower())) for t in self.texts]
        self.pids = [str(ref.get("product_id", "")).lower() if kind == "product" else ""
                     for kind, ref, _ in self.docs]

    def search(self, query: str, k: int = 3) -> List[Hit]:
        q_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
        cos = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]

        ql = query.lower()
        hits = []
        for idx, (kind, ref, text) in enumerate(self.docs):
            overlap = len(q_tokens & self.doc_tokens[idx]) / max(len(q_tokens), 1)
            score = 0.7 * cos[idx] + 0.3 * overlap
            if kind == "note":
                score *= 0.9   # items are the canonical answer surface
            elif self.pids[idx] and self.pids[idx] in ql:
                score = 1.0
            hits.append(Hit(kind=kind, ref=ref, score=round(float(score), 4)))

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]
