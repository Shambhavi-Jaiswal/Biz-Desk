# BizDesk sample datasets

Three complete example businesses to try in BizDesk. Each folder has the
three files the "Your data" tab accepts:

| File | What it is | Required? |
|---|---|---|
| `table.csv` | The inventory/price sheet | Yes |
| `posts.json` | Catalog posts (WhatsApp/Instagram style) | Optional |
| `notes.txt` | Informal staff notes and policies | Optional |

## How to load one

1. Run BizDesk (`python3 server.py`) and open http://localhost:8000
2. Go to the **Your data** tab
3. Pick the three files from one folder (e.g. `furniture/`)
4. Click **Load my data**
5. Go to the **Ask** tab and try the questions below

Notice that every business has different column names - BizDesk detects
them automatically. No configuration needed.

## Questions to try

### Furniture (`furniture/`)
- `teak coffee table wholesale rate` - straight price lookup
- `rocking chair available?` - out of stock, suggests checking with owner
- `delivery charge kya hai` - answered from the notes (policy)
- `study desk rate` - the stale-price trap: an old post says 1950, the
  correct current answer is 2050 with a caution
- `L shape sofa rate` - a new arrival not yet in the sheet, answered from
  the post with a "not yet logged" warning

### Toy shop (`toys/`)
- `talking teddy dozen rate` - stale-price trap: old post says 950,
  correct answer is 990
- `cricket set available?` - out of stock + alternatives from the notes
- `bulk order discount for schools` - informal 5% rule from the notes
- `mini drone rate` - unlisted new arrival
- `T-505 stock` - exact code lookup

### Electronics (`electronics/`)
- `power bank 20000 dealer rate` - stale-price trap: old post says 1250,
  correct answer is 1320
- `tempered glass pack stock` - out of stock + counter-stock workaround
  from the notes
- `warranty claim rule` - policy answered from the notes
- `car holder quality issue` - the weak-magnet batch warning
- `E-703 stock` - exact code lookup

## What to look at besides the answers

- The **stamp** on each slip: CONFIRMED means all sources agreed;
  VERIFY means something was uncertain and the caution below says why.
- The **Review** tab after loading: every item the engine merged with
  doubt, with the reason - stale posts, unlisted arrivals, moderate matches.
- Ask something the business does not sell (e.g. `do you sell sarees` to
  the furniture store) - it refuses instead of guessing.
