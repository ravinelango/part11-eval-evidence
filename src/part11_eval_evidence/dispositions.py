"""Load and validate deviation disposition records for failed checks.

A disposition file documents how each known failure or gap was handled
(accepted / corrected / deferred), with root cause and approver metadata.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

DISPOSITIONS = frozenset({"accepted", "corrected", "deferred"})
REQUIRED = (
    "deviation_id",
    "description",
    "root_cause",
    "disposition",
    "disposition_rationale",
    "approver",
    "approved_at",
)


class DispositionError(ValueError):
    pass


def _read_doc(path: Path) -> dict | list:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        return yaml.safe_load(text) or {}
    data = json.loads(text)
    return data


def normalize_disposition(rec: dict) -> dict:
    missing = [k for k in REQUIRED if k not in rec or rec[k] in (None, "")]
    if missing:
        raise DispositionError(
            f"disposition {rec.get('deviation_id', '?')} missing fields: {missing}"
        )
    related_req = rec.get("requirement_id") or rec.get("related_requirement_id")
    related_test = rec.get("test_id") or rec.get("related_test_id")
    if not related_req and not related_test:
        raise DispositionError(
            f"disposition {rec['deviation_id']}: need requirement_id and/or test_id"
        )
    disp = str(rec["disposition"]).lower()
    if disp not in DISPOSITIONS:
        raise DispositionError(
            f"disposition {rec['deviation_id']}: disposition must be one of "
            f"{sorted(DISPOSITIONS)}"
        )
    return {
        "deviation_id": str(rec["deviation_id"]),
        "requirement_id": str(related_req) if related_req else "",
        "test_id": str(related_test) if related_test else "",
        "description": str(rec["description"]),
        "root_cause": str(rec["root_cause"]),
        "disposition": disp,
        "disposition_rationale": str(rec["disposition_rationale"]),
        "approver": str(rec["approver"]),
        "approved_at": str(rec["approved_at"]),
    }


def load_dispositions(path: str | Path | None) -> list[dict]:
    """Load dispositions from YAML or JSON. Returns [] when path is None."""
    if path is None:
        return []
    path = Path(path)
    raw = _read_doc(path)
    if isinstance(raw, dict):
        rows = raw.get("dispositions", [])
        if not isinstance(rows, list):
            raise DispositionError("dispositions key must be a list")
    elif isinstance(raw, list):
        rows = raw
    else:
        raise DispositionError("disposition file must be a mapping or a list")
    return [normalize_disposition(r) for r in rows]


def match_dispositions(
    dispositions: list[dict],
    results: list[dict],
    matrix: list[dict],
) -> list[dict]:
    """Annotate dispositions with whether they cover a known failure or gap.

    Matching is by test_id and/or requirement_id against failed/error results
    and against matrix rows that are FAIL / NOT TESTED / UNTRACED.
    """
    failed_tests = {
        r["test_id"]: r for r in results if r["verdict"] != "pass"
    }
    gap_reqs = {
        m["requirement_id"]: m
        for m in matrix
        if m["status"] in ("FAIL", "NOT TESTED", "UNTRACED")
    }
    out = []
    for d in dispositions:
        linked_fail = bool(d["test_id"] and d["test_id"] in failed_tests)
        linked_gap = bool(d["requirement_id"] and d["requirement_id"] in gap_reqs)
        out.append({**d, "covers_known_issue": linked_fail or linked_gap})
    return out
