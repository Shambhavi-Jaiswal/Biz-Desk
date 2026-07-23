"""Structured query parsing - filter/aggregate questions over the catalog.

"Give flagged items", "list items under Rs 500", "which items are about to
run out of stock", "quantity less than 50 units" - these are not lookups
for ONE item, they are filters over ALL items. This module detects that
intent and translates natural language into structured conditions, fully
offline and deterministic.

The router runs BEFORE similarity retrieval: if a query parses into a
filter, it is answered from the whole catalog; otherwise it falls through
to normal top-1 retrieval. (Upgrade path: swap this rule-based parser for
an LLM function-call that emits the same filter dict - the executor
underneath stays identical.)
"""

import re
from typing import Optional

LOW_STOCK_THRESHOLD = 20   # matches the "low" pill in the UI

_CMP = re.compile(
    r"(less than|under|below|up ?to|cheaper than|more than|above|over|at least|greater than)"
    r"\s*(?:rs\.?|rupees|inr)?\s*(\d[\d,]*)", re.I)
_STOCK_WORDS = re.compile(r"unit|qty|quantit|stock|piece|pcs", re.I)
_LT = {"less than", "under", "below", "up to", "upto", "cheaper than"}

_STOP = set(("give show list me all the a an items item products product with that are is was "
             "of in less than under below above more over at least rs rupees inr price prices "
             "rate rates units unit quantity qty stock pieces pcs about to get go run out low "
             "running flagged flag sold available which whose their there than cheaper greater "
             "and or very provide find fetch display tell check need want kindly please currently "
             "have has get going almost").split())


def parse(query: str) -> Optional[dict]:
    """Returns a filter dict if the query is a filter/aggregate question,
    else None (caller falls through to similarity retrieval)."""
    ql = " " + query.lower() + " "
    f = {"flagged": False, "oos": False, "low": None,
         "price": None, "stock": None, "terms": []}
    matched = False

    if re.search(r"\bflag", ql):
        f["flagged"] = True; matched = True
    if re.search(r"out of stock|sold out|zero stock", ql) and not re.search(r"about to|going", ql):
        f["oos"] = True; matched = True
    if re.search(r"about to (get |go |run )?out|running (out|low)|almost (out|over)|low (on )?stock|low stock", ql):
        f["low"] = LOW_STOCK_THRESHOLD; matched = True

    for m in _CMP.finditer(ql):
        op = "<" if m.group(1).lower() in _LT else ">"
        val = int(m.group(2).replace(",", ""))
        window = ql[max(0, m.start() - 25): m.end() + 25]
        if _STOCK_WORDS.search(window):
            f["stock"] = (op, val)
        else:
            f["price"] = (op, val)
        matched = True

    if not matched:
        return None

    terms = [t for t in re.findall(r"[a-z]+", ql) if t not in _STOP and len(t) > 2]
    f["terms"] = terms
    return f


def _primary_price(p: dict):
    prices = [v for v in (p.get("prices") or {}).values() if v is not None]
    return prices[0] if prices else None


def _haystack(p: dict) -> str:
    parts = [p.get("canonical_name") or ""]
    parts += [str(v) for v in (p.get("attributes") or {}).values() if v]
    return " ".join(parts).lower()


def run(products: list, f: dict) -> list:
    """Applies the filter dict to the full catalog. O(N), fine at 100k rows."""
    out = []
    for p in products:
        st = p.get("stock_qty")
        if f["flagged"] and not p.get("needs_review"):
            continue
        if f["oos"] and st != 0:
            continue
        if f["low"] is not None and not (st is not None and 0 < st <= f["low"]):
            continue
        if f["stock"]:
            op, v = f["stock"]
            if st is None or (op == "<" and not st < v) or (op == ">" and not st > v):
                continue
        if f["price"]:
            op, v = f["price"]
            pr = _primary_price(p)
            if pr is None or (op == "<" and not pr < v) or (op == ">" and not pr > v):
                continue
        if f["terms"]:
            hay = _haystack(p)
            if not all(t in hay or t.rstrip("s") in hay for t in f["terms"]):
                continue
        out.append(p)

    if f["price"]:
        out.sort(key=lambda p: _primary_price(p) or 0)
    elif f["stock"] or f["low"] is not None or f["oos"]:
        out.sort(key=lambda p: (p.get("stock_qty") is None, p.get("stock_qty") or 0))
    else:
        out.sort(key=lambda p: p.get("canonical_name") or "")
    return out


def describe(f: dict) -> str:
    bits = []
    if f["flagged"]: bits.append("flagged for review")
    if f["oos"]: bits.append("out of stock")
    if f["low"] is not None: bits.append(f"stock {f['low']} units or less (about to run out)")
    if f["price"]: bits.append(f"primary price {f['price'][0]} Rs {f['price'][1]}")
    if f["stock"]: bits.append(f"stock {f['stock'][0]} {f['stock'][1]} units")
    if f["terms"]: bits.append("matching '" + " ".join(f["terms"]) + "'")
    return ", ".join(bits) if bits else "your filter"
