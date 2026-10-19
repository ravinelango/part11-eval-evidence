# part11-eval-evidence

Turn an LLM eval run into an audit-ready evidence package: a hash-chained run log, a
requirements traceability matrix, and a one-page validation summary, mapped to the
FDA **21 CFR Part 11** clauses they can support.

> **Status: early, example data only.** The included run is a clearly labeled *synthetic example*.
> No real model evaluations or results are claimed.
>
> **Disclaimer:** this tool generates *supporting evidence*. It is **not** a Part 11 compliant
> system and is **not** legal or regulatory advice.

## Why this matters

Eval tools (promptfoo, DeepEval, Ragas, Inspect) tell you whether a model passes. In regulated
domains like life sciences and healthcare, that isn't enough. A QA reviewer or auditor also asks
which requirement each test verifies, whether the record has been altered, which model and config
were run, who ran it and when, and what failed and how it was dispositioned. Most eval output lives
in dashboards and JSON blobs. This tool packages it the way computerized-system validation
expects to see it.

## Quickstart

```bash
pip install -e ".[dev]"
p11e build --results examples/synthetic_run/results.jsonl \
           --requirements examples/synthetic_run/requirements.yaml \
           --config examples/synthetic_run/config.yaml \
           --dispositions examples/synthetic_run/dispositions.yaml \
           --operator "your.name" --out out
p11e verify out/run_log.jsonl          # exit 0 = chain intact, 1 = tamper detected
p11e head out/run_log.jsonl            # print the chain head to record outside the repo
p11e verify out/run_log.jsonl --expect-head <recorded-sha256>
```

Other inputs: `--format promptfoo` reads promptfoo `-o results.json` (version 3) or
`-o results.jsonl`; put `requirement_id`/`test_id` in each test's `metadata`. Provider errors
become `verdict=error`, and rows with no `test_id` get a stable `pf-t<testIdx>-p<promptIdx>` id.
JSONL rows carry no run timestamp, so prefer the JSON export for the audit trail. Fixtures in
[`examples/promptfoo_synthetic/`](examples/promptfoo_synthetic/) are hand-written synthetic
rows in promptfoo's export shape, not output from a real run. `--format deepeval` reads a
DeepEval test-run object (`testCases`, camelCase) or a bare list of test cases (snake_case); put
`requirement_id`/`test_id`/`model` in `additional_metadata`. A metric error becomes
`verdict=error` and `score` is the lowest metric score. The fixture in
[`examples/deepeval_synthetic/`](examples/deepeval_synthetic/) is hand-written synthetic data in
that shape, not output from a real run.

`--format jck` reads a [judge-calibration-kit](https://github.com/ravinelango/judge-calibration-kit)
`--json` summary (`jck run`, `jck agree` or `jck ab`) as evidence that an LLM judge was
checked against human labels before its verdicts were trusted. Each calibrated configuration
becomes one record mapped to `--requirement-id`, with `verdict=pass` when Cohen's kappa is at
least `--min-kappa` (default 0.6), `fail` below it, and `error` when kappa is missing or n < 2.
Agreement, the kappa CI and the confusion matrix are kept in the record's output. The threshold
is yours to justify; 0.6 is a common starting point, not a regulatory number. Synthetic
summaries from jck's mock judges are in [`examples/jck_synthetic/`](examples/jck_synthetic/).

## Input schema (native)

JSONL, one object per line (or a JSON array):

| field | type | notes |
|---|---|---|
| `test_id` | str | unique test identifier |
| `requirement_id` | str | must match an `id` in the requirements YAML |
| `input` / `output` | str | prompt and model response |
| `verdict` | `pass` \| `fail` \| `error` | |
| `score` | float, optional | |
| `model` | str | model identifier |
| `timestamp` | ISO 8601 | |

Requirements YAML: `label` (optional banner) and `requirements: [{id, description, risk}]`.

Optional dispositions YAML/JSON (`--dispositions`): records how each known failure or gap was
handled. Each entry needs `deviation_id`, `description`, `root_cause`,
`disposition` (`accepted` | `corrected` | `deferred`), `disposition_rationale`, `approver`,
`approved_at` (ISO 8601), plus `requirement_id` and/or `test_id`. See
`examples/synthetic_run/dispositions.yaml` (labeled synthetic).

## Artifacts (`out/`)

| file | purpose |
|---|---|
| `run_log.jsonl` | SHA-256 hash-chained events (run start, each result, run end) |
| `traceability_matrix.csv` / `.md` | requirement → tests → result (PASS / FAIL / NOT TESTED / UNTRACED) |
| `validation_summary.md` / `.html` | one-page summary: operator, time, models, config hash, results by requirement, deviations, dispositions, manual review line |
| `dispositions.csv` / `.json` | present when `--dispositions` is supplied; root cause, disposition, approver |
| `manifest.json` | metadata + SHA-256 of every artifact |

## Part 11 mapping

Clause text checked against [eCFR 21 CFR Part 11](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11). Full table with gaps: [docs/part11-mapping.md](docs/part11-mapping.md).

| Clause | Topic | Supported by |
|---|---|---|
| 11.10(a) | Validation; ability to discern altered records | summary, traceability matrix, `p11e verify` |
| 11.10(b) | Human-readable and electronic copies | `.md`/`.html` + `.jsonl`/`.csv` |
| 11.10(c) | Record protection / accurate retrieval | manifest hashes |
| 11.10(e) | Time-stamped audit trails | hash-chained `run_log.jsonl` |
| 11.10(f) | Sequencing checks | chain `seq`, start/complete events |
| 11.10(k)(2) | Change control of documentation | config/requirements hashes |

## Limitations

- **Tamper-evident, not tamper-proof.** Someone who can rewrite the whole log can rebuild the chain. Record the chain head somewhere independent (QMS record, ticket, signed tag) and check it with `--expect-head`; see [docs/anchoring.md](docs/anchoring.md).
- No access control, user authentication, or Part 11 electronic signatures. Sign-off is a manual line.
- The operator name is self-reported. Timestamps come from the eval harness and the local clock.
- The tool itself would need validation before you rely on it in a GxP context; see the IQ/OQ template in [docs/validation-plan.md](docs/validation-plan.md).
- The HTML report is a minimal printable wrapper.

## Development

```bash
ruff check . && pytest -q
```

## License

MIT © Ravin Elango
