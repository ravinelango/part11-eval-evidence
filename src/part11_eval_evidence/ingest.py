"""Load eval results into a normalized record list.

Native schema (one JSON object per line, or a JSON array):
  test_id, requirement_id, input, output, verdict ("pass"|"fail"|"error"),
  score (optional float), model, timestamp (ISO 8601).
Adapters: promptfoo `--output results.json` / `.jsonl`,
judge-calibration-kit (`jck run|agree|ab --json`) summaries,
DeepEval test-run files or test case lists (snake_case or camelCase).
"""

from __future__ import annotations

import json
import math
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


def _de(r: dict, snake: str, camel: str, default=None):
    """DeepEval writes pydantic aliases (camelCase) in test-run files; accept both spellings."""
    if snake in r:
        return r[snake]
    return r.get(camel, default)


def _de_rows(data) -> list[dict]:
    """Test cases from a DeepEval test-run file (`{"testCases": [...]}`) or a bare list."""
    if isinstance(data, dict):
        return _de(data, "test_cases", "testCases", []) or []
    return data


def from_deepeval(data) -> list[dict]:
    """Map DeepEval test cases to the native schema.

    Accepts a bare list of test cases or a test-run object with `testCases`, in snake_case or
    camelCase (`actualOutput`, `metricsData`, `additionalMetadata`). A metric that raised an
    error makes the case `verdict=error`; otherwise the case's `success` decides pass/fail.
    `score` is the lowest metric score, since the weakest metric is what failed the case.
    `model` comes from `additional_metadata.model`, not the metric's evaluation (judge) model.
    """
    recs = []
    for i, r in enumerate(_de_rows(data)):
        md = _de(r, "metrics_data", "metricsData", []) or []
        meta = _de(r, "additional_metadata", "additionalMetadata", {}) or {}
        scores = [m["score"] for m in md if isinstance(m.get("score"), (int, float))]
        if any(m.get("error") for m in md):
            verdict = "error"
        else:
            verdict = "pass" if r.get("success") else "fail"
        recs.append({
            "test_id": meta.get("test_id") or r.get("name") or f"de-{i}",
            "requirement_id": meta.get("requirement_id", "UNMAPPED"),
            "input": r.get("input", ""),
            "output": _de(r, "actual_output", "actualOutput", "") or "",
            "verdict": verdict,
            "score": min(scores) if scores else None,
            "model": meta.get("model", "unknown"),
            "timestamp": meta.get("timestamp", "unknown"),
        })
    return recs


DEFAULT_MIN_KAPPA = 0.6


def _jck_record(test_id: str, model: str, side: dict, top: dict, requirement_id: str,
                min_kappa: float) -> dict:
    kappa = side.get("kappa")
    ok = isinstance(kappa, (int, float)) and not math.isnan(kappa) and top.get("n", 0) >= 2
    verdict = ("pass" if kappa >= min_kappa else "fail") if ok else "error"
    metrics = {k: side.get(k) for k in ("raw_agreement", "kappa", "kappa_ci_95",
                                         "judge_pass_rate", "confusion") if k in side}
    return {
        "test_id": test_id,
        "requirement_id": requirement_id,
        "input": json.dumps({"mode": top.get("mode"), "n": top.get("n"),
                             "min_kappa": min_kappa, "synthetic": bool(top.get("synthetic"))},
                            sort_keys=True),
        "output": json.dumps(metrics, sort_keys=True),
        "verdict": verdict,
        "score": kappa if ok else None,
        "model": model,
        "timestamp": top.get("generated_at", "unknown"),
    }


def from_jck(data: dict, requirement_id: str = "UNMAPPED",
             min_kappa: float = DEFAULT_MIN_KAPPA) -> list[dict]:
    """Map a judge-calibration-kit `--json` summary to calibration evidence records.

    jck reports agreement between an LLM judge (or a second rater) and human labels. Each
    calibrated configuration becomes one record whose verdict is `pass` when Cohen's kappa
    meets `min_kappa`, `fail` below it, and `error` when kappa is missing or n < 2. The full
    metrics (agreement, kappa CI, confusion) go in `output` for the reviewer.

    - `mode: judge`       -> one record, test_id `jck-judge`, model = judge name
    - `mode: human_human` -> one record, test_id `jck-human-human`, model = "raterA vs raterB"
    - `mode: ab`          -> two records, `jck-ab-a` and `jck-ab-b`, one per judge config
    """
    if isinstance(data, list):
        if len(data) != 1:
            raise SchemaError("jck summary must be a single JSON object")
        data = data[0]
    mode = data.get("mode")
    args = (requirement_id, min_kappa)
    if mode == "judge":
        return [_jck_record("jck-judge", data.get("judge", "unknown"), data, data, *args)]
    if mode == "human_human":
        model = f"{data.get('rater_a', 'a')} vs {data.get('rater_b', 'b')}"
        return [_jck_record("jck-human-human", model, data, data, *args)]
    if mode == "ab":
        return [_jck_record(f"jck-ab-{side}", data.get(f"judge_{side}", side),
                            data.get(side) or {}, data, *args) for side in ("a", "b")]
    raise SchemaError(f"unknown jck summary mode {mode!r}; expected judge, human_human or ab")


def load_results(path: str | Path, fmt: str = "native", requirement_id: str = "UNMAPPED",
                 min_kappa: float = DEFAULT_MIN_KAPPA) -> list[dict]:
    data = _read(Path(path))
    if fmt == "promptfoo":
        data = from_promptfoo(data)
    elif fmt == "jck":
        data = from_jck(data, requirement_id, min_kappa)
    elif fmt == "deepeval":
        data = from_deepeval(data)
    elif isinstance(data, dict):
        data = [data]
    recs = [normalize(r) for r in data]
    _check_unique_ids(recs)
    return recs


def _check_unique_ids(recs: list[dict]) -> None:
    """Each test_id must appear once, or the traceability matrix and deviation list
    would silently merge two different results under one id."""
    seen: set[str] = set()
    dupes: list[str] = []
    for r in recs:
        tid = str(r["test_id"])
        if tid in seen and tid not in dupes:
            dupes.append(tid)
        seen.add(tid)
    if dupes:
        raise SchemaError(f"duplicate test_id values: {dupes}; each result needs its own id")
