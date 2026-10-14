"""Load eval results into a normalized record list.

Native schema (one JSON object per line, or a JSON array):
  test_id, requirement_id, input, output, verdict ("pass"|"fail"|"error"),
  score (optional float), model, timestamp (ISO 8601).
Adapters: promptfoo `--output results.json` / `.jsonl`,
DeepEval-style test case lists (best effort).
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


# promptfoo ResultFailureReason: 0 = none, 1 = assertion failed, 2 = provider/runtime error
_PF_ERROR = 2


def _pf_rows(data) -> tuple[list[dict], str | None]:
    """Return (result rows, run timestamp) for any promptfoo export shape we accept.

    - `-o results.json`: {evalId, results: {version, timestamp, results: [...], stats}, config}
    - older JSON: {createdAt, results: {results: [...]}}
    - `-o results.jsonl`: one result row per line (no run timestamp)
    """
    if isinstance(data, list):
        return data, None
    inner = data.get("results") or {}
    if isinstance(inner, list):
        return inner, data.get("timestamp") or data.get("createdAt")
    ts = inner.get("timestamp") or data.get("timestamp") or data.get("createdAt")
    return inner.get("results") or [], ts


def _pf_verdict(r: dict) -> str:
    if r.get("error") or r.get("failureReason") == _PF_ERROR:
        return "error"
    if r.get("success"):
        return "pass"
    return "fail"


def _pf_provider(r: dict) -> str:
    prov = r.get("provider")
    if isinstance(prov, str):
        return prov
    prov = prov or {}
    return prov.get("label") or prov.get("id") or "unknown"


def from_promptfoo(data) -> list[dict]:
    """Map promptfoo result rows to the native schema.

    `requirement_id` / `test_id` come from the test's `metadata`. Rows without a test_id
    get a stable id from their position (`pf-t<testIdx>-p<promptIdx>`), so the same eval
    re-exported maps to the same ids.
    """
    rows, run_ts = _pf_rows(data)
    recs = []
    for i, r in enumerate(rows):
        tc = r.get("testCase") or {}
        meta = {**(r.get("metadata") or {}), **(tc.get("metadata") or {})}
        t_idx, p_idx = r.get("testIdx", i), r.get("promptIdx", 0)
        recs.append({
            "test_id": meta.get("test_id", f"pf-t{t_idx}-p{p_idx}"),
            "requirement_id": meta.get("requirement_id", "UNMAPPED"),
            "input": json.dumps(r.get("vars", tc.get("vars", {})), sort_keys=True),
            "output": (r.get("response") or {}).get("output", "") or "",
            "verdict": _pf_verdict(r),
            "score": r.get("score"),
            "model": _pf_provider(r),
            "timestamp": run_ts or meta.get("timestamp", "unknown"),
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
