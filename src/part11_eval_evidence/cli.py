"""Command line: `p11e build`, `p11e verify` and `p11e head`."""

from __future__ import annotations

import argparse
import sys

from .build import build
from .chain import read_head, verify_against_anchor, verify_chain


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="p11e", description="Eval run -> audit-ready evidence package")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build evidence package")
    b.add_argument("--results", required=True)
    b.add_argument("--requirements", required=True)
    b.add_argument("--out", default="out")
    b.add_argument("--operator")
    b.add_argument("--config", help="eval config file to fingerprint")
    b.add_argument("--format", default="native", choices=["native", "promptfoo", "deepeval"])
    b.add_argument("--run-id")
    b.add_argument("--dispositions",
                   help="YAML/JSON deviation disposition file for failed checks")
    v = sub.add_parser("verify", help="verify hash-chained run log")
    v.add_argument("log")
    v.add_argument("--expect-head", metavar="SHA256",
                   help="chain head recorded outside the log; fails if it differs")
    h = sub.add_parser("head", help="print the chain head hash to record externally")
    h.add_argument("log")
    a = p.parse_args(argv)

    if a.cmd == "build":
        r = build(a.results, a.requirements, a.out, a.operator, a.config, a.format, a.run_id,
                  dispositions_path=a.dispositions)
        m = r["meta"]
        print(f"Built evidence package in {a.out}/ ({m['n_tests']} tests, "
              f"{len(r['deviations'])} deviations, {len(r['dispositions'])} dispositions). "
              f"Chain head: {m['chain_head']}")
        return 0
    if a.cmd == "head":
        head = read_head(a.log)
        if head is None:
            print(f"No chain head: {a.log} is empty or unreadable", file=sys.stderr)
            return 1
        print(head)
        return 0
    if a.expect_head:
        ok, problems = verify_against_anchor(a.log, a.expect_head)
    else:
        ok, problems = verify_chain(a.log)
    if ok:
        suffix = " and matches anchored head" if a.expect_head else ""
        print(f"OK: {a.log} hash chain intact{suffix}")
        return 0
    print(f"TAMPER DETECTED in {a.log}:")
    for prob in problems:
        print(f"  - {prob}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
