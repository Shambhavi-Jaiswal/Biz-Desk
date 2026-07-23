"""Scale benchmark: proves the pipeline handles 10k+ rows.

Generates a synthetic 12,000-item catalog, builds the knowledge base
(ingestion + blocking-based unification + index), then times a mixed set
of lookup and filter queries. Run: python3 scripts/benchmark.py
"""

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ingestion.load_table import load_table
from src.ingestion.load_posts import load_posts
from src.ingestion.load_notes import load_notes
from src.unification.entity_resolver import unify
from src.generation.answer_engine import AnswerEngine

N_ROWS, N_POSTS, N_NOTES = 12000, 400, 40
random.seed(7)

ADJ = ["Classic", "Premium", "Eco", "Deluxe", "Compact", "Heavy Duty", "Slim", "Pro", "Smart", "Basic"]
NOUN = ["Kurti", "Saree", "Chair", "Table", "Speaker", "Charger", "Teddy", "Blocks", "Bottle",
        "Lamp", "Mixer", "Fan", "Kettle", "Backpack", "Shoes", "Watch", "Helmet", "Mattress"]
VAR = ["Red", "Blue", "Green", "Black", "White", "Grey", "Teal", "Maroon", "Beige", "Olive"]
MAT = ["Cotton", "Steel", "Plastic", "Wood", "Silk", "Leather", "Rayon", "Glass", "Bamboo", "Alloy"]


def make_dataset(tmp: Path):
    rows = ["sku,product_name,material,color,price_single,price_bulk,stock_qty,last_updated"]
    for i in range(N_ROWS):
        name = f"{random.choice(ADJ)} {random.choice(NOUN)}"
        single = random.randint(90, 9000)
        rows.append(f"B-{i:05d},{name},{random.choice(MAT)},{random.choice(VAR)},"
                    f"{single},{int(single*0.85)},{random.choice([0]*2 + list(range(1,300)))},2026-07-{random.randint(1,21):02d}")
    (tmp / "table.csv").write_text("\n".join(rows))

    posts = []
    for i in range(N_POSTS):
        j = random.randrange(N_ROWS)
        sku, name, mat, col = rows[j + 1].split(",")[:4]
        posts.append({"id": f"P-{i}", "title": f"{name.lower()} {col.lower()} {mat.lower()}",
                      "text": f"{col} {mat} {name}, good rate for bulk buyers. Limited stock!",
                      "date": "2026-07-10"})
    (tmp / "posts.json").write_text(json.dumps(posts))

    notes = []
    for i in range(N_NOTES):
        j = random.randrange(N_ROWS)
        name = rows[j + 1].split(",")[1]
        notes.append(f"---\n[Note {i+1} - 2026-07-15]\nFor {name} bulk orders above 100 pieces "
                     f"there is an extra discount, owner approves verbally.")
    (tmp / "notes.txt").write_text("\n".join(notes))


def main():
    tmp = Path("/tmp/bizdesk-bench")
    tmp.mkdir(exist_ok=True)
    make_dataset(tmp)

    t0 = time.time()
    table = load_table(str(tmp / "table.csv"))
    posts = load_posts(str(tmp / "posts.json"))
    notes = load_notes(str(tmp / "notes.txt"))
    t_ingest = time.time() - t0

    t0 = time.time()
    products = unify(table, posts, notes)
    t_unify = time.time() - t0

    kb = {"products": [p.to_dict() for p in products], "notes": [n.to_dict() for n in notes],
          "stats": {}}
    kb_path = tmp / "kb.json"
    kb_path.write_text(json.dumps(kb))

    t0 = time.time()
    engine = AnswerEngine(str(kb_path))
    t_index = time.time() - t0

    queries = (["premium kurti red price", "B-00042 stock", "deluxe table wood rate",
                "smart watch black available?", "eco bottle bamboo price"] * 2 +
               ["give flagged items", "items less than 500 rs",
                "items about to get out of stock", "quantity less than 50 units",
                "which items are out of stock"] * 2)
    lat = []
    for q in queries:
        t0 = time.time()
        engine.answer(q)
        lat.append((time.time() - t0) * 1000)
    lat.sort()

    print(f"dataset      : {len(table):,} rows + {len(posts)} posts + {len(notes)} notes")
    print(f"ingestion    : {t_ingest:.2f}s")
    print(f"unification  : {t_unify:.2f}s  ({len(products):,} unified items)")
    print(f"index build  : {t_index:.2f}s")
    print(f"query latency: median {lat[len(lat)//2]:.0f}ms | p95 {lat[int(len(lat)*.95)]:.0f}ms | max {lat[-1]:.0f}ms  ({len(queries)} queries)")


if __name__ == "__main__":
    main()
