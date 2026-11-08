#!/usr/bin/env python3
"""GLP-1000 simulation runner. See METHOD.md (the spec) and CLAUDE.md (the rules).

    python sim.py validate
    python sim.py generate --step N [--n 50] [--seed S] [--dry-run]
    python sim.py judge    --step N [--dry-run]
    python sim.py select   --step N
    python sim.py report
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

    g = sub.add_parser("generate", help="draw drivers, render prompts, submit one generation batch")
    g.add_argument("--step", type=int, required=True, choices=range(1, 6))
    g.add_argument("--n", type=int, default=None, help="runs this step (default config runs_per_step)")
    g.add_argument("--seed", type=int, default=None, help="base seed (default config seed)")
    g.add_argument("--dry-run", action="store_true", help="render and write the batch file; submit nothing")
    g.add_argument("--yes", action="store_true", help="submit even if the estimate exceeds max_usd_per_step")
    g.add_argument("--resume", action="store_true", help="resume polling/collecting a submitted batch")
    g.add_argument("--poll-interval", type=float, default=60.0, help="seconds between batch status polls")

    j = sub.add_parser("judge", help="score every unjudged ok run of a step in one batch")
    j.add_argument("--step", type=int, required=True, choices=range(1, 6))
    j.add_argument("--dry-run", action="store_true", help="render and write the batch file; submit nothing")
    j.add_argument("--fixture", default=None, help="dry-run only: render against this run file if no runs exist")
    j.add_argument("--rejudge", action="store_true", help="also judge runs that already have scores")
    j.add_argument("--yes", action="store_true", help="submit even if the estimate exceeds max_usd_per_step")
    j.add_argument("--resume", action="store_true", help="resume polling/collecting a submitted batch")
    j.add_argument("--poll-interval", type=float, default=60.0, help="seconds between batch status polls")

    s = sub.add_parser("select", help="apply the METHOD §7 selection rule to a judged step")
    s.add_argument("--step", type=int, required=True, choices=range(1, 6))
    s.add_argument("--force", action="store_true", help="redo a step that was already selected")

    sub.add_parser("report", help="re-render lineage.md and write report/ (checks every selection reproduces)")

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    paths = Paths()
    if args.cmd == "validate":
        from glpsim import validate
        return validate.main(paths, args)
    if args.cmd == "generate":
        from glpsim import generate
        return generate.main(paths, args)
    if args.cmd == "judge":
        from glpsim import judge
        return judge.main(paths, args)
    if args.cmd == "select":
        from glpsim import select
        return select.main(paths, args)
    if args.cmd == "report":
        from glpsim import report
        return report.main(paths, args)
    raise SystemExit(f"unknown command {args.cmd}")


if __name__ == "__main__":
    sys.exit(main())
