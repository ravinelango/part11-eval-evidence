# Inspect AI import fixture

**SYNTHETIC EXAMPLE - hand-written to mimic an Inspect AI eval-log JSON export
(`inspect eval --log-format=json` / `inspect log dump`), not a real eval run.**
`eval_log.json` holds four hand-written samples in the documented EvalLog /
EvalSample shape (`version`, `status`, `eval`, `samples` with `id`, `input`,
`output`, `scores`, `metadata`, `error`): 2 pass (numeric `1.0` and Inspect
`C`/`I`-style string), 1 failure (score `0.0` after a synthetic identifier
leaked into the response) and 1 sample error (provider timeout, empty scores).

The `--format inspect` adapter also accepts a bare list of samples or a
`{"samples": [...]}` wrapper. Map samples to requirements with sample
`metadata`:

```python
# after log = read_eval_log(...) or inspect log dump
# attach ids the audit trail needs on each sample.metadata, then json.dump
```

```bash
p11e build --format inspect --results examples/inspect_synthetic/eval_log.json \
           --requirements examples/synthetic_run/requirements.yaml --out out-ins
# optional: --min-score 0.7 (default) sets the pass threshold on the weakest score
```
