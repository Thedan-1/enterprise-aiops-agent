"""Dataset quality gate used locally and in CI."""
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "eval" / "dataset" / "eval_cases.json"
DOCS = ROOT / "data" / "raw"


def validate() -> dict:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    doc_slugs = {path.stem for path in DOCS.rglob("*.md")}
    ids = [case["id"] for case in cases]
    questions = [case["question"].strip().lower() for case in cases]
    assert len(cases) >= 100, "V2 requires at least 100 evaluation cases"
    assert len(ids) == len(set(ids)), "duplicate case id"
    assert len(questions) == len(set(questions)), "duplicate question"
    unknown = {
        slug for case in cases for slug in case["ground_truth_doc_slugs"] if slug not in doc_slugs
    }
    assert not unknown, f"unknown ground-truth documents: {sorted(unknown)}"
    for case in cases:
        if case["category"] == "not_in_kb":
            assert case["ground_truth_doc_slugs"] == [], f"out-of-KB case {case['id']} has ground truth"
    return {"cases": len(cases), "documents": len(doc_slugs), "categories": dict(Counter(c["category"] for c in cases))}


if __name__ == "__main__":
    print(json.dumps(validate(), ensure_ascii=False, indent=2))

