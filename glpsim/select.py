"""`sim.py select` — the selection rule of METHOD §7, in code.

The rule itself (`select_step`) is a pure function over a list of run dicts and
the sim config; `main` does the file I/O around it.

Procedure (METHOD §7):
 1. Discard runs with status != "ok" (and, necessarily, runs with no scores).
 2. Plausibility floor: discard plausibility < floor. If fewer than
    `min_survivors` remain, lower the floor by 1 and repeat (logged); never
    below `plausibility_floor_min`.
 3. axis_badness = weighted mean of the six badness dimensions with the step's
    weights, plus the step's `section_severity` (world.<section>.severity) at
    `section_severity_weight` when the axis names one.
 4. Rank by axis_badness desc, then plausibility desc, then generativity desc.
    Final tie-break: run_id asc, so the ranking is total and reproducible.
 5. Diversity guard, walking down the ranking: at most `max_from_one_parent`
    survivors from one parent lineage (unless only one lineage has eligible
    runs), and no two survivors with identical values on `distinct_on`.
 6. Survivors get new lineage ids L1..Lk in rank order, parent recorded.

One case METHOD does not specify: the guard cannot fill the beam from the
eligible pool. Then the floor is lowered by 1 (logged) if that would admit more
runs, the same remedy step 2 uses; the guard's constraints are never relaxed.
If the beam still cannot be filled at the minimum floor, fewer survivors are
kept and that is logged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

DIMS = ("flourishing", "autonomy", "inequality", "public_health", "cohesion", "epistemic")


class SelectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    run_id: str
    parent: str
    axis_badness: float
    plausibility: float
    generativity: float
    combo: tuple
    run: dict = field(compare=False, hash=False, repr=False)

    def sort_key(self):
        # round so float noise in the weighted mean can't break a genuine tie
        return (-round(self.axis_badness, 6), -self.plausibility, -self.generativity, self.run_id)


@dataclass
class Survivor:
    lineage: str
    candidate: Candidate
    rank: int


@dataclass
class Selection:
    step: int
    axis: str
    floor_used: int
    survivors: list[Survivor]
    ranking: list[Candidate]             # eligible runs at the final floor, ranked
    runner_up: Candidate | None
    runner_up_reason: str | None         # why it lost: rank, or which guard rule skipped it
    excluded: dict[str, str]             # run_id -> reason (status / unscored / magnitude floor)
    below_floor: list[Candidate]
    skipped: list[tuple[str, str]]       # (run_id, guard rule that skipped it) at the final floor
    log: list[str]
    per_run: dict[str, dict]             # run_id -> the run file's `selection` object


def axis_badness(run: dict, axis_cfg: dict, section_weight: float) -> float:
    b = run["scores"]["badness"]
    w = axis_cfg["weights"]
    num = sum(w[d] * b[d] for d in DIMS)
    den = sum(w[d] for d in DIMS)
    section = axis_cfg.get("section_severity")
    if section:
        num += section_weight * run["world"][section]["severity"]
        den += section_weight
    return num / den


def exclusion_reason(run: dict, magnitude_floor: float) -> str | None:
    """Why a run cannot be ranked at all. The magnitude floor is applied here, before the
    plausibility floor, and is never lowered."""
    if run.get("status") != "ok":
        return f"status={run.get('status')}"
    if not run.get("scores"):
        return "unscored"
    axes = run["scores"].get("plausibility_axes")
    if not axes:
        return "judged without plausibility sub-axes (rubric v1); re-judge"
    if axes["magnitude"] < magnitude_floor:
        return f"magnitude {axes['magnitude']:g} < magnitude_floor {magnitude_floor:g}"
    return None


def guarded_pick(ranked: list[Candidate], beam: int, max_from_one_parent: int):
    """Walk down the ranking applying the diversity guard. Returns (picked, skipped)."""
    single_lineage = len({c.parent for c in ranked}) <= 1
    picked: list[Candidate] = []
    skipped: list[tuple[str, str]] = []
    per_parent: dict[str, int] = {}
    combos: dict[tuple, str] = {}
    for c in ranked:
        if len(picked) >= beam:
            break
        if not single_lineage and per_parent.get(c.parent, 0) >= max_from_one_parent:
            skipped.append((c.run_id, f"parent {c.parent} already has {max_from_one_parent} survivors"))
            continue
        if c.combo in combos:
            skipped.append((c.run_id, f"same drivers {'/'.join(map(str, c.combo))} as {combos[c.combo]}"))
            continue
        picked.append(c)
        per_parent[c.parent] = per_parent.get(c.parent, 0) + 1
        combos[c.combo] = c.run_id
    return picked, skipped


def select_step(runs: list[dict], cfg: dict, step: int) -> Selection:
    axis_cfg = cfg["axes"][str(step)]
    guard = cfg["diversity_guard"]
    beam = cfg["beam"]
    floor_min = cfg["plausibility_floor_min"]
    min_survivors = cfg["min_survivors"]
    log: list[str] = []

    excluded: dict[str, str] = {}
    scored: list[Candidate] = []
    for run in sorted(runs, key=lambda r: r["run_id"]):
        reason = exclusion_reason(run, cfg["magnitude_floor"])
        if reason:
            excluded[run["run_id"]] = reason
            continue
        s = run["scores"]
        scored.append(Candidate(
            run_id=run["run_id"],
            parent=run["parent_lineage"],
            axis_badness=axis_badness(run, axis_cfg, cfg["section_severity_weight"]),
            plausibility=s["plausibility"],
            generativity=s["generativity"],
            combo=tuple(run["drivers"][k] for k in guard["distinct_on"]),
            run=run,
        ))
    if not scored:
        raise SelectionError(f"step {step}: no scored runs with status ok "
                             f"({len(excluded)} excluded) — run `judge --step {step}` first?")

    floor = cfg["plausibility_floor"]
    while True:
        eligible = [c for c in scored if c.plausibility >= floor]
        if len(eligible) < min_survivors and floor > floor_min:
            log.append(f"only {len(eligible)} run(s) at plausibility >= {floor}; "
                       f"lowering floor to {floor - 1}")
            floor -= 1
            continue
        ranked = sorted(eligible, key=Candidate.sort_key)
        picked, skipped = guarded_pick(ranked, beam, guard["max_from_one_parent"])
        if len(picked) < beam and floor > floor_min and len(eligible) < len(scored):
            log.append(f"diversity guard filled only {len(picked)} of {beam} at floor {floor}; "
                       f"lowering floor to {floor - 1}")
            floor -= 1
            continue
        break

    if not picked:
        raise SelectionError(f"step {step}: no run reaches the minimum plausibility floor {floor_min}")
    if len(picked) < beam:
        log.append(f"WARNING: only {len(picked)} survivor(s) (beam {beam}) at the final floor {floor}")

    picked_ids = {c.run_id for c in picked}
    survivors = [Survivor(lineage=f"L{i}", candidate=c,
                          rank=next(j for j, r in enumerate(ranked, 1) if r.run_id == c.run_id))
                 for i, c in enumerate(picked, 1)]

    runner_up, runner_up_reason = None, None
    skip_reason = dict(skipped)
    for j, c in enumerate(ranked, 1):
        if c.run_id not in picked_ids:
            runner_up = c
            runner_up_reason = (f"skipped by diversity guard: {skip_reason[c.run_id]}"
                                if c.run_id in skip_reason else f"ranked {j}")
            break

    per_run: dict[str, dict] = {}
    lineage_of = {s.candidate.run_id: s.lineage for s in survivors}
    rank_of = {c.run_id: j for j, c in enumerate(ranked, 1)}
    for c in scored:
        sel = {"axis": axis_cfg["name"], "axis_badness": round(c.axis_badness, 4),
               "survived": c.run_id in picked_ids, "new_lineage": lineage_of.get(c.run_id),
               "floor_used": floor}
        if c.run_id in rank_of:
            sel["rank"] = rank_of[c.run_id]
        per_run[c.run_id] = sel
    for rid in excluded:
        per_run[rid] = {"axis": axis_cfg["name"], "survived": False, "new_lineage": None,
                        "floor_used": floor}

    return Selection(
        step=step, axis=axis_cfg["name"], floor_used=floor, survivors=survivors,
        ranking=ranked, runner_up=runner_up, runner_up_reason=runner_up_reason,
        excluded=excluded, below_floor=[c for c in scored if c.plausibility < floor],
        skipped=skipped, log=log, per_run=per_run,
    )


# ---------------------------------------------------------------- rendering

def world_step_doc(sel: Selection, year: int, parent_ancestry: dict[str, list[str]],
                   selected_at: str) -> dict:
    lineages = {}
    for s in sel.survivors:
        run = s.candidate.run
        lineages[s.lineage] = {
            "lineage": s.lineage,
            "parent_lineage": run["parent_lineage"],
            "ancestry": parent_ancestry.get(run["parent_lineage"], []) + [run["run_id"]],
            "source_run": run["run_id"],
            "rank": s.rank,
            "axis_badness": round(s.candidate.axis_badness, 4),
            "world": run["world"],
            "prose": run["prose"],
        }
    return {"step": sel.step, "year": year, "axis": sel.axis, "floor_used": sel.floor_used,
            "selected_at": selected_at, "lineages": lineages}


def _fmt(x) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)


def _weights_line(axis_cfg: dict, section_weight) -> str:
    parts = [f"{d} ×{w}" for d, w in axis_cfg["weights"].items()]
    if axis_cfg.get("section_severity"):
        parts.append(f"`{axis_cfg['section_severity']}` severity ×{section_weight}")
    return ", ".join(parts)


def lineage_section(sel: Selection, cfg: dict, year: int, runs: list[dict], selected_at: str) -> str:
    axis_cfg = cfg["axes"][str(sel.step)]
    distinct = cfg["diversity_guard"]["distinct_on"]
    n_runs = len(runs)
    parents = sorted({r["parent_lineage"] for r in runs})
    seeds = sorted({r["seed"] for r in runs if r.get("seed") is not None})
    gen_models = sorted({r["generator_model"] for r in runs if r.get("generator_model")})
    judge_models = sorted({r["scores"]["judge_model"] for r in runs if r.get("scores", {}).get("judge_model")})

    reasons: dict[str, int] = {}
    for r in sel.excluded.values():
        reasons[r] = reasons.get(r, 0) + 1
    excl = ", ".join(f"{n} {r}" for r, n in sorted(reasons.items())) or "none"

    L = [f"<!-- step:{sel.step}:begin -->",
         f"## Step {sel.step} · {year} · axis of worst: {sel.axis}", "",
         f"- Selected {selected_at} from {n_runs} run(s) of parent lineage(s) {', '.join(parents)}"
         + (f"; seed {', '.join(map(str, seeds))}" if seeds else ""),
         f"- Generator {', '.join(gen_models) or '?'} · judge {', '.join(judge_models) or '?'}",
         f"- Weights: {_weights_line(axis_cfg, cfg['section_severity_weight'])}",
         f"- Magnitude floor (hard): {cfg['magnitude_floor']:g} · composite plausibility = "
         + " + ".join(f"{w:g}×{k}" for k, w in cfg["plausibility_weights"].items()),
         f"- Plausibility floor used: {sel.floor_used}"
         + (f" (configured {cfg['plausibility_floor']})" if sel.floor_used != cfg["plausibility_floor"] else ""),
         f"- Excluded before ranking: {excl}; below floor: {len(sel.below_floor)}; "
         f"eligible and ranked: {len(sel.ranking)}"]
    for line in sel.log:
        L.append(f"- Log: {line}")
    L += ["", "| Lineage | Parent | Run | Rank | Axis badness | Plausibility | Generativity | Overall | "
          + " / ".join(distinct) + " |",
          "|---|---|---|---|---|---|---|---|---|"]
    for s in sel.survivors:
        c = s.candidate
        L.append(f"| **{s.lineage}** | {c.parent} | `{c.run_id}` | {s.rank} | {_fmt(c.axis_badness)} | "
                 f"{_fmt(c.plausibility)} | {_fmt(c.generativity)} | "
                 f"{_fmt(c.run['scores']['badness']['overall'])} | {' / '.join(map(str, c.combo))} |")
    L.append("")
    for s in sel.survivors:
        headline = s.candidate.run.get("prose", {}).get("headline", "")
        L.append(f"- **{s.lineage}** — {headline}")
    L.append("")
    if sel.runner_up:
        c = sel.runner_up
        headline = c.run.get("prose", {}).get("headline", "")
        L.append(f"Runner-up: `{c.run_id}` (parent {c.parent}; axis badness {_fmt(c.axis_badness)}, "
                 f"plausibility {_fmt(c.plausibility)}, generativity {_fmt(c.generativity)}) — "
                 f"{sel.runner_up_reason}. {headline}")
    else:
        L.append("Runner-up: none (every eligible run survived).")
    if sel.skipped:
        L += ["", "Diversity guard skips:"]
        L += [f"- `{rid}`: {why}" for rid, why in sel.skipped]
    L += [f"<!-- step:{sel.step}:end -->", ""]
    return "\n".join(L)


LINEAGE_HEADER = """# GLP-1000 — lineage

