import json
from pathlib import Path

import pytest

from part11_eval_evidence import chain
from part11_eval_evidence.build import build
from part11_eval_evidence.cli import main
from part11_eval_evidence.dispositions import (
    DispositionError,
    load_dispositions,
    normalize_disposition,
)
from part11_eval_evidence.ingest import (
    SchemaError,
    from_deepeval,
    from_jck,
    from_promptfoo,
    load_results,
    normalize,
)

EX = Path(__file__).parent.parent / "examples" / "synthetic_run"


def _build(tmp_path):
    return build(EX / "results.jsonl", EX / "requirements.yaml", tmp_path, operator="tester",
                 config_path=EX / "config.yaml", run_id="test-run", now="2026-01-01T00:00:00Z")


def test_load_example():
    assert len(load_results(EX / "results.jsonl")) == 5


def test_schema_rejects_missing_and_bad_verdict():
    with pytest.raises(SchemaError):
        normalize({"test_id": "x"})
    rec = dict(test_id="x", requirement_id="R", input="", output="", verdict="maybe",
               model="m", timestamp="t")
    with pytest.raises(SchemaError):
        normalize(rec)


def test_chain_roundtrip_and_tamper(tmp_path):
    entries = chain.build_chain([{"a": 1}, {"b": 2}, {"c": 3}])
    p = tmp_path / "log.jsonl"
    chain.write_chain(entries, p)
    assert chain.verify_chain(p)[0]
    lines = p.read_text().splitlines()
    lines[1] = lines[1].replace('"b":2', '"b":3')
    p.write_text("\n".join(lines) + "\n")
    ok, probs = chain.verify_chain(p)
    assert not ok and any("hash mismatch" in x for x in probs)


def test_chain_detects_deletion(tmp_path):
    p = tmp_path / "log.jsonl"
    chain.write_chain(chain.build_chain([{"a": 1}, {"b": 2}, {"c": 3}]), p)
    lines = p.read_text().splitlines()
    p.write_text(lines[0] + "\n" + lines[2] + "\n")
    assert not chain.verify_chain(p)[0]



@pytest.mark.parametrize("bad", ["[1, 2]", "null", '"text"', "42"])
def test_chain_reports_non_object_lines_instead_of_crashing(tmp_path, bad):
    p = tmp_path / "log.jsonl"
    chain.write_chain(chain.build_chain([{"a": 1}, {"b": 2}]), p)
    p.write_text(p.read_text() + bad + "\n")
    ok, probs = chain.verify_chain(p)
    assert not ok and any("line 3: not a log entry" in x for x in probs)
    assert chain.read_head(p) is None

def test_build_matrix_and_deviations(tmp_path):
    r = _build(tmp_path)
    status = {m["requirement_id"]: m["status"] for m in r["matrix"]}
    assert status == {"REQ-001": "FAIL", "REQ-002": "PASS", "REQ-003": "PASS",
                      "REQ-004": "NOT TESTED"}
    assert len(r["deviations"]) == 2
    for f in ["run_log.jsonl", "traceability_matrix.csv", "validation_summary.md",
              "validation_summary.html", "manifest.json"]:
        assert (tmp_path / f).exists()
    md = (tmp_path / "validation_summary.md").read_text()
    assert "SYNTHETIC EXAMPLE" in md and "not legal or regulatory advice" in md


def test_cli_verify_exit_codes(tmp_path, capsys):
    _build(tmp_path)
    log = tmp_path / "run_log.jsonl"
    assert main(["verify", str(log)]) == 0
    log.write_text(log.read_text().replace('"verdict":"fail"', '"verdict":"pass"'))
    assert main(["verify", str(log)]) == 1


def test_anchor_catches_full_rewrite_and_truncation(tmp_path):
    p = tmp_path / "log.jsonl"
    chain.write_chain(chain.build_chain([{"a": 1}, {"b": 2}, {"c": 3}]), p)
    anchored = chain.read_head(p)
    assert chain.verify_against_anchor(p, anchored)[0]
    # A rebuilt chain is internally valid, so only the anchor exposes it.
    chain.write_chain(chain.build_chain([{"a": 1}, {"b": 99}, {"c": 3}]), p)
    assert chain.verify_chain(p)[0]
    ok, probs = chain.verify_against_anchor(p, anchored)
    assert not ok and any("anchored head" in x for x in probs)
    # Dropping the last entry also leaves a valid chain with a different head.
    chain.write_chain(chain.build_chain([{"a": 1}, {"b": 2}]), p)
    assert not chain.verify_against_anchor(p, anchored)[0]


