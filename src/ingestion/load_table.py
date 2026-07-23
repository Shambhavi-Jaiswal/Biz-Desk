"""Generic table loader - any business's CSV inventory/price sheet.

Auto-detects which columns mean what, so a boutique's sheet
(sku, fabric, color, price_single...) and a furniture store's sheet
(id, material, finish, price_retail, quantity...) both work with
zero configuration:

  id column     -> first column named like sku/id/code, else the first column
  name column   -> named like name/title/product/item, else the second column
  price columns -> every column whose name contains price/rate/mrp/cost
  stock column  -> named like stock/qty/quantity/inventory/units
  date column   -> named like date/updated
  everything else -> generic attributes
"""

import csv
from pathlib import Path
from typing import List, Optional

from src.schema import RawRecord

ID_HINTS = ("sku", "product_id", "item_id", "item_code", "code", "id")
NAME_HINTS = ("product_name", "item_name", "name", "title", "product", "item")
PRICE_HINTS = ("price", "rate", "mrp", "cost")
STOCK_HINTS = ("stock", "qty", "quantity", "inventory", "units")
DATE_HINTS = ("updated", "date")


def _find(cols, hints, exclude=()):
    for h in hints:
        for c in cols:
            if h in c.lower() and c not in exclude:
                return c
    return None


def load_table(path: str) -> List[RawRecord]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return []
    cols = list(rows[0].keys())

    id_col = _find(cols, ID_HINTS) or cols[0]
    name_col = _find(cols, NAME_HINTS, exclude={id_col}) or (cols[1] if len(cols) > 1 else cols[0])
    price_cols = [c for c in cols if any(h in c.lower() for h in PRICE_HINTS)]
    stock_col = _find(cols, STOCK_HINTS, exclude=set(price_cols) | {id_col, name_col})
    date_col = _find(cols, DATE_HINTS, exclude=set(price_cols))
    attr_cols = [c for c in cols
                 if c not in {id_col, name_col, stock_col, date_col} and c not in price_cols]

    records: List[RawRecord] = []
    for row in rows:
        prices = {c: _num(row.get(c)) for c in price_cols}
        attrs = {c: row.get(c) for c in attr_cols if row.get(c) not in (None, "", "NA")}
        text = (f"{row.get(name_col, '')} " +
                " ".join(str(v) for v in attrs.values()) + ". " +
                " ".join(f"{_pretty(c)} {v}" for c, v in prices.items() if v is not None) +
                (f". Stock: {row.get(stock_col)}" if stock_col else ""))
        records.append(RawRecord(
            source="table", source_id=str(row.get(id_col, "")), text=text,
            date=row.get(date_col) if date_col else None,
            fields={"id": str(row.get(id_col, "")), "name": row.get(name_col, ""),
                    "attributes": attrs, "prices": prices,
                    "stock_qty": _num(row.get(stock_col)) if stock_col else None}))
    return records


def _pretty(col: str) -> str:
    return col.replace("price", "").replace("_", " ").strip() or "price"


def _num(value) -> Optional[float]:
    try:
        if value is None or str(value).strip() in ("", "NA", "na", "-"):
            return None
        v = float(str(value).replace(",", ""))
        return int(v) if v == int(v) else v
    except (ValueError, TypeError):
        return None


if __name__ == "__main__":
    recs = load_table(str(Path(__file__).resolve().parents[2] / "data/raw/erp_inventory.csv"))
    print(f"Loaded {len(recs)} table rows; first: {recs[0].fields['id']} prices={recs[0].fields['prices']}")
