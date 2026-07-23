"""Generic notes loader - the informal knowledge no system records.

Accepts plain text: notes separated by '---' lines (or blank-line
paragraphs if no '---' present). An optional header like
[Note 3 - 2026-07-10] supplies a date; without it the note still loads.
Voice memos transcribed with Whisper drop straight into this format.
"""

import re
from pathlib import Path
from typing import List

from src.schema import RawRecord

NOTE_HEADER = re.compile(r"\[Note (\d+) - (\d{4}-\d{2}-\d{2})\]")
QUALITY_FLAGS = ["uneven stitching", "defect", "quality issue", "damaged", "scratch", "faulty"]
PRICING_FLAGS = ["extra", "discount", "minimum order value", "% off", "min order", "credit"]


def load_notes(path: str) -> List[RawRecord]:
    content = Path(path).read_text(encoding="utf-8")
    chunks = content.split("---") if "---" in content else re.split(r"\n\s*\n", content)
    file_has_headers = bool(NOTE_HEADER.search(content))

    records: List[RawRecord] = []
    n = 0
    for chunk in chunks:
        m = NOTE_HEADER.search(chunk)
        if file_has_headers and not m:
            continue  # intro text / stray paragraph in a headered file
        body = chunk[m.end():].strip() if m else chunk.strip()
        if not body or len(body) < 15:
            continue
        n += 1
        lower = body.lower()
        records.append(RawRecord(
            source="notes",
            source_id=f"note-{m.group(1)}" if m else f"note-{n}",
            text=body,
            date=m.group(2) if m else None,
            fields={"is_quality_flag": any(f in lower for f in QUALITY_FLAGS),
                    "is_pricing_rule": any(f in lower for f in PRICING_FLAGS),
                    "is_new_unlisted_item": "not yet" in lower}))
    return records


if __name__ == "__main__":
    recs = load_notes(str(Path(__file__).resolve().parents[2] / "data/raw/staff_notes.txt"))
    print(f"Loaded {len(recs)} notes")
