"""Generic posts loader - marketplace/WhatsApp/Instagram-style listings.

Accepts a JSON list where each item has (any of) these keys:
  id:    post_id | id
  title: catalog_code | title | name
  text:  caption_text | caption | text | description
  date:  date_posted | date | posted_at
Everything is optional except some text; unknown keys are ignored, so
almost any export shape works.
"""

import json
import re
from pathlib import Path
from typing import List

from src.schema import RawRecord

PRICE_PATTERN = re.compile(r"(\d{2,6})\s*(?:/pc|/piece|/unit)?\b")
OOS_FLAGS = ["out of stock", "booking only", "advance booking", "sold out", "unavailable"]
NEW_FLAGS = ["not yet added", "not yet entered", "not in system", "not yet logged"]


def _pick(d: dict, *keys, default=""):
    for k in keys:
        if d.get(k):
            return d[k]
    return default


def load_posts(path: str) -> List[RawRecord]:
    with open(path, encoding="utf-8") as f:
        posts = json.load(f)
    records: List[RawRecord] = []
    for i, post in enumerate(posts):
        title = str(_pick(post, "catalog_code", "title", "name"))
        text = str(_pick(post, "caption_text", "caption", "text", "description"))
        lower = text.lower()
        records.append(RawRecord(
            source="posts",
            source_id=str(_pick(post, "post_id", "id", default=f"post-{i+1}")),
            text=f"{title}. {text}".strip(". "),
            date=_pick(post, "date_posted", "date", "posted_at", default=None),
            fields={"title": title,
                    "extracted_prices": [int(m) for m in PRICE_PATTERN.findall(text)
                                         if 20 <= int(m) <= 500000],
                    "mentions_out_of_stock": any(f in lower for f in OOS_FLAGS),
                    "mentions_new_arrival": any(f in lower for f in NEW_FLAGS)}))
    return records


if __name__ == "__main__":
    recs = load_posts(str(Path(__file__).resolve().parents[2] / "data/raw/whatsapp_catalog.json"))
    print(f"Loaded {len(recs)} posts")
