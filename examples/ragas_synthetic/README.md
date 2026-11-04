# Ragas import fixture

**SYNTHETIC EXAMPLE - hand-written to mimic a Ragas `EvaluationResult.to_pandas().to_dict("records")`
export, not a real eval run.** `results.json` holds four hand-written rows in that shape
(`user_input`, `response`, `retrieved_contexts`, `reference`, plus metric columns): 2 pass,
1 failure (low faithfulness after a synthetic identifier leaked into the response) and 1 metric
error (`null` scores when the judge call failed). The `--format ragas` adapter also accepts the
same rows as JSONL, and a bare list of score-only dicts if you only dumped `result.scores`.

Map rows to requirements with a `metadata` object (or flat `test_id` / `requirement_id` /
`model` / `timestamp` columns):

```python
# after result = evaluate(...)
rows = result.to_pandas().to_dict("records")
# attach ids the audit trail needs, then json.dump(rows, ...)
```

```bash
p11e build --format ragas --results examples/ragas_synthetic/results.json \
           --requirements examples/synthetic_run/requirements.yaml --out out-rg
# optional: --min-score 0.7 (default) sets the pass threshold on the weakest metric
```
