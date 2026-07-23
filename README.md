# BizDesk - Ask your business records anything

![eval](https://github.com/Shambhavi-Jaiswal/Biz-Desk/actions/workflows/eval.yml/badge.svg)

A grounded RAG system for ANY small business whose critical knowledge is scattered
across three places that never agree with each other: a stock/price spreadsheet,
catalog posts (WhatsApp / Instagram / marketplace listings), and knowledge that
lives only in people's heads. Clothing wholesaler, furniture store, electronics
shop, grocery distributor - upload your own data and ask questions in plain
language (Hinglish works too).

BizDesk unifies those messy sources into one retrievable knowledge base and
answers with one hard rule: **it never invents a number.** Every price and stock
figure in an answer is copied from a retrieved record, and when the underlying
data is uncertain (conflicting prices, stale posts, unlisted new arrivals), the
answer says so explicitly - a VERIFY stamp instead of false confidence.

## Bring your own data - no configuration

The Data tab accepts three files:

1. **Inventory table (CSV, required).** Any column layout works. BizDesk
   auto-detects the id column (sku/id/code...), the name column, every price
   column (anything containing price/rate/mrp/cost), the stock column
   (stock/qty/quantity...), and treats all remaining columns as generic
   attributes - fabric and colour for a boutique, material and finish for a
   furniture store, brand and warranty for electronics.
2. **Catalog posts (JSON, optional).** A list of your listings with flexible
   keys (title/text/date under common names). Prices inside the text are
   extracted automatically; stale prices are detected and reconciled by date.
3. **Notes (plain text, optional).** The informal knowledge no system records -
   discount rules, quality issues, policies. Whisper transcripts of voice memos
   drop straight in. Separate notes with a `---` line.

A complete demo dataset (a clothing wholesale business) is bundled, and one
click switches between demo and your data.

## Architecture

```
inventory table        catalog posts           notes (voice -> text)
      |                      |                        |
      +--- ingestion (auto-detecting normalizers) ----+
                             |
              entity resolution / unification
     (TF-IDF + fuzzy matching -> candidate merges; optional LLM
      confirmation; price-conflict reconciliation by freshness;
      grey-zone merges flagged `needs_review`)
                             |
              unified knowledge base (JSON)
        items with provenance + confidence fields
                             |
                  hybrid retrieval index
     (TF-IDF cosine + token overlap + deterministic exact-ID
      path; standalone policy notes indexed as their own docs)
                             |
              grounded answer generation
     (numbers only ever copied from records; confidence-aware
      hedging; explicit refusal for out-of-catalog questions)
                             |
                      BizDesk UI
        Ask / Catalog / Review / Your data + dark mode
```

### Design decisions worth knowing

- **Exact retrieval for numbers, fuzzy retrieval for descriptions.** Semantic
  similarity is least trustworthy exactly where mistakes are most expensive -
  prices, stock counts, item codes. A query containing an exact id like
  `F-101` deterministically wins; prices are never paraphrased or estimated.
- **Confidence is a first-class field.** Unification writes
  `price_confidence` / `stock_confidence` / `needs_review` onto every record;
  the answer layer turns those into visible cautions and a VERIFY stamp, and
  the Review tab lists every flagged record with its reason - a built-in
  data-cleaning to-do list.
- **Refusal is a feature.** Below a retrieval-score threshold the system says
  it found nothing rather than answering from the nearest wrong record. Ask a
  furniture dataset about sarees and it declines.
- **Offline-first, LLM-optional.** The whole pipeline runs on scikit-learn
  with zero network access, which makes the evaluation deterministic. Setting
  `ANTHROPIC_API_KEY` upgrades two hooks: LLM confirmation of borderline
  entity merges, and natural-language phrasing under a strict no-new-facts
  prompt. Swapping TF-IDF for a real embedding model is a two-line change in
  `src/retrieval/hybrid_search.py`.

## Filter and aggregate queries

Not every question is about one item. A query router detects filter intent
and answers from the whole catalog: "give flagged items", "list items less
than 500 rs", "items about to get out of stock", "quantity less than 50
units", "which items are out of stock" - including combined with terms
("kurtis under 400"). The rule-based parser translates natural language
into structured conditions executed over all items; single-item questions
fall through to similarity retrieval untouched. Upgrade path: swap the
parser for an LLM function-call emitting the same filter dict - the
executor stays identical.

## Scale: 10k+ rows

Entity resolution uses blocking (the standard production pattern): sparse
TF-IDF cosine generates top-k candidates per row in chunks, and the
expensive fuzzy refinement runs only on those candidates - never a dense
NxM matrix. Benchmarked on a synthetic 12,000-row catalog with 400 posts
and 40 notes (`python3 scripts/benchmark.py`):

| Stage | Time |
|---|---|
| Ingestion | 0.2s |
| Unification (12,000 items) | ~6s |
| Index build | 0.3s |
| Query latency | median 17ms, p95 ~110ms |

## Evaluation (the part most RAG demos skip)

`src/evaluation/run_eval.py` runs a fixed set of 13 realistic queries against
the demo dataset - Hinglish phrasing, an exact-id ask, a stale-price trap, a
policy question answered from notes, and two out-of-scope questions that must
be refused. Current results (deterministic, reproducible):

| Metric | Score |
|---|---|
| Retrieval accuracy @1 (incl. 5 filter queries) | 16/16 (100%) |
| Answer correctness (ground truth contained, stale numbers absent) | 11/11 (100%) |
| Refusal correctness | 2/2 (100%) |

The most interesting single case: *"denim long kurti 10 piece rate"* must
answer Rs 510 (the current table rate) and must NOT contain Rs 480 (the stale
price in an old post that buyers keep quoting back). The freshness-based
conflict reconciliation in `entity_resolver.py` is what makes that pass.

```bash
python3 scripts/build_kb.py
python3 src/evaluation/run_eval.py
```

## Running it

```bash
pip install -r requirements.txt   # scikit-learn only, unless you want the LLM hooks
python3 server.py                 # builds the knowledge base on first run
# open http://localhost:8000
```

Four views, plus a dark/light toggle (remembered across visits):

- **Ask** - type a question, get an answer slip with a tear-off edge, a rate
  table built from YOUR price columns, a rubber-stamp confidence mark
  (CONFIRMED / VERIFY / NO MATCH), caution strips, and provenance badges
  showing which sources the answer came from.
- **Catalog** - every unified item as cards with live filter and stock filters.
- **Review** - every record flagged during unification, with reasons and
  per-field confidence tags.
- **Your data** - upload your own three files, or reset to the demo.

The server is stdlib-only (no framework): `POST /api/query`,
`POST /api/upload`, `POST /api/use_demo`, `GET /api/products`,
`GET /api/review`, `GET /api/health`.

## Sample datasets included

The `samples/` folder ships four ready-to-load businesses, each with the three
files the Your data tab accepts - proving the zero-configuration column
detection across completely different industries:

| Folder | Business | Size |
|---|---|---|
| `samples/furniture` | Furniture store | 10 items |
| `samples/toys` | Toy shop | 10 items |
| `samples/electronics` | Mobile accessories | 10 items |
| `samples/vmart-10k` | Value fashion retail | ~10,000 items |

Each includes the realistic traps: stale prices in old posts, out-of-stock
items with alternatives, unlisted new arrivals, defect-batch warnings, and
informal policies that live only in the notes. See `samples/HOW-TO-USE.md`.

## Project layout

```
data/raw/               bundled demo dataset (clothing wholesale)
data/raw/user/          your uploaded data lives here (gitignored)
data/processed/         built knowledge base + eval results (gitignored)
src/ingestion/          auto-detecting loaders: table, posts, notes
src/unification/        entity resolution, conflict reconciliation, note attachment
src/retrieval/          hybrid index (TF-IDF + token overlap + exact-id)
src/generation/         grounded answer engine with confidence hedging
src/evaluation/         eval set + harness
frontend/index.html     the app (vanilla JS, no build step, dark mode)
server.py               stdlib HTTP server
scripts/build_kb.py     offline pipeline entrypoint
```

## Roadmap

- Excel (.xlsx) upload alongside CSV
- Image embeddings (CLIP) over catalog photos for "same as this photo" queries
- Whisper voice input for hands-free counter use
- WhatsApp bot interface so staff can query the same engine from their phones
- Write-back loop: VERIFY-stamped answers feed a review queue that corrects the source data
