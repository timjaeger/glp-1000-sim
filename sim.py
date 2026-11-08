#!/usr/bin/env python3
"""GLP-1000 simulation runner. See METHOD.md (the spec) and CLAUDE.md (the rules).

    python sim.py validate
    python sim.py generate --step N [--n 50] [--seed S] [--dry-run]
    python sim.py judge    --step N [--dry-run]
    python sim.py select   --step N
"""
from __future__ import annotations

import argparse
import sys

from glpsim.common import Paths


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sim.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="validate world/ and runs/ against schema/")
    v.add_argument("-v", "--verbose", action="store_true", help="also list passing files")

    s = sub.add_parser("select", help="apply the METHOD §7 selection rule to a judged step")
    s.add_argument("--step", type=int, required=True, choices=range(1, 6))
    s.add_argument("--force", action="store_true", help="redo a step that was already selected")

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    paths = Paths()
    if args.cmd == "validate":
        from glpsim import validate
        return validate.main(paths, args)
    if args.cmd == "select":
        from glpsim import select
        return select.main(paths, args)
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    sys.exit(main())
