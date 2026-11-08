"""`sim.py validate` — check every JSON file under world/ and runs/ against schema/.

Beyond the JSON Schemas this enforces the repo's integrity rules:
  * world/step0.json is byte-for-byte the researched baseline and fictional=false
  * every simulated world (runs, world/stepN.json for N>=1) has fictional=true
    and the year its step implies
  * run files live at runs/stepN/<parent_lineage>/<run_id>.json and their ids agree
Nothing is skipped silently: an unrecognised JSON file is itself a problem.
runs/_dry/ (dry-run scratch output, gitignored) is not part of the record and is not walked.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import schemas
from .common import Paths, load_json, load_sim_config, step_year

RUN_ID_RE = re.compile(r"^s(?P<step>[1-5])-(?P<parent>L[0-9]+)-r(?P<idx>[0-9]{2})$")
STEP_DIR_RE = re.compile(r"^step(?P<step>[0-9]+)$")
WORLD_FILE_RE = re.compile(r"^step(?P<step>[0-9]+)\.json$")
BATCH_STATE_RE = re.compile(r"^_state_(generate|judge)\.json$")


def check_world_state(paths: Paths, world, *, fictional: bool, year: int | None) -> list[str]:
    errs = schemas.errors(schemas.validator(paths, "world_state"), world)
    if isinstance(world, dict):
        if world.get("fictional") is not fictional:
            errs.append(f"fictional: must be {str(fictional).lower()} "
                        f"({'researched baseline' if not fictional else 'simulated step'})")
        if year is not None and world.get("year") != year:
            errs.append(f"year: {world.get('year')!r} but this step is {year}")
    return errs


def check_run(paths: Paths, run, file: Path, cfg: dict) -> list[str]:
    errs = schemas.errors(schemas.validator(paths, "run"), run)
    if not isinstance(run, dict):
        return errs
    rid = run.get("run_id", "")
    m = RUN_ID_RE.match(rid)
    if m:
        if int(m["step"]) != run.get("step"):
            errs.append(f"run_id {rid} does not match step {run.get('step')}")
        if m["parent"] != run.get("parent_lineage"):
            errs.append(f"run_id {rid} does not match parent_lineage {run.get('parent_lineage')}")
        if "run_index" in run and int(m["idx"]) != run["run_index"]:
            errs.append(f"run_id {rid} does not match run_index {run['run_index']}")
    expected = paths.run_file(run.get("step", -1), run.get("parent_lineage", "?"), rid)
    if file.resolve() != expected.resolve():
        errs.append(f"file should be at {expected.relative_to(paths.root)}")
    if isinstance(run.get("step"), int) and run.get("year") != step_year(cfg, run["step"]):
        errs.append(f"year {run.get('year')} but step {run['step']} is {step_year(cfg, run['step'])}")
    if run.get("status") == "ok":
        for k in ("world", "prose"):
            if k not in run:
                errs.append(f"status is ok but '{k}' is missing")
    if "world" in run and run.get("status") == "ok":
        # schema already checked shape via $ref; add the integrity rules
        w = run["world"]
        if isinstance(w, dict):
            if w.get("fictional") is not True:
                errs.append("world.fictional: simulated worlds must be fictional=true")
            if w.get("year") != run.get("year"):
                errs.append(f"world.year {w.get('year')} != run year {run.get('year')}")
    return errs


def check_world_step(paths: Paths, doc, cfg: dict, step: int) -> list[str]:
    errs = schemas.errors(schemas.validator(paths, "world_step"), doc)
    if not isinstance(doc, dict):
        return errs
    if doc.get("step") != step:
        errs.append(f"step {doc.get('step')!r} but file is step{step}.json")
    year = step_year(cfg, step)
    for lid, entry in (doc.get("lineages") or {}).items():
        if not isinstance(entry, dict):
            continue
        if entry.get("lineage") != lid:
            errs.append(f"lineages/{lid}: lineage field is {entry.get('lineage')!r}")
        w = entry.get("world")
        if isinstance(w, dict):
            if w.get("fictional") is not True:
                errs.append(f"lineages/{lid}/world.fictional: must be true")
            if w.get("year") != year:
                errs.append(f"lineages/{lid}/world.year: {w.get('year')} but step {step} is {year}")
    return errs


def validate_tree(paths: Paths) -> tuple[list[str], list[tuple[str, str]]]:
    """Returns (files_checked, problems) where problems are (relative_path, message)."""
    cfg = load_sim_config(paths)
    checked: list[str] = []
    problems: list[tuple[str, str]] = []

    def rel(p: Path) -> str:
        return str(p.relative_to(paths.root))

    def add(p: Path, msgs: list[str]):
        checked.append(rel(p))
        problems.extend((rel(p), m) for m in msgs)

    def load(p: Path):
        try:
            return load_json(p), None
        except Exception as e:  # malformed JSON is a validation failure, not a crash
            return None, f"not valid JSON: {e}"

    # world/
    if paths.world.exists():
        for p in sorted(paths.world.rglob("*.json")):
            doc, err = load(p)
            if err:
                add(p, [err]); continue
            m = WORLD_FILE_RE.match(p.name)
            if p.parent != paths.world or not m:
                add(p, ["unrecognised file in world/ (expected world/stepN.json)"]); continue
            step = int(m["step"])
            if step == 0:
                msgs = check_world_state(paths, doc, fictional=False, year=cfg["baseline_year"])
                if paths.baseline.exists() and doc != load_json(paths.baseline):
                    msgs.append("differs from data/step0_baseline.json (step-0 facts must come "
                                "only from the sourced baseline)")
                add(p, msgs)
            else:
                add(p, check_world_step(paths, doc, cfg, step))

    # runs/
    if paths.runs.exists():
        for p in sorted(paths.runs.rglob("*.json")):
            if paths.dry in p.parents:
                continue
            doc, err = load(p)
            if err:
                add(p, [err]); continue
            parts = p.relative_to(paths.runs).parts
            if len(parts) == 2 and STEP_DIR_RE.match(parts[0]) and BATCH_STATE_RE.match(parts[1]):
                add(p, schemas.errors(schemas.validator(paths, "batch_state"), doc))
            elif len(parts) == 3 and STEP_DIR_RE.match(parts[0]):
                add(p, check_run(paths, doc, p, cfg))
            else:
                add(p, ["unrecognised file in runs/ (expected runs/stepN/<lineage>/<run_id>.json)"])

    return checked, problems


def main(paths: Paths, args) -> int:
    from .common import ensure_step0
    if ensure_step0(paths):
        print("copied data/step0_baseline.json -> world/step0.json")
    checked, problems = validate_tree(paths)
    for f, m in problems:
        print(f"FAIL {f}: {m}")
    bad = {f for f, _ in problems}
    for f in checked:
        if f not in bad and args.verbose:
            print(f"ok   {f}")
    print(f"validated {len(checked)} file(s): {len(checked) - len(bad)} ok, {len(bad)} failing")
    return 1 if problems else 0