def test_cli_head_and_expect_head(tmp_path, capsys):
    r = _build(tmp_path)
    log = str(tmp_path / "run_log.jsonl")
    assert main(["head", log]) == 0
    assert capsys.readouterr().out.strip() == r["meta"]["chain_head"]
    assert main(["verify", log, "--expect-head", r["meta"]["chain_head"].upper()]) == 0
    assert main(["verify", log, "--expect-head", "0" * 64]) == 1


def test_cli_missing_log_and_bad_anchor(tmp_path, capsys):
    missing = str(tmp_path / "nope.jsonl")
    assert main(["verify", missing]) == 2
    assert main(["head", missing]) == 2
    assert "No such log file" in capsys.readouterr().err
    _build(tmp_path)
    log = str(tmp_path / "run_log.jsonl")
    # A truncated or pasted-wrong anchor is a usage error, not a tamper finding.
    assert main(["verify", log, "--expect-head", "abc123"]) == 2
    assert "64-character" in capsys.readouterr().err


def test_promptfoo_adapter():
    data = {"createdAt": "2026-01-01", "results": {"results": [
        {"vars": {"q": "hi"}, "response": {"output": "hello"}, "success": True, "score": 1,
         "provider": {"id": "openai:x"},
         "testCase": {"metadata": {"requirement_id": "REQ-9", "test_id": "PF-1"}}}]}}
    recs = [normalize(r) for r in from_promptfoo(data)]
    assert recs[0]["requirement_id"] == "REQ-9" and recs[0]["verdict"] == "pass"
    assert json.loads(recs[0]["input"]) == {"q": "hi"}


def test_html_report_is_structured_and_escaped():
    from part11_eval_evidence.report import summary_html_report

    meta = {"run_id": "r<1>", "operator": "op", "generated_at": "t", "models": ["m"],
            "config_hash": "c", "results_hash": "r", "requirements_hash": "q",
            "chain_head": "h", "n_tests": 1, "label": "SYNTHETIC"}
    matrix = [{"requirement_id": "R1", "description": "<script>x</script>", "risk": "high",
               "tests": ["T1"], "passed": 0, "total": 1, "status": "FAIL"}]
    out = summary_html_report(meta, matrix, ["Test T1 (R1): verdict FAIL"])
    assert "<table>" in out and "class='FAIL'" in out and "SYNTHETIC" in out
    assert "<script>x" not in out and "&lt;script&gt;" in out and "r&lt;1&gt;" in out


def test_load_synthetic_dispositions():
    rows = load_dispositions(EX / "dispositions.yaml")
    assert len(rows) == 2
    assert rows[0]["deviation_id"] == "DEV-001"
    assert rows[0]["disposition"] == "corrected"
    assert rows[0]["test_id"] == "T-002"
    assert rows[1]["disposition"] == "deferred"
    assert "SYNTHETIC" in rows[0]["description"]


def test_disposition_schema_rejects_bad_values():
    with pytest.raises(DispositionError):
        normalize_disposition({"deviation_id": "D"})
    bad = dict(
        deviation_id="D1", requirement_id="R1", description="x", root_cause="y",
        disposition="ignored", disposition_rationale="z",
        approver="a", approved_at="2026-01-01T00:00:00Z",
    )
    with pytest.raises(DispositionError):
        normalize_disposition(bad)


def test_build_includes_dispositions_in_reports(tmp_path):
    r = build(
        EX / "results.jsonl", EX / "requirements.yaml", tmp_path, operator="tester",
        config_path=EX / "config.yaml", run_id="test-run", now="2026-01-01T00:00:00Z",
        dispositions_path=EX / "dispositions.yaml",
    )
    assert len(r["dispositions"]) == 2
    assert all(d["covers_known_issue"] for d in r["dispositions"])
    assert (tmp_path / "dispositions.csv").exists()
    assert (tmp_path / "dispositions.json").exists()
    md = (tmp_path / "validation_summary.md").read_text()
    html = (tmp_path / "validation_summary.html").read_text()
    assert "## Deviation dispositions" in md
    assert "DEV-001" in md and "corrected" in md
    assert "DEV-001" in html and "deferred" in html
    assert "Deviation dispositions" in html


