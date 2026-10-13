import json
from pathlib import Path

import pytest

from part11_eval_evidence import chain
from part11_eval_evidence.build import build
from part11_eval_evidence.cli import main
from part11_eval_evidence.ingest import SchemaError, from_promptfoo, load_results, normalize

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
