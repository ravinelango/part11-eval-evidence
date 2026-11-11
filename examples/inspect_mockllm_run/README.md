# Inspect AI export from a real offline run (mockllm)

Unlike `examples/inspect_synthetic/` (hand-written), `eval_log.json` here is the
unedited file written by a real `inspect eval` run, so it pins the adapter to
the export shape Inspect actually produces (`inspect_ai` 0.3.289).

**The data is synthetic and the model is Inspect's built-in `mockllm/model`,
which returns a fixed default string without calling any API.** The 1-of-3
pass rate only reflects that canned reply; it says nothing about any real
model.

To regenerate (the log filename and ids will differ):

```bash
pip install inspect-ai
inspect eval examples/inspect_mockllm_run/task.py --model mockllm/model \
    --log-format=json --log-dir /tmp/inspect-logs
```

Samples carry `metadata.requirement_id`, so they map to
`examples/synthetic_run/requirements.yaml`:

```bash
p11e build --format inspect --results examples/inspect_mockllm_run/eval_log.json \
           --requirements examples/synthetic_run/requirements.yaml --out out-mockllm
```

Expected: 3 tests, SYN-1 passes (REQ-001), SYN-2 and SYN-3 fail (REQ-004), and
REQ-002 / REQ-003 are reported NOT TESTED.
