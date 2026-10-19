# DeepEval import fixture

**SYNTHETIC EXAMPLE - hand-written to mimic the shape of a DeepEval test-run file, not a real
eval run.** `test_run.json` holds four hand-written test cases in DeepEval's camelCase
(`testCases`, `actualOutput`, `metricsData`, `additionalMetadata`): 2 pass, 1 failure (a
synthetic identifier repeated in the output) and 1 metric error (judge call failed). The
`--format deepeval` adapter also accepts a bare list of test cases in snake_case.

Map cases to requirements with `additional_metadata`:

```python
LLMTestCase(input=..., actual_output=...,
            additional_metadata={"test_id": "DE-003", "requirement_id": "REQ-003",
                                 "model": "my-model", "timestamp": "2026-01-01T10:00:00Z"})
```

```bash
p11e build --format deepeval --results examples/deepeval_synthetic/test_run.json \
           --requirements examples/synthetic_run/requirements.yaml --out out-de
```
