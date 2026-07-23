"""Runs ingestion + unification and writes the unified knowledge base.

Reads from data/raw/user/ if the user has uploaded their own data
(via the Data tab), otherwise falls back to the bundled demo dataset.
Rerun whenever any raw source changes.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ingestion.load_table import load_table
from src.ingestion.load_posts import load_posts
from src.ingestion.load_notes import load_notes
from src.unification.entity_resolver import unify

DEMO = {"table": ROOT / "data/raw/erp_inventory.csv",
        "posts": ROOT / "data/raw/whatsapp_catalog.json",
        "notes": ROOT / "data/raw/staff_notes.txt"}
USER = {"table": ROOT / "data/raw/user/table.csv",
        "posts": ROOT / "data/raw/user/posts.json",
        "notes": ROOT / "data/raw/user/notes.txt"}


def build(force_demo: bool = False) -> dict:
    use_user = (not force_demo) and USER["table"].exists()
    paths = USER if use_user else DEMO

    table = load_table(str(paths["table"]))
    posts = load_posts(str(paths["posts"])) if paths["posts"].exists() else []
    notes = load_notes(str(paths["notes"])) if paths["notes"].exists() else []
    products = unify(table, posts, notes)

    kb = {"products": [p.to_dict() for p in products],
          "notes": [n.to_dict() for n in notes],
          "stats": {"dataset": "your data" if use_user else "demo data",
                    "table_rows": len(table), "posts": len(posts), "notes": len(notes),
                    "unified_products": len(products),
                    "flagged_for_review": sum(p.needs_review for p in products)}}
    out = ROOT / "data/processed/knowledge_base.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(kb, indent=2, ensure_ascii=False), encoding="utf-8")
    return kb["stats"]


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
