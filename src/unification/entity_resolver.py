"""Entity resolution across sources - the core of this project.

The same real-world item appears under different names in each source
(table id "KB-204" vs post title "kurti blue georgette 01"; or for a
furniture store, "F-101" vs "teak coffee table new stock"). We merge
them into one canonical record without wrongly merging two different
items - across ANY business domain, because matching works on the text
of the records, not on hardcoded fields.

  1. Table rows anchor the process (most reliable structure).
  2. For each row, find candidate posts via a similarity score blending
     TF-IDF cosine similarity with fuzzy string matching.
  3. Auto-merge above a high-confidence threshold; grey-zone merges are
     kept but flagged `needs_review` so the answer layer hedges.
  4. Notes attach to their best-matching item(s) - they carry pricing
     rules, quality flags and stock warnings that live nowhere else.
  5. Unmatched posts become their own records marked "not in the table".

Runs offline on scikit-learn. `llm_confirm_merge` is the hook where an
LLM double-checks borderline merges when ANTHROPIC_API_KEY is set.
"""

import difflib
import os

import numpy as np
from datetime import datetime
from typing import List, Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.schema import RawRecord, UnifiedProduct

AUTO_MERGE_THRESHOLD = 0.55
REVIEW_THRESHOLD = 0.35
NOTE_ATTACH_THRESHOLD = 0.20
VARIANT_HINTS = ("color", "colour", "variant", "shade", "model", "finish", "flavour", "size")


def _top_candidates(texts_a: List[str], texts_b: List[str], k: int = 3):
    """Scalable candidate matching via blocking.

    Instead of a dense NxM matrix with fuzzy matching on every pair
    (O(N*M) slow string ops, gigabytes of memory at 10k x 10k), we:
      1. compute sparse TF-IDF cosine scores in row chunks (fast, low memory),
      2. take only the top-k candidates per row,
      3. run the expensive difflib fuzzy refinement on those k pairs only.
    This is the standard blocking / candidate-generation pattern from
    production entity-resolution systems, and takes the pipeline from
    "hours at 10k rows" to "seconds".
    Returns, per row of texts_a: a list of (index_in_b, blended_score),
    best first."""
    if not texts_a or not texts_b:
        return [[] for _ in texts_a]
    vec = TfidfVectorizer(stop_words="english").fit(texts_a + texts_b)
    A = vec.transform(texts_a)          # L2-normalized -> dot product = cosine
    B = vec.transform(texts_b)
    results = []
    k = min(k, len(texts_b))
    CHUNK = 1024
    for start in range(0, A.shape[0], CHUNK):
        cos = (A[start:start + CHUNK] @ B.T).toarray()
        for r in range(cos.shape[0]):
            row = cos[r]
            idx = np.argpartition(row, -k)[-k:] if len(row) > k else np.arange(len(row))
            ta = texts_a[start + r].lower()
            cands = []
            for j in idx:
                fuzzy = difflib.SequenceMatcher(None, ta, texts_b[j].lower()).ratio()
                cands.append((int(j), 0.6 * float(row[j]) + 0.4 * fuzzy))
            cands.sort(key=lambda x: -x[1])
            results.append(cands)
    return results


def llm_confirm_merge(a: str, b: str) -> Optional[bool]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=5,
            messages=[{"role": "user", "content":
                "Do these two listings describe the SAME physical item? "
                "Answer only YES or NO.\n\nListing A: " + a + "\nListing B: " + b}])
        return "".join(t.text for t in resp.content if hasattr(t, "text")).strip().upper().startswith("Y")
    except Exception:
        return None


def _canonical_name(fields: dict) -> str:
    name = str(fields.get("name") or fields.get("id") or "item")
    for key, val in (fields.get("attributes") or {}).items():
        if any(h in key.lower() for h in VARIANT_HINTS) and val:
            return f"{name} - {val}"
    return name


