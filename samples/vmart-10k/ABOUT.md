# V-Mart-style store sample (~10,000 items)

A synthetic value-fashion-retail dataset in the shape of a V-Mart-type store,
for testing BizDesk at scale. All data is fictional - product names use
made-up house brands, and nothing here is real company data.

## Contents

| File | Size | What's inside |
|---|---|---|
| `table.csv` | ~10,000 rows | sku, product name, category, brand, size, color, MRP, offer price, stock, updated date |
| `posts.json` | 258 posts | promo posts; ~15% quote a stale (last month's) offer price; 8 are new arrivals not yet in the table |
| `notes.txt` | 25 notes | exchange policy, festival discount rule, school bulk-order rule, defect batches, stockout callbacks, low-stock warnings |

Categories: Mens Wear, Womens Wear, Kids Wear, Footwear, Home & Kitchen,
Accessories - roughly 2,000 items out of stock and 1,500 running low, so the
filter queries return meaningful sets.

## Load it

Your data tab -> pick the three files -> Load my data. On a typical laptop the
build takes about 10 seconds for this size (blocking-based unification).

## Questions to try

Lookups:
- `VM-10001 stock` (exact code)
- `sequin kurti new arrival price` (unlisted arrival -> flagged answer)
- `exchange policy kya hai` / `school uniform bulk discount` (from notes)

Filters:
- `items less than 200 rs`
- `give flagged items`
- `items about to get out of stock`
- `which items are out of stock`
- `kids wear under 300`

Honesty checks:
- ask about a post-promoted item - if the post carried last month's rate,
  the answer uses the current table price and warns about the conflict
- `do you sell live goldfish` -> refuses
