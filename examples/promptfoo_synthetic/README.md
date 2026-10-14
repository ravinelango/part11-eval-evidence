# promptfoo import fixtures

**SYNTHETIC EXAMPLE - hand-written to mimic promptfoo's export shape, not a real eval run.** Both files hold the same four hand-written rows: 2 pass, 1 assertion failure
(synthetic PHI leak) and 1 provider error. They follow the shape of `promptfoo eval -o results.json`
(version 3) and `-o results.jsonl`. Map rows to requirements with test `metadata`:

```yaml
tests:
  - vars: { q: "Which clause covers audit trails?" }
    metadata: { test_id: PF-001, requirement_id: REQ-001 }
```

```bash
p11e build --format promptfoo --results examples/promptfoo_synthetic/results.json \
           --requirements examples/synthetic_run/requirements.yaml --out out-pf
```
