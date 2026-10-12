"""Hash-chained (SHA-256) run log. Each entry commits to the previous entry's hash.

This makes edits *detectable* (tamper-evident), not impossible (not tamper-proof).
Anyone able to rewrite the whole file can rebuild the chain; anchor the final hash
externally (e.g. in a signed commit or ticket) to close that gap.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

GENESIS = "0" * 64


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_chain(events: list[dict]) -> list[dict]:
    prev, entries = GENESIS, []
    for seq, ev in enumerate(events):
        body = {"seq": seq, "prev_hash": prev, "event": ev}
        h = sha256(canonical(body))
        entries.append({**body, "hash": h})
        prev = h
    return entries


def write_chain(entries: list[dict], path: Path) -> None:
    path.write_text("".join(canonical(e) + "\n" for e in entries), encoding="utf-8")


def verify_chain(path: str | Path) -> tuple[bool, list[str]]:
    problems, prev = [], GENESIS
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            problems.append(f"line {i + 1}: not valid JSON")
            break
        body = {"seq": e.get("seq"), "prev_hash": e.get("prev_hash"), "event": e.get("event")}
        if e.get("seq") != i:
            problems.append(f"line {i + 1}: sequence {e.get('seq')} != {i} (reordered/removed?)")
        if e.get("prev_hash") != prev:
            problems.append(f"line {i + 1}: prev_hash does not match previous entry")
        if sha256(canonical(body)) != e.get("hash"):
            problems.append(f"line {i + 1}: content hash mismatch (entry edited)")
        prev = e.get("hash")
    if not lines:
        problems.append("log is empty")
    return (not problems, problems)
