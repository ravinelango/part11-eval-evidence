"""Load eval results into a normalized record list.

Native schema (one JSON object per line, or a JSON array):
  test_id, requirement_id, input, output, verdict ("pass"|"fail"|"error"),
  score (optional float), model, timestamp (ISO 8601).
Adapters: promptfoo `--output results.json`, DeepEval-style test case lists (best effort).
"""

from __future__ import annotations

import json
from pathlib import Path

REQUIRED = ("test_id", "requirement_id", "input", "output", "verdict", "model", "timestamp")
VERDICTS = {"pass", "fail", "error"}


class SchemaError(ValueError):
    pass


def _read(path: Path):
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text[0] in "[{" and not path.suffix == ".jsonl":
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def normalize(rec: dict) -> dict:
    missing = [k for k in REQUIRED if k not in rec]
    if missing:
        raise SchemaError(f"record {rec.get('test_id', '?')} missing fields: {missing}")
    v = str(rec["verdict"]).lower()
    if v not in VERDICTS:
        raise SchemaError(f"record {rec['test_id']}: verdict must be one of {sorted(VERDICTS)}")
    out = {k: rec[k] for k in REQUIRED}
    out["verdict"] = v
    out["score"] = rec.get("score")
    return out


def from_promptfoo(data: dict) -> list[dict]:
    """promptfoo eval JSON: results.results[] with vars, response.output, success, score."""
    rows = data.get("results", {}).get("results", [])
    recs = []
    for i, r in enumerate(rows):
        meta = (r.get("testCase") or {}).get("metadata") or {}
        recs.append({
            "test_id": meta.get("test_id", f"pf-{i}"),
            "requirement_id": meta.get("requirement_id", "UNMAPPED"),
            "input": json.dumps(r.get("vars", {})),
            "output": (r.get("response") or {}).get("output", ""),
            "verdict": "pass" if r.get("success") else ("error" if r.get("error") else "fail"),
            "score": r.get("score"),
            "model": (r.get("provider") or {}).get("id", "unknown"),
            "timestamp": data.get("createdAt") or meta.get("timestamp", "unknown"),
        })
    return recs


def from_deepeval(rows: list[dict]) -> list[dict]:
    """DeepEval-style list: {name, input, actual_output, success, metrics_data:[{score}], ...}."""
    recs = []
    for i, r in enumerate(rows):
        md = r.get("metrics_data") or []
        meta = r.get("additional_metadata") or {}
        recs.append({
            "test_id": r.get("name", f"de-{i}"),
            "requirement_id": meta.get("requirement_id", "UNMAPPED"),
            "input": r.get("input", ""),
            "output": r.get("actual_output", ""),
            "verdict": "pass" if r.get("success") else "fail",
            "score": md[0].get("score") if md else None,
            "model": meta.get("model", "unknown"),
            "timestamp": meta.get("timestamp", "unknown"),
        })
    return recs


def load_results(path: str | Path, fmt: str = "native") -> list[dict]:
    data = _read(Path(path))
    if fmt == "promptfoo":
        data = from_promptfoo(data)
    elif fmt == "deepeval":
        data = from_deepeval(data)
    elif isinstance(data, dict):
        data = [data]
    return [normalize(r) for r in data]
