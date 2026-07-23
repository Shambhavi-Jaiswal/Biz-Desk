"""Shared data structures - business-agnostic.

A product is no longer assumed to be clothing. Whatever columns the
user's table has (fabric/colour for a boutique, material/finish for a
furniture store, brand/warranty for electronics) are carried as a
generic `attributes` dict, and any number of price columns are carried
as an ordered `prices` dict.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RawRecord:
    """A single normalized-but-not-yet-unified item from one raw source."""

    source: str                  # "table" | "posts" | "notes"
    source_id: str
    text: str                    # flattened text used for matching + retrieval
    date: Optional[str] = None
    fields: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"source": self.source, "source_id": self.source_id,
                "text": self.text, "date": self.date, "fields": self.fields}


@dataclass
class UnifiedProduct:
    """A single real-world item after entity resolution across all sources."""

    product_id: str
    canonical_name: str
    attributes: dict = field(default_factory=dict)   # any non-price, non-stock columns
    prices: dict = field(default_factory=dict)       # ordered {column_name: value}
    stock_qty: Optional[int] = None
    moq_note: Optional[str] = None
    quality_note: Optional[str] = None
    alternative_suggestion: Optional[str] = None
    last_updated: Optional[str] = None
    price_confidence: str = "high"                   # high | medium | low
    stock_confidence: str = "high"
    sources: list = field(default_factory=list)
    needs_review: bool = False
    review_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    def searchable_text(self) -> str:
        parts = [self.canonical_name]
        parts += [str(v) for v in self.attributes.values() if v]
        parts += [self.moq_note or "", self.quality_note or ""]
        for s in self.sources:
            if s.get("source") == "posts":
                parts.append(s.get("fields", {}).get("title", ""))
                parts.append(s.get("text", ""))
        return " ".join(p for p in parts if p)