def test_cli_build_with_dispositions(tmp_path, capsys):
    out = tmp_path / "out"
    rc = main([
        "build",
        "--results", str(EX / "results.jsonl"),
        "--requirements", str(EX / "requirements.yaml"),
        "--config", str(EX / "config.yaml"),
        "--dispositions", str(EX / "dispositions.yaml"),
        "--operator", "tester",
        "--run-id", "cli-disp",
        "--out", str(out),
    ])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "2 dispositions" in printed
    assert "DEV-002" in (out / "validation_summary.md").read_text()


PF_DIR = Path(__file__).parent.parent / "examples" / "promptfoo_synthetic"


def test_promptfoo_v3_json_and_jsonl_fixtures_agree():
    full = load_results(PF_DIR / "results.json", fmt="promptfoo")
    lines = load_results(PF_DIR / "results.jsonl", fmt="promptfoo")
    assert [r["verdict"] for r in full] == ["pass", "pass", "fail", "error"]
    assert [r["test_id"] for r in full] == [r["test_id"] for r in lines]
    assert [r["verdict"] for r in full] == [r["verdict"] for r in lines]
    assert full[0]["timestamp"] == "2026-01-01T10:00:00Z"
    assert lines[0]["timestamp"] == "unknown"  # JSONL rows carry no run timestamp
    assert full[0]["model"] == "example-model-v1"
    assert full[3]["output"] == ""


def test_promptfoo_rows_without_metadata_get_stable_ids():
    rows = [{"testIdx": 3, "promptIdx": 1, "success": False, "provider": "echo",
             "response": {"output": "x"}}]
    rec = normalize(from_promptfoo(rows)[0])
    assert rec["test_id"] == "pf-t3-p1" and rec["requirement_id"] == "UNMAPPED"
    assert rec["model"] == "echo" and rec["verdict"] == "fail"


def test_build_from_promptfoo_fixture(tmp_path):
    r = build(PF_DIR / "results.json", EX / "requirements.yaml", tmp_path, fmt="promptfoo",
              run_id="pf-test", now="2026-01-01T00:00:00Z")
    assert r["meta"]["n_tests"] == 4
    assert "Test PF-003 (REQ-003): verdict FAIL" in r["deviations"]
    assert "Test PF-004 (REQ-004): verdict ERROR" in r["deviations"]


JCK_DIR = Path(__file__).parent.parent / "examples" / "jck_synthetic"


def test_jck_judge_summary_maps_to_one_record():
    (rec,) = load_results(JCK_DIR / "judge_summary.json", fmt="jck",
                          requirement_id="REQ-JUDGE-001")
    assert rec["test_id"] == "jck-judge" and rec["model"] == "mock"
    assert rec["requirement_id"] == "REQ-JUDGE-001"
    assert rec["verdict"] == "fail" and rec["score"] == pytest.approx(0.5833, abs=1e-4)
    assert json.loads(rec["input"]) == {"min_kappa": 0.6, "mode": "judge", "n": 10,
                                        "synthetic": True}
    out = json.loads(rec["output"])
    assert out["raw_agreement"] == 0.8 and out["confusion"]["fail"]["fail"] == 3
    assert load_results(JCK_DIR / "judge_summary.json", fmt="jck",
                        min_kappa=0.5)[0]["verdict"] == "pass"


def test_jck_ab_and_human_human_summaries():
    a, b = load_results(JCK_DIR / "ab_summary.json", fmt="jck")
    assert (a["test_id"], a["model"], a["verdict"]) == ("jck-ab-a", "mock", "fail")
    assert (b["test_id"], b["model"], b["verdict"]) == ("jck-ab-b", "mock:strict", "pass")
    assert a["requirement_id"] == "UNMAPPED" and b["timestamp"] == "unknown"
    (h,) = load_results(JCK_DIR / "agree_summary.json", fmt="jck", min_kappa=0.4)
    assert h["test_id"] == "jck-human-human" and h["model"] == "human_a vs human_b"
    assert h["verdict"] == "pass"


