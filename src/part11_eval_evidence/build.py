"""Assemble the evidence package."""

from __future__ import annotations

import csv
import getpass
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import chain, report
from .ingest import load_results


def file_hash(path: Path | None) -> str:
    return chain.sha256(path.read_text(encoding="utf-8")) if path else "none"


def build(results_path, requirements_path, out_dir, operator=None, config_path=None,
          fmt="native", run_id=None, now=None) -> dict:
    results_path, requirements_path = Path(results_path), Path(requirements_path)
    config_path = Path(config_path) if config_path else None
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    results = load_results(results_path, fmt)
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
    events.append({"type": "run_completed", "run_id": run_id, "n_tests": len(results),
                   "n_deviations": len(devs)})
    entries = chain.build_chain(events)
    chain.write_chain(entries, out / "run_log.jsonl")
    meta["chain_head"] = entries[-1]["hash"]

    with (out / "traceability_matrix.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["requirement_id", "description", "risk", "tests", "passed", "total", "status"])
        for m in matrix:
            w.writerow([m["requirement_id"], m["description"], m["risk"], ";".join(m["tests"]),
                        m["passed"], m["total"], m["status"]])
    (out / "traceability_matrix.md").write_text(report.matrix_markdown(matrix) + "\n",
                                                encoding="utf-8")
    md = report.summary_markdown(meta, matrix, devs)
    (out / "validation_summary.md").write_text(md, encoding="utf-8")
    (out / "validation_summary.html").write_text(report.summary_html(md), encoding="utf-8")

    manifest = {name: file_hash(out / name) for name in sorted(
        ["run_log.jsonl", "traceability_matrix.csv", "traceability_matrix.md",
         "validation_summary.md", "validation_summary.html"])}
    (out / "manifest.json").write_text(json.dumps({"meta": meta, "sha256": manifest}, indent=2)
                                       + "\n", encoding="utf-8")
    return {"meta": meta, "matrix": matrix, "deviations": devs}