def unify(table_records: List[RawRecord], post_records: List[RawRecord],
          note_records: List[RawRecord]) -> List[UnifiedProduct]:
    products: List[UnifiedProduct] = []
    matched_posts = set()
    candidates = _top_candidates([r.text for r in table_records],
                                 [r.text for r in post_records], k=3)

    for i, row in enumerate(table_records):
        best_j, best_score = -1, 0.0
        for j, score in candidates[i]:
            if post_records[j].source_id in matched_posts:
                continue   # already claimed - fall to the next candidate
            best_j, best_score = j, score
            break

        p = UnifiedProduct(
            product_id=row.fields["id"],
            canonical_name=_canonical_name(row.fields),
            attributes=dict(row.fields.get("attributes") or {}),
            prices=dict(row.fields.get("prices") or {}),
            stock_qty=row.fields.get("stock_qty"),
            last_updated=row.date,
            sources=[row.to_dict()])

        if best_j >= 0 and best_score >= REVIEW_THRESHOLD:
            post = post_records[best_j]
            matched_posts.add(post.source_id)
            p.sources.append(post.to_dict())
            if best_score >= AUTO_MERGE_THRESHOLD:
                if llm_confirm_merge(row.text, post.text) is False:
                    p.needs_review = True
                    p.review_reason = f"Similarity {best_score:.2f} but LLM check disagreed."
                else:
                    _reconcile_price_conflict(p, row, post)
            else:
                p.needs_review = True
                p.review_reason = f"Matched post {post.source_id} with moderate confidence ({best_score:.2f})."
                p.price_confidence = "medium"
            if post.fields.get("mentions_out_of_stock") and p.stock_qty:
                p.stock_confidence = "low"
        products.append(p)

    for post in post_records:
        if post.source_id in matched_posts:
            continue
        prices = post.fields.get("extracted_prices") or []
        products.append(UnifiedProduct(
            product_id=f"UNLISTED-{post.source_id}",
            canonical_name=(post.fields.get("title") or post.source_id).title(),
            prices={"quoted high": max(prices), "quoted low": min(prices)} if len(prices) > 1
                   else ({"quoted": prices[0]} if prices else {}),
            last_updated=post.date,
            price_confidence="medium" if prices else "low",
            stock_confidence="low", sources=[post.to_dict()],
            needs_review=True,
            review_reason="No matching record in the main table - likely a new arrival not yet logged into the system."))

    _attach_notes(products, note_records)
    return products


def _reconcile_price_conflict(p: UnifiedProduct, row: RawRecord, post: RawRecord) -> None:
    """When the table and a post disagree on price, prefer the fresher
    source but flag it - wrongly quoted prices are the costliest failure."""
    post_prices = set(post.fields.get("extracted_prices") or [])
    table_prices = {v for v in (p.prices or {}).values() if v is not None}
    if not post_prices or not table_prices:
        return
    if not (post_prices & table_prices):
        rd, pd = _d(row.date), _d(post.date)
        if rd and pd and rd >= pd:
            p.price_confidence = "medium"
            p.review_reason = (f"Post ({post.date}) quoted different prices than the current "
                               f"table ({row.date}); the table is fresher and was used.")


def _attach_notes(products: List[UnifiedProduct], note_records: List[RawRecord]) -> None:
    """Notes are few but products may be many, so we block from the note
    side: for each note, find its top matching products via sparse cosine,
    fuzzy-refine those, and attach where the blend clears the threshold."""
    if not products or not note_records:
        return
    per_note = _top_candidates([r.text for r in note_records],
                               [p.searchable_text() for p in products], k=8)
    for j, note in enumerate(note_records):
        for i, score in per_note[j]:
            if score < NOTE_ATTACH_THRESHOLD:
                continue
            p = products[i]
            p.sources.append(note.to_dict())
            low = note.text.lower()
            if note.fields.get("is_quality_flag"):
                p.quality_note = ((p.quality_note or "") + " " + note.text).strip()
            if note.fields.get("is_pricing_rule"):
                p.moq_note = ((p.moq_note or "") + " " + note.text).strip()
            if "alternative" in low or "offer" in low:
                p.alternative_suggestion = note.text
            if "out of stock" in low and any(
                    str(v).lower() in low for v in p.attributes.values() if v):
                p.stock_confidence = "low"


def _d(s: Optional[str]):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return None