def test_jck_degenerate_and_unknown_summaries():
    rec = normalize(from_jck({"mode": "judge", "judge": "x", "n": 1, "kappa": 1.0})[0])
    assert rec["verdict"] == "error" and rec["score"] is None
    rec = normalize(from_jck({"mode": "judge", "judge": "x", "n": 5, "kappa": float("nan")})[0])
    assert rec["verdict"] == "error"
    with pytest.raises(SchemaError):
        from_jck({"mode": "pairwise"})
    with pytest.raises(SchemaError):
        from_jck([{"mode": "judge"}, {"mode": "judge"}])


def test_cli_build_from_jck_ab_fixture(tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["build", "--format", "jck", "--results", str(JCK_DIR / "ab_summary.json"),
                 "--requirements", str(JCK_DIR / "requirements.yaml"),
                 "--requirement-id", "REQ-JUDGE-001", "--operator", "tester",
                 "--out", str(out)]) == 0
    assert "2 tests, 1 deviations" in capsys.readouterr().out
    matrix = (out / "traceability_matrix.csv").read_text()
    assert "REQ-JUDGE-001" in matrix and "jck-ab-a;jck-ab-b" in matrix and "FAIL" in matrix
    assert main(["verify", str(out / "run_log.jsonl")]) == 0


def test_deepeval_camelcase_test_run_and_metric_errors():
    run = {"testCases": [
        {"name": "case-1", "input": "q1", "actualOutput": "a1", "success": True,
         "metricsData": [{"name": "Faithfulness", "score": 0.9, "success": True},
                         {"name": "Relevancy", "score": 0.7, "success": True}],
         "additionalMetadata": {"requirement_id": "REQ-001", "model": "m1"}},
        {"name": "case-2", "input": "q2", "actualOutput": "a2", "success": False,
         "metricsData": [{"name": "Faithfulness", "score": None, "success": False,
                          "error": "judge timed out"}]}]}
    recs = [normalize(r) for r in from_deepeval(run)]
    assert [r["verdict"] for r in recs] == ["pass", "error"]
    assert recs[0]["score"] == 0.7 and recs[0]["model"] == "m1"
    assert recs[0]["output"] == "a1" and recs[0]["requirement_id"] == "REQ-001"
    assert recs[1]["score"] is None and recs[1]["requirement_id"] == "UNMAPPED"
    snake = [{"name": "case-1", "input": "q1", "actual_output": "a1", "success": False,
              "metrics_data": [{"score": 0.2}]}]
    assert from_deepeval(snake)[0]["verdict"] == "fail"


DE_DIR = Path(__file__).parent.parent / "examples" / "deepeval_synthetic"


def test_build_from_deepeval_fixture(tmp_path):
    recs = load_results(DE_DIR / "test_run.json", fmt="deepeval")
    assert [r["test_id"] for r in recs] == ["DE-001", "DE-002", "DE-003", "DE-004"]
    assert recs[2]["score"] == 0.0 and recs[3]["score"] is None
    r = build(DE_DIR / "test_run.json", EX / "requirements.yaml", tmp_path, fmt="deepeval",
              run_id="de-test", now="2026-01-01T00:00:00Z")
    assert r["meta"]["n_tests"] == 4
    assert "Test DE-003 (REQ-003): verdict FAIL" in r["deviations"]
    assert "Test DE-004 (REQ-004): verdict ERROR" in r["deviations"]


def test_duplicate_test_ids_are_rejected(tmp_path):
    rec = dict(test_id="T-1", requirement_id="R", input="", output="", verdict="pass",
               model="m", timestamp="2026-01-01T00:00:00Z")
    p = tmp_path / "dupes.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in (rec, {**rec, "verdict": "fail"})))
    with pytest.raises(SchemaError, match="duplicate test_id"):
        load_results(p)


def test_promptfoo_same_test_id_across_providers_gets_column_suffix():
    def row(p_idx, provider, ok):
        return {"testIdx": 0, "promptIdx": p_idx, "success": ok, "provider": {"id": provider},
                "response": {"output": "x"}, "vars": {"q": "synthetic"},
                "testCase": {"metadata": {"requirement_id": "REQ-1", "test_id": "PF-1"}}}
    recs = from_promptfoo({"results": {"results": [row(0, "mock:a", True),
                                                   row(1, "mock:b", False)]}})
    assert [(r["test_id"], r["model"], r["verdict"]) for r in recs] == [
        ("PF-1/p0", "mock:a", "pass"), ("PF-1/p1", "mock:b", "fail")]
