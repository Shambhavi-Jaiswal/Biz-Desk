"""Grounded answer generation with confidence-aware hedging.

Design rule #1: the system NEVER invents a number. Every price and stock
figure is copied from a retrieved record. When the underlying data is
uncertain (conflicting sources, stale posts, unlisted new arrivals), the
answer says so - and out-of-catalog questions get an explicit refusal
instead of a confident wrong answer.
"""

import json
import os
from typing import Optional

from src.retrieval.hybrid_search import HybridIndex
from src.retrieval import structured_query

REFUSE_THRESHOLD = 0.10
HEDGE_THRESHOLD = 0.25


def _price_label(col: str) -> str:
    label = col.replace("price", "").replace("_", " ").strip()
    return (label or "price").capitalize()


class AnswerEngine:
    def __init__(self, kb_path: str):
        with open(kb_path, encoding="utf-8") as f:
            kb = json.load(f)
        self.products = kb["products"]
        self.notes = kb["notes"]
        self.index = HybridIndex(self.products, self.notes)

    def answer(self, query: str) -> dict:
        # Route 1: filter/aggregate questions ("flagged items", "under Rs 500",
        # "about to run out") answer from the WHOLE catalog, not one item.
        filt = structured_query.parse(query)
        if filt is not None:
            return self._list_answer(filt)

        # Route 2: single-item / policy lookup via similarity retrieval.
        hits = self.index.search(query, k=3)
        if not hits or hits[0].score < REFUSE_THRESHOLD:
            return {"refused": True, "confidence": "none",
                    "answer": ("I could not find anything in your records matching that. "
                               "I only answer from the data you've loaded - please check "
                               "the source directly."),
                    "products": [], "hits": []}

        top = hits[0]
        hedge = "Closest match I found - please confirm this is the item you meant:\n\n" \
            if top.score < HEDGE_THRESHOLD else ""

        if top.kind == "note":
            dated = f", dated {top.ref['date']}" if top.ref.get("date") else ""
            body = f"As per your notes ({top.ref['source_id']}{dated}):\n{top.ref['text']}"
            result = {"refused": False, "confidence": "high", "answer": hedge + body,
                      "products": [], "hits": [self._hit_view(h) for h in hits]}
        else:
            body, confidence = self._product_answer(top.ref)
            result = {"refused": False, "confidence": confidence, "answer": hedge + body,
                      "products": [self._product_view(top.ref)],
                      "hits": [self._hit_view(h) for h in hits]}

        polished = self._llm_polish(query, result)  # list mode returns before this
        if polished:
            result["answer"] = polished
        return result

    def _list_answer(self, filt: dict) -> dict:
        matches = structured_query.run(self.products, filt)
        desc = structured_query.describe(filt)
        views = [self._product_view(p) for p in matches[:200]]

        if not matches:
            text = f"No items match: {desc}."
        else:
            head = f"{len(matches)} item{'s' if len(matches) != 1 else ''} match ({desc}):"
            rows = []
            for p in matches[:20]:
                pr = structured_query._primary_price(p)
                st = p.get("stock_qty")
                stock_txt = ("out of stock" if st == 0 else
                             f"{st:g} units" if st is not None else "stock unknown")
                rows.append(f"- {p['canonical_name']} ({p['product_id']})"
                            + (f" - Rs {pr:g}" if pr is not None else "")
                            + f" - {stock_txt}"
                            + (" [FLAGGED]" if p.get("needs_review") else ""))
            if len(matches) > 20:
                rows.append(f"...and {len(matches) - 20} more (see the list below).")
            text = head + "\n" + "\n".join(rows)

        return {"refused": False, "mode": "list", "confidence": "high",
                "answer": text, "count": len(matches),
                "items": views, "products": [], "hits": []}

    def _product_answer(self, p: dict) -> tuple:
        lines = [f"{p['canonical_name']} ({p['product_id']})"]
        rates = [f"{_price_label(c)} Rs {v:g}" for c, v in (p.get("prices") or {}).items()
                 if v is not None]
        lines.append("Rates: " + (" | ".join(rates) if rates
                     else "not recorded - confirm with the owner"))

        stock = p.get("stock_qty")
        if stock is None:
            lines.append("Stock: not recorded in the system - confirm the count directly.")
        elif stock == 0:
            lines.append("Stock: OUT OF STOCK.")
        else:
            upd = f" (updated {p['last_updated']})" if p.get("last_updated") else ""
            lines.append(f"Stock: {stock:g} units{upd}.")

        confidence = "high"
        if p.get("price_confidence") != "high":
            confidence = "medium"
            lines.append("Caution: price sources disagreed for this item - verify before quoting.")
        if p.get("stock_confidence") != "high" and stock not in (0, None):
            confidence = "medium"
            lines.append("Caution: stock figure may be stale - physically confirm before committing.")
        if p.get("needs_review") and p.get("review_reason"):
            confidence = "medium"
            lines.append(f"Note: {p['review_reason']}")
        if p.get("quality_note"):
            lines.append(f"Quality note: {p['quality_note']}")
        if p.get("moq_note"):
            lines.append(f"Pricing rule: {p['moq_note']}")
        if stock == 0 and p.get("alternative_suggestion"):
            lines.append(f"Suggested alternative: {p['alternative_suggestion']}")
        return "\n".join(lines), confidence

    def _product_view(self, p: dict) -> dict:
        keys = ["product_id", "canonical_name", "attributes", "prices", "stock_qty",
                "last_updated", "price_confidence", "stock_confidence",
                "quality_note", "moq_note", "alternative_suggestion",
                "needs_review", "review_reason"]
        return {k: p.get(k) for k in keys}

    def _hit_view(self, h) -> dict:
        if h.kind == "product":
            label = f"{h.ref['canonical_name']} ({h.ref['product_id']})"
            srcs = sorted({s["source"] for s in h.ref.get("sources", [])})
        else:
            label = f"Note {h.ref['source_id']}" + (f" ({h.ref['date']})" if h.ref.get("date") else "")
            srcs = ["notes"]
        return {"kind": h.kind, "label": label, "score": h.score, "sources": srcs}

    def _llm_polish(self, query: str, result: dict) -> Optional[str]:
        if not os.environ.get("ANTHROPIC_API_KEY") or result["refused"]:
            return None
        try:
            import anthropic
            client = anthropic.Anthropic()
            resp = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=400,
                messages=[{"role": "user", "content":
                    "Rephrase this stock/pricing answer for a business assistant. STRICT: "
                    "use ONLY facts below, change no number, drop no caution, add nothing.\n\n"
                    f"Question: {query}\n\nFacts:\n{result['answer']}"}])
            return "".join(b.text for b in resp.content if hasattr(b, "text")).strip() or None
        except Exception:
            return None
