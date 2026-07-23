"""BizDesk server - stdlib only, no framework needed.

Endpoints:
  GET  /              -> frontend/index.html (the app)
  POST /api/query     -> {"question": "..."} => grounded answer JSON
  POST /api/upload    -> {"table_csv": "...", "posts_json": "...", "notes_txt": "..."}
                         saves the user's own data and rebuilds the knowledge base
  POST /api/use_demo  -> switch back to the bundled demo dataset
  GET  /api/products  -> full unified catalog
  GET  /api/review    -> records flagged needs_review
  GET  /api/health    -> {"ok": true, ...kb stats}

Run:  python3 server.py
"""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from scripts.build_kb import build
from src.generation.answer_engine import AnswerEngine

KB_PATH = ROOT / "data/processed/knowledge_base.json"
USER_DIR = ROOT / "data/raw/user"
LOCK = threading.Lock()

STATE = {}


def reload_engine(force_demo: bool = False):
    stats = build(force_demo=force_demo)
    kb = json.loads(KB_PATH.read_text(encoding="utf-8"))

    def view(p):
        keys = ["product_id", "canonical_name", "attributes", "prices", "stock_qty",
                "last_updated", "price_confidence", "stock_confidence",
                "quality_note", "moq_note", "needs_review", "review_reason"]
        v = {k: p.get(k) for k in keys}
        v["source_kinds"] = sorted({s["source"] for s in p.get("sources", [])})
        return v

    with LOCK:
        STATE["engine"] = AnswerEngine(str(KB_PATH))
        STATE["stats"] = stats
        STATE["products"] = json.dumps(
            {"products": [view(p) for p in kb["products"]]}, ensure_ascii=False).encode("utf-8")
        STATE["review"] = json.dumps(
            {"flagged": [view(p) for p in kb["products"] if p.get("needs_review")]},
            ensure_ascii=False).encode("utf-8")
    return stats


def empty_state():
    """Fresh boot: nothing loaded until the user chooses demo or uploads."""
    with LOCK:
        STATE["engine"] = None
        STATE["stats"] = {"dataset": "none", "table_rows": 0, "posts": 0,
                          "notes": 0, "unified_products": 0, "flagged_for_review": 0}
        STATE["products"] = json.dumps({"products": []}).encode("utf-8")
        STATE["review"] = json.dumps({"flagged": []}).encode("utf-8")


if (USER_DIR / "table.csv").exists():
    reload_engine()          # user had loaded their own data before - keep it
else:
    empty_state()            # start clean; demo loads only on request


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (ROOT / "frontend/index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/health":
            self._json(200, {"ok": True, **STATE["stats"]})
        elif self.path == "/api/products":
            self._send(200, STATE["products"], "application/json; charset=utf-8")
        elif self.path == "/api/review":
            self._send(200, STATE["review"], "application/json; charset=utf-8")
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._json(400, {"error": "invalid JSON body"})
            return

        if self.path == "/api/query":
            question = (body.get("question") or "").strip()
            if not question:
                self._json(400, {"error": "question is required"})
                return
            try:
                with LOCK:
                    engine = STATE["engine"]
                if engine is None:
                    self._json(200, {"refused": True, "confidence": "none",
                        "answer": ("No data loaded yet. Open the Your data tab to "
                                   "upload your files, or try the demo dataset."),
                        "products": [], "hits": []})
                    return
                self._json(200, engine.answer(question))
            except Exception as exc:
                self._json(500, {"error": str(exc)})

        elif self.path == "/api/upload":
            table_csv = body.get("table_csv")
            if not table_csv or "," not in table_csv.splitlines()[0]:
                self._json(400, {"error": "A CSV table with a header row is required."})
                return
            if body.get("posts_json"):
                try:
                    parsed = json.loads(body["posts_json"])
                    assert isinstance(parsed, list)
                except Exception:
                    self._json(400, {"error": "Posts file must be a JSON list."})
                    return
            try:
                USER_DIR.mkdir(parents=True, exist_ok=True)
                (USER_DIR / "table.csv").write_text(table_csv, encoding="utf-8")
                if body.get("posts_json"):
                    (USER_DIR / "posts.json").write_text(body["posts_json"], encoding="utf-8")
                else:
                    (USER_DIR / "posts.json").unlink(missing_ok=True)
                if body.get("notes_txt"):
                    (USER_DIR / "notes.txt").write_text(body["notes_txt"], encoding="utf-8")
                else:
                    (USER_DIR / "notes.txt").unlink(missing_ok=True)
                stats = reload_engine()
                self._json(200, {"ok": True, **stats})
            except Exception as exc:
                self._json(500, {"error": f"Could not process the data: {exc}"})

        elif self.path == "/api/use_demo":
            try:
                for f in ("table.csv", "posts.json", "notes.txt"):
                    (USER_DIR / f).unlink(missing_ok=True)
                stats = reload_engine(force_demo=True)
                self._json(200, {"ok": True, **stats})
            except Exception as exc:
                self._json(500, {"error": str(exc)})
        else:
            self._json(404, {"error": "not found"})

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _send(self, code, payload, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        print(f"[server] {args[0] if args else ''}")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"BizDesk running at http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