Every surviving world, the run it was selected from, its scores, and the runner-up it
beat. Written by `python sim.py select`; do not edit by hand. Full drivers, prose,
scores and judge rationales for every run are in `runs/`.

"""


def upsert_section(existing: str | None, step: int, section: str) -> str:
    text = existing if existing else LINEAGE_HEADER
    begin, end = f"<!-- step:{step}:begin -->", f"<!-- step:{step}:end -->"
    if begin in text:
        i, j = text.index(begin), text.index(end) + len(end)
        rest = text[j:].lstrip("\n")
        return text[:i] + section + ("\n" + rest if rest else "")
    if not text.endswith("\n\n"):
        text = text.rstrip("\n") + "\n\n"
    return text + section


# ---------------------------------------------------------------- I/O

def load_step_runs(paths, step: int) -> list[tuple[object, dict]]:
    from .common import load_json
    d = paths.step_runs(step)
    if not d.exists():
        return []
    return [(p, load_json(p)) for p in sorted(d.glob("L*/s*.json"))]


def parent_ancestry(paths, step: int) -> dict[str, list[str]]:
    from .common import load_json
    if step <= 1:
        return {"L0": []}
    doc = load_json(paths.world_file(step - 1))
    return {lid: e["ancestry"] for lid, e in doc["lineages"].items()}


def main(paths, args) -> int:
    from .common import dump_json, load_sim_config, step_year, write_text_atomic
    from . import schemas

    cfg = load_sim_config(paths)
    step = args.step
    out = paths.world_file(step)
    if out.exists() and not args.force:
        print(f"{out.relative_to(paths.root)} already exists; selection for step {step} is done. "
              f"Use --force to redo it (rewrites world/step{step}.json and the step {step} section of lineage.md).")
        return 1
    loaded = load_step_runs(paths, step)
    if not loaded:
        print(f"no runs in runs/step{step}/")
        return 1
    runs = [r for _, r in loaded]
    try:
        sel = select_step(runs, cfg, step)
    except SelectionError as e:
        print(f"select failed: {e}")
        return 1

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    year = step_year(cfg, step)
    doc = world_step_doc(sel, year, parent_ancestry(paths, step), now)
    errs = schemas.errors(schemas.validator(paths, "world_step"), doc)
    if errs:
        print("refusing to write an invalid world file:\n  " + "\n  ".join(errs))
        return 1

    for p, run in loaded:
        run["selection"] = sel.per_run[run["run_id"]]
        dump_json(p, run)
    dump_json(out, doc)
    existing = paths.lineage_md.read_text(encoding="utf-8") if paths.lineage_md.exists() else None
    write_text_atomic(paths.lineage_md,
                      upsert_section(existing, step, lineage_section(sel, cfg, year, runs, now)))

    for line in sel.log:
        print(f"log: {line}")
    print(f"step {step} ({year}, axis {sel.axis}): floor {sel.floor_used}, "
          f"{len(sel.ranking)} eligible of {len(runs)}; survivors:")
    for s in sel.survivors:
        c = s.candidate
        print(f"  {s.lineage} <- {c.run_id}  axis_badness {c.axis_badness:.2f}  "
              f"plausibility {_fmt(c.plausibility)}  generativity {_fmt(c.generativity)}")
    if sel.runner_up:
        print(f"  runner-up {sel.runner_up.run_id} ({sel.runner_up_reason})")
    print(f"wrote {out.relative_to(paths.root)} and lineage.md")
    return 0
