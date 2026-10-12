# Part 11 clause mapping

Clause text checked against eCFR, 21 CFR 11.10 ("Controls for closed systems"), on 2026-10-12:
https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11

**Read this first:** these artifacts can *support* evidence for the clauses below inside a
validated, controlled process. The tool is not itself a Part 11 compliant system. It does not
implement access control (11.10(d), (g)), electronic signatures (Subpart C), or record retention.
This is not legal or regulatory advice. Your QA/regulatory function decides what is sufficient.

| Clause | Text (abridged, quoted) | Artifact | How it supports | Gap / what you still need |
|---|---|---|---|---|
| 11.10(a) | "Validation of systems to ensure accuracy, reliability, consistent intended performance, and the ability to discern invalid or altered records." | `validation_summary.md`, `traceability_matrix.*`, `p11e verify` | Requirement-to-test-to-result evidence for the AI system under test; verify discerns altered log records | Validation of the AI system *and* of this tool itself (IQ/OQ/PQ, plan, protocol) is your process |
| 11.10(b) | "...accurate and complete copies of records in both human readable and electronic form..." | `.md`/`.html` (human readable), `.jsonl`/`.csv`/`manifest.json` (electronic) | Same run exported in both forms, with hashes | Completeness depends on what your harness logs |
| 11.10(c) | "Protection of records to enable their accurate and ready retrieval throughout the records retention period." | `manifest.json` SHA-256 hashes, chain head | Lets you check retrieved copies are unchanged | Storage, backup, and retention (WORM storage, etc.) are out of scope |
| 11.10(e) | "Use of secure, computer-generated, time-stamped audit trails ... Record changes shall not obscure previously recorded information." | `run_log.jsonl` (hash-chained, timestamped) | Computer-generated, time-stamped, tamper-evident record of the run | Tamper-evident, not tamper-proof; anchor the chain head externally. Not a full system audit trail of operator create/modify/delete actions |
| 11.10(f) | "Use of operational system checks to enforce permitted sequencing of steps and events, as appropriate." | Chain `seq` + `run_started`/`run_completed` events | Detects reordered or removed steps in the log | Does not enforce sequencing in the harness itself |
| 11.10(k)(2) | "Revision and change control procedures to maintain an audit trail that documents time-sequenced development and modification of systems documentation." | Config, results, and requirements SHA-256 in the summary | Pins exactly which config/requirements version was tested | Change control lives in your VCS/QMS |

Not addressed: 11.10(d), (g), (h), (i), (j), 11.30 (open systems), Subpart C (electronic signatures).
