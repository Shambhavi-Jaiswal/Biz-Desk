"""Evaluation harness - the part most RAG demos skip.

Checks three things on a fixed query set:
  1. Retrieval accuracy - did the right product/note come back at rank 1?
  2. Answer correctness - does the answer contain the true price/stock string
     (and NOT contain known-stale numbers, e.g. the old WhatsApp price)?
  3. Refusal correctness - does it decline out-of-catalog questions instead
     of hallucinating an answer?

Deterministic template mode means results are exactly reproducible in CI.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.generation.answer_engine import AnswerEngine


def main():
    engine = AnswerEngine(str(ROOT / "data/processed/knowledge_base.json"))
    cases = json.loads((ROOT / "src/evaluation/eval_set.json").read_text(encoding="utf-8"))

    retrieval_ok = answer_ok = refusal_ok = 0
    retrieval_total = answer_total = refusal_total = 0
    rows = []

    for case in cases:
        res = engine.answer(case["query"])
        ans_low = res["answer"].lower()
        checks = []

        if case.get("expect_mode") == "list":
            retrieval_total += 1
            ids = {it["product_id"] for it in res.get("items", [])}
            ok = (res.get("mode") == "list"
                  and all(x in ids for x in case.get("expect_list_contains", []))
                  and all(x not in ids for x in case.get("expect_list_not_contains", []))
                  and len(ids) >= case.get("expect_list_min", 0))
            retrieval_ok += ok
            checks.append(("filter query returned right set", ok))
        elif case.get("expect_refusal"):
            refusal_total += 1
            passed = res["refused"]
            refusal_ok += passed
            checks.append(("refused correctly", passed))
        else:
            retrieval_total += 1
            top = res["hits"][0] if res["hits"] else None
            if case.get("expect_product"):
                got = res["products"][0]["product_id"] if res["products"] else None
                passed = got == case["expect_product"]
            else:
                passed = bool(top and case["expect_note"] in top["label"])
            retrieval_ok += passed
            checks.append(("retrieved right record @1", passed))

            answer_total += 1
            contains_ok = all(s.lower() in ans_low for s in case.get("expect_contains", []))
            not_contains_ok = all(s.lower() not in ans_low for s in case.get("expect_not_contains", []))
            a_pass = contains_ok and not_contains_ok
            answer_ok += a_pass
            checks.append(("answer contains ground truth", a_pass))

        rows.append({"id": case["id"], "query": case["query"],
                     "checks": [(name, bool(p)) for name, p in checks]})

    print("=" * 62)
    print("EVALUATION RESULTS")
    print("=" * 62)
    for r in rows:
        for name, p in r["checks"]:
            mark = "PASS" if p else "FAIL"
            print(f"  [{mark}] Q{r['id']:>2} {r['query'][:44]:<46} {name}")
    print("-" * 62)
    print(f"  Retrieval accuracy @1 : {retrieval_ok}/{retrieval_total}"
          f"  ({100*retrieval_ok/max(retrieval_total,1):.0f}%)")
    print(f"  Answer correctness    : {answer_ok}/{answer_total}"
          f"  ({100*answer_ok/max(answer_total,1):.0f}%)")
    print(f"  Refusal correctness   : {refusal_ok}/{refusal_total}"
          f"  ({100*refusal_ok/max(refusal_total,1):.0f}%)")
    print("=" * 62)

    (ROOT / "data/processed/eval_results.json").write_text(json.dumps({
        "retrieval_accuracy_at_1": f"{retrieval_ok}/{retrieval_total}",
        "answer_correctness": f"{answer_ok}/{answer_total}",
        "refusal_correctness": f"{refusal_ok}/{refusal_total}",
        "detail": rows}, indent=2), encoding="utf-8")

    all_pass = (retrieval_ok == retrieval_total and answer_ok == answer_total
                and refusal_ok == refusal_total)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
