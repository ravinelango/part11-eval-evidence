"""Load eval results into a normalized record list.

Native schema (one JSON object per line, or a JSON array):
  test_id, requirement_id, input, output, verdict ("pass"|"fail"|"error"),
  score (optional float), model, timestamp (ISO 8601).
Adapters: promptfoo `--output results.json` / `.jsonl`,
judge-calibration-kit (`jck run|agree|ab --json`) summaries,
DeepEval test-run files or test case lists (snake_case or camelCase),
Ragas `EvaluationResult.to_pandas().to_dict("records")` / JSONL rows,
Inspect AI eval-log JSON (`--log-format=json` / `inspect log dump`) or sample lists.
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
    # Real exports also fill `error` with the assertion message when failureReason == 1,
    # so `error` only means a provider/runtime error when failureReason is absent.
    reason = r.get("failureReason")
    if reason == _PF_ERROR or (reason is None and r.get("error")):
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
    re-exported maps to the same ids. One test run against several prompts or providers
    yields one row per column with the same metadata test_id; those ids get a `/p<promptIdx>`
    suffix so each column stays a separate result.
    """
    rows, run_ts = _pf_rows(data)
    metas = []
    for r in rows:
        tc = r.get("testCase") or {}
        metas.append({**(r.get("metadata") or {}), **(tc.get("metadata") or {})})
    counts: dict[str, int] = {}
    for meta in metas:
        if "test_id" in meta:
            counts[meta["test_id"]] = counts.get(meta["test_id"], 0) + 1
    recs = []
    for i, (r, meta) in enumerate(zip(rows, metas, strict=True)):
        tc = r.get("testCase") or {}
        t_idx, p_idx = r.get("testIdx", i), r.get("promptIdx", 0)
        tid = meta.get("test_id", f"pf-t{t_idx}-p{p_idx}")
        if counts.get(tid, 0) > 1:
            tid = f"{tid}/p{p_idx}"
        recs.append({
            "test_id": tid,
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


DEFAULT_MIN_SCORE = 0.7

# Columns that are sample fields / ids, not Ragas metric scores.
_RAGAS_NON_METRIC = {
    "user_input", "question", "response", "answer", "retrieved_contexts", "contexts",
    "reference", "ground_truth", "reference_contexts", "reference_context",
    "rubrics", "metadata", "test_id", "requirement_id", "model", "timestamp", "error",
}


def _ragas_rows(data) -> list[dict]:
    """Records from a to_pandas().to_dict("records") dump, a scores-only list, or JSONL."""
    if isinstance(data, dict):
        if "scores" in data and isinstance(data["scores"], list):
            return data["scores"]
        raise SchemaError("ragas export must be a list of records or {\"scores\": [...]}")
    return data


def _ragas_metrics(row: dict) -> list[float | None]:
    """Collect metric values: prefer known float columns outside the sample/id set."""
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    skip = _RAGAS_NON_METRIC | set(meta)
    out: list[float | None] = []
    for k, v in row.items():
        if k in skip:
            continue
        if v is None:
            out.append(None)
        elif isinstance(v, bool):
            continue
        elif isinstance(v, (int, float)):
            out.append(float(v))
    return out


def from_ragas(data, min_score: float = DEFAULT_MIN_SCORE) -> list[dict]:
    """Map Ragas evaluation rows to the native schema.

    Accepts the list produced by `EvaluationResult.to_pandas().to_dict("records")` (sample
    columns plus metric columns), the same rows as JSONL, or a `{"scores": [...]}` object.
    `requirement_id` / `test_id` / `model` / `timestamp` come from a `metadata` object or
    matching top-level fields. `score` is the lowest metric; `verdict` is `error` when any
    metric is null or the row carries `error`, otherwise `pass` when every metric is at least
    `min_score` and `fail` below it.
    """
    recs = []
    for i, row in enumerate(_ragas_rows(data)):
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        metrics = _ragas_metrics(row)
        explicit_err = row.get("error") or meta.get("error")
        if explicit_err or not metrics or any(m is None for m in metrics):
            verdict = "error"
            score = None
        else:
            score = min(metrics)  # type: ignore[arg-type]
            verdict = "pass" if score >= min_score else "fail"
        recs.append({
            "test_id": meta.get("test_id") or row.get("test_id") or f"rg-{i}",
            "requirement_id": meta.get("requirement_id") or row.get("requirement_id", "UNMAPPED"),
            "input": row.get("user_input") or row.get("question") or "",
            "output": row.get("response") or row.get("answer") or "",
            "verdict": verdict,
            "score": score,
            "model": meta.get("model") or row.get("model", "unknown"),
            "timestamp": meta.get("timestamp") or row.get("timestamp", "unknown"),
        })
    return recs



def _inspect_samples(data) -> tuple[list[dict], dict]:
    """Return (samples, eval_spec) from an EvalLog object, {samples: [...]}, or bare list."""
    if isinstance(data, list):
        return data, {}
    if isinstance(data, dict):
        if "samples" in data:
            samples = data.get("samples") or []
            if not isinstance(samples, list):
                raise SchemaError("inspect export samples must be a list")
            return samples, data.get("eval") or {}
        raise SchemaError(
            'inspect export must be an EvalLog object with "samples", '
            'a {"samples": [...]} wrapper, or a bare list of samples'
        )
    raise SchemaError("inspect export must be a JSON object or array")


def _inspect_input(sample: dict) -> str:
    inp = sample.get("input", "")
    if isinstance(inp, str):
        return inp
    return json.dumps(inp, sort_keys=True)


def _inspect_output(sample: dict) -> str:
    out = sample.get("output") or {}
    if isinstance(out, str):
        return out
    if out.get("completion"):
        return str(out["completion"])
    choices = out.get("choices") or []
    if choices:
        msg = (choices[0] or {}).get("message") or {}
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        return json.dumps(content, sort_keys=True) if content else ""
    return ""


def _inspect_score_number(value) -> float | None:
    """Map a Score.value (or nested dict leaf) to a float in [0, 1] when possible."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    if isinstance(value, str):
        key = value.strip().lower()
        if key in {"c", "correct", "pass", "true", "yes"}:
            return 1.0
        if key in {"i", "incorrect", "fail", "false", "no"}:
            return 0.0
        if key in {"p", "partial"}:
            return 0.5
        try:
            return float(value)
        except ValueError:
            return None
    if isinstance(value, dict):
        for k in ("accuracy", "correct", "score", "value"):
            if k in value:
                return _inspect_score_number(value[k])
        for v in value.values():
            n = _inspect_score_number(v)
            if n is not None:
                return n
        return None
    return None


def from_inspect(data, min_score: float = DEFAULT_MIN_SCORE) -> list[dict]:
    """Map Inspect AI eval-log / sample JSON to the native schema.

    Accepts a full EvalLog JSON object (`inspect eval --log-format=json` or
    `inspect log dump`), a `{"samples": [...]}` wrapper, or a bare list of
    EvalSample-like objects. `requirement_id` / `test_id` / `model` /
    `timestamp` come from sample `metadata` when present; otherwise `test_id`
    falls back to the sample `id` (with `/e<epoch>` when epoch > 1), `model`
    and `timestamp` fall back to `eval.model` / `eval.created`.

    `verdict` is `error` when the sample has an `error` field or any score
    value cannot be read as a number; otherwise `pass` when every score is at
    least `min_score` and `fail` below it. `score` is the lowest numeric score.
    """
    samples, ev = _inspect_samples(data)
    recs = []
    for i, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise SchemaError(f"inspect sample at index {i} must be an object")
        meta = sample.get("metadata") if isinstance(sample.get("metadata"), dict) else {}
        sid = sample.get("id", i)
        epoch = sample.get("epoch") or 1
        default_tid = f"{sid}/e{epoch}" if epoch and int(epoch) > 1 else str(sid)
        err = sample.get("error")
        scores = sample.get("scores") or {}
        nums: list[float | None] = []
        if isinstance(scores, dict):
            for sc in scores.values():
                val = sc.get("value") if isinstance(sc, dict) else sc
                nums.append(_inspect_score_number(val))
        if err:
            verdict, score = "error", None
        elif not nums or any(n is None for n in nums):
            verdict, score = "error", None
        else:
            score = min(nums)  # type: ignore[arg-type]
            verdict = "pass" if score >= min_score else "fail"
        out_model = (sample.get("output") or {})
        model = (
            meta.get("model")
            or (out_model.get("model") if isinstance(out_model, dict) else None)
            or ev.get("model")
            or "unknown"
        )
        recs.append({
            "test_id": meta.get("test_id") or default_tid,
            "requirement_id": meta.get("requirement_id", "UNMAPPED"),
            "input": _inspect_input(sample),
            "output": _inspect_output(sample),
            "verdict": verdict,
            "score": score,
            "model": model,
            "timestamp": meta.get("timestamp") or ev.get("created") or "unknown",
        })
    return recs


def load_results(path: str | Path, fmt: str = "native", requirement_id: str = "UNMAPPED",
                 min_kappa: float = DEFAULT_MIN_KAPPA,
                 min_score: float = DEFAULT_MIN_SCORE) -> list[dict]:
    data = _read(Path(path))
    if fmt == "promptfoo":
        data = from_promptfoo(data)
    elif fmt == "jck":
        data = from_jck(data, requirement_id, min_kappa)
    elif fmt == "deepeval":
        data = from_deepeval(data)
    elif fmt == "ragas":
        data = from_ragas(data, min_score)
    elif fmt == "inspect":
        data = from_inspect(data, min_score)
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
