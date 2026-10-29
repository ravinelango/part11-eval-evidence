# Validation plan for part11-eval-evidence (IQ / OQ template)

**Status:** template and example protocol only. This document describes how *you*
could qualify **this tool** before relying on it in a controlled process. It is
**not** a completed IQ/OQ/PQ package, **not** evidence that the tool is validated,
and **not** regulatory advice. Your QA function owns acceptance criteria, approvals,
and whether any of this is sufficient.

Clause context: 21 CFR 11.10(a) asks for validation of systems used to create,
modify, or maintain electronic records. The [Part 11 mapping](part11-mapping.md)
already notes that validating *this packaging tool itself* is out of band of a
single eval run. Use this plan (or your site template) for that step.

## Scope

**In scope**

- Installation of a pinned release or commit of `part11-eval-evidence`
- Correct packaging of native JSONL, promptfoo, and judge-calibration-kit inputs
  into the documented artifacts
- Integrity checks (`p11e verify`, optional `--expect-head`)
- Traceability (requirement → test → result) and disposition wiring

**Out of scope**

- Validation of the AI / LLM system under test (separate protocol)
- Access control, electronic signatures, record retention / WORM storage
- Performance or load of upstream eval harnesses
- Any claim that synthetic fixtures represent real clinical or GxP data

## Roles (fill in for a real execution)

| Role | Responsibility |
|---|---|
| Author | Drafts protocol and expected results |
| Executor | Runs IQ/OQ steps and attaches evidence |
| Reviewer / QA | Approves protocol and report; decides go/no-go |

## Installation qualification (IQ)

Purpose: show the installed build matches what you intended to qualify.

| Step | Action | Expected result | Evidence |
|---|---|---|---|
| IQ-1 | Record git commit SHA (or release tag), `p11e --version`, and `pip show` / lockfile hashes | SHA and package version match the approved build | Screenshot or log attached to the report |
| IQ-2 | Confirm Python version is in the supported set (see CI / `pyproject.toml`) | Version matches the matrix you approved | `python --version` log |
| IQ-3 | Install with the documented command (`pip install -e ".[dev]"` or pinned wheel) | `p11e --help` exits 0 | Command transcript |
| IQ-4 | Confirm required entry points resolve (`p11e build`, `verify`, `head`) | Each prints help or usage without import errors | Transcript |

## Operational qualification (OQ)

Purpose: show the installed build behaves as specified on **controlled synthetic
inputs**. Do not substitute real production eval output until IQ/OQ pass and your
change control allows it.

The repository's synthetic fixtures are labeled as such:

- `examples/synthetic_run/` — native JSONL + requirements + dispositions
- `examples/promptfoo_synthetic/` — hand-written promptfoo-shaped rows
- `examples/jck_synthetic/` — judge-calibration-kit JSON summaries from mock judges

| Step | Action | Expected result | Evidence |
|---|---|---|---|
| OQ-1 | `p11e build` on `examples/synthetic_run/` with a known operator string | Exit 0; `out/` contains `run_log.jsonl`, traceability matrix, validation summary, manifest | Command transcript + artifact listing |
| OQ-2 | `p11e verify out/run_log.jsonl` | Exit 0 (chain intact) | Transcript |
| OQ-3 | Record `p11e head out/run_log.jsonl`, then `verify --expect-head <that value>` | Exit 0 | Transcript |
| OQ-4 | Flip one byte in a copy of `run_log.jsonl` and re-verify | Exit non-zero (tamper detected) | Transcript |
| OQ-5 | Confirm every `requirement_id` in results appears in the matrix with the expected rollup | Matrix rows match the fixture's known pass/fail/error pattern | Annotated matrix or test log |
| OQ-6 | Build with `--dispositions` on the synthetic dispositions file | Summary and disposition exports list each seeded deviation with approver fields | Artifacts |
| OQ-7 | Build with `--format promptfoo` on a synthetic fixture | Rows map; provider errors become `verdict=error` where seeded | Transcript |
| OQ-8 | Build with `--format jck` on a synthetic jck summary | Kappa vs `--min-kappa` drives pass/fail; missing kappa → error | Transcript |
| OQ-9 | Run the project's automated tests (`ruff check` + `pytest`) on the qualified build | All tests pass on the pinned commit | CI link or local transcript |

Automated tests in `tests/` are **candidates** for OQ evidence when executed on
the same pinned build under change control. Passing CI on `main` is not by itself
a completed OQ.

## Performance qualification (PQ)

PQ is site-specific: re-run a subset of OQ (at least OQ-1..OQ-4 and one importer
you actually use) on a representative *real* eval export inside your controlled
environment, with your retention and anchoring process
([anchoring.md](anchoring.md)). This template does not prescribe PQ acceptance
numbers.

## Deviations

Record any step that does not meet its expected result: ID, description, root
cause, disposition (`accepted` / `corrected` / `deferred`), approver, date. You
may reuse this tool's disposition file shape for consistency, or your QMS form.

## Report contents (minimum)

1. Protocol ID / version and the git SHA qualified
2. Executor and reviewer names, dates
3. IQ and OQ step table with pass/fail and evidence pointers
4. Deviations and dispositions
5. Go / no-go decision for using this build to package eval evidence

## Traceability to repository tests (informative)

| OQ theme | Closest automated coverage (may change) |
|---|---|
| Native build + chain verify | `tests/test_core.py` build/verify cases |
| Tamper detection | verify failure cases in the same module |
| promptfoo import | promptfoo fixture tests |
| jck import | jck summary tests |
| Dispositions in summary | disposition wiring tests |

Re-confirm the mapping when you pin a commit; do not cite this table as frozen
validation without re-execution.

## Labels

All example commands above use **synthetic** fixtures shipped in this repository.
Do not present their outputs as clinical, manufacturing, or regulatory results.
