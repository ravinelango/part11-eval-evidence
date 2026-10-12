"""Command line: `p11e build` and `p11e verify`."""

from __future__ import annotations

import argparse
import sys

from .build import build
from .chain import verify_chain


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
    v = sub.add_parser("verify", help="verify hash-chained run log")
    v.add_argument("log")
    a = p.parse_args(argv)

    if a.cmd == "build":
        r = build(a.results, a.requirements, a.out, a.operator, a.config, a.format, a.run_id)
        m = r["meta"]
        print(f"Built evidence package in {a.out}/ ({m['n_tests']} tests, "
              f"{len(r['deviations'])} deviations). Chain head: {m['chain_head']}")
        return 0
    ok, problems = verify_chain(a.log)
    if ok:
        print(f"OK: {a.log} hash chain intact")
        return 0
    print(f"TAMPER DETECTED in {a.log}:")
    for prob in problems:
        print(f"  - {prob}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
