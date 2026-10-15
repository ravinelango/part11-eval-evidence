"""Assemble the evidence package."""

from __future__ import annotations

import csv
import getpass
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import chain, report
from .dispositions import load_dispositions, match_dispositions
from .ingest import load_results


def file_hash(path: Path | None) -> str:
    return chain.sha256(path.read_text(encoding="utf-8")) if path else "none"


def build(results_path, requirements_path, out_dir, operator=None, config_path=None,
          fmt="native", run_id=None, now=None, dispositions_path=None,
          ingest_opts=None) -> dict:
    results_path, requirements_path = Path(results_path), Path(requirements_path)
    config_path = Path(config_path) if config_path else None
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    results = load_results(results_path, fmt, **(ingest_opts or {}))
    req_doc = yaml.safe_load(requirements_path.read_text(encoding="utf-8")) or {}
    requirements = req_doc.get("requirements", [])
    generated = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    operator = operator or getpass.getuser()
    run_id = run_id or f"run-{generated.replace(':', '').replace('-', '')}"

    meta = {
        "run_id": run_id, "operator": operator, "generated_at": generated,
        "models": sorted({r["model"] for r in results}),
        "config_hash": file_hash(config_path),
        "results_hash": file_hash(results_path),
        "requirements_hash": file_hash(requirements_path),
        "n_tests": len(results), "label": req_doc.get("label", ""),
    }

    events = [{"type": "run_started", "run_id": run_id, "operator": operator,
               "at": generated, "config_hash": meta["config_hash"],
               "results_hash": meta["results_hash"],
               "requirements_hash": meta["requirements_hash"]}]
    events += [{"type": "test_result", **r} for r in results]
    matrix = report.trace_matrix(requirements, results)
    devs = report.deviations(results, matrix)
    dispositions = match_dispositions(
        load_dispositions(dispositions_path), results, matrix)
    events.append({"type": "run_completed", "run_id": run_id, "n_tests": len(results),
                   "n_deviations": len(devs), "n_dispositions": len(dispositions)})
    entries = chain.build_chain(events)
    chain.write_chain(entries, out / "run_log.jsonl")
    meta["chain_head"] = entries[-1]["hash"]
    meta["n_dispositions"] = len(dispositions)

    with (out / "traceability_matrix.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["requirement_id", "description", "risk", "tests", "passed", "total", "status"])
        for m in matrix:
            w.writerow([m["requirement_id"], m["description"], m["risk"], ";".join(m["tests"]),
                        m["passed"], m["total"], m["status"]])
    (out / "traceability_matrix.md").write_text(report.matrix_markdown(matrix) + "\n",
                                                encoding="utf-8")
    if dispositions:
        with (out / "dispositions.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["deviation_id", "requirement_id", "test_id", "disposition",
                        "approver", "approved_at", "covers_known_issue"])
            for d in dispositions:
                w.writerow([d["deviation_id"], d["requirement_id"], d["test_id"],
                            d["disposition"], d["approver"], d["approved_at"],
                            d["covers_known_issue"]])
        (out / "dispositions.json").write_text(
            json.dumps(dispositions, indent=2) + "\n", encoding="utf-8")
    md = report.summary_markdown(meta, matrix, devs, dispositions)
    (out / "validation_summary.md").write_text(md, encoding="utf-8")
    html_doc = report.summary_html_report(meta, matrix, devs, dispositions)
    (out / "validation_summary.html").write_text(html_doc, encoding="utf-8")

    artifact_names = [
        "run_log.jsonl", "traceability_matrix.csv", "traceability_matrix.md",
        "validation_summary.md", "validation_summary.html",
    ]
    if dispositions:
        artifact_names += ["dispositions.csv", "dispositions.json"]
    manifest = {name: file_hash(out / name) for name in sorted(artifact_names)}
    (out / "manifest.json").write_text(json.dumps({"meta": meta, "sha256": manifest}, indent=2)
                                       + "\n", encoding="utf-8")
    return {"meta": meta, "matrix": matrix, "deviations": devs, "dispositions": dispositions}
