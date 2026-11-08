"""`sim.py report`: re-render lineage.md and write report/ (METHOD §10). Pure: no API calls.

Before writing anything it re-runs the selection rule (select.select_step, a pure function)
on every step's run files and checks that it reproduces exactly the survivors, ranks and
floor recorded in world/stepN.json. If any step does not reproduce, nothing is written:
the lineage is the product, and a report must never describe a selection the recorded
runs do not support.

Outputs, all deterministic (the only timestamps are the recorded `selected_at` values):
  lineage.md            every step's section, re-rendered from runs + world files
  report/README.md      the index: what was run, the finalists, models, rubrics, spend
  report/L<n>.md        one dossier per final lineage
"""
from __future__ import annotations

import json
import re
from collections import Counter

from . import select as S
from .common import load_json, load_sim_config, step_year, write_text_atomic

WORLD_FILE = re.compile(r"^step([1-9][0-9]*)\.json$")


class ReportError(RuntimeError):
    pass


# ---------------------------------------------------------------- data

def selected_steps(paths) -> list[int]:
    """Steps with a world/stepN.json, which must run 1..N without gaps."""
    steps = sorted(int(m[1]) for p in paths.world.glob("step*.json") if (m := WORLD_FILE.match(p.name)))
    if not steps:
        raise ReportError("no selected step: run `python sim.py select --step 1` first")
    if steps != list(range(1, steps[-1] + 1)):
        raise ReportError(f"world/ has steps {steps}; expected 1..{steps[-1]} without gaps")
    return steps


def reselect(paths, cfg: dict, step: int):
    """(Selection, runs, world doc), after checking the rule reproduces the recorded selection."""
    runs = [r for _, r in S.load_step_runs(paths, step)]
    doc = load_json(paths.world_file(step))
    sel = S.select_step(runs, cfg, step)
    got = [(s.lineage, s.candidate.run_id, s.rank) for s in sel.survivors]
    want = [(k, v["source_run"], v["rank"]) for k, v in doc["lineages"].items()]
    if got != want or sel.floor_used != doc["floor_used"]:
        raise ReportError(f"step {step}: the selection rule on runs/step{step}/ gives {got} at floor "
                          f"{sel.floor_used}, but world/step{step}.json records {want} at floor "
                          f"{doc['floor_used']}. Nothing written.")
    return sel, runs, doc


def load_all(paths, cfg: dict) -> dict:
    steps = selected_steps(paths)
    data = {"steps": steps, "sel": {}, "doc": {}, "runs": {}}
    for step in steps:
        sel, runs, doc = reselect(paths, cfg, step)
        data["sel"][step], data["doc"][step] = sel, doc
        data["runs"].update({r["run_id"]: r for r in runs})
    return data


def spend(paths) -> dict:
    ledger = load_json(paths.spend_ledger)["batches"] if paths.spend_ledger.exists() else []
    cost = lambda b: b["actual_usd"] if b.get("actual_usd") is not None else b["estimate_usd"]
    by_step = Counter()
    for b in ledger:
        by_step[b["step"]] += cost(b)
    return {"batches": len(ledger), "total": sum(by_step.values()), "by_step": dict(by_step)}


# ---------------------------------------------------------------- lineage.md

def render_lineage(paths, cfg: dict, data: dict) -> str:
    text = None
    for step in data["steps"]:
        sel, doc = data["sel"][step], data["doc"][step]
        runs = [r for r in data["runs"].values() if r["step"] == step]
        section = S.lineage_section(sel, cfg, step_year(cfg, step), runs, doc["selected_at"])
        text = S.upsert_section(text, step, section)
    return text


# ---------------------------------------------------------------- markdown helpers

def _f(x) -> str:
    return S._fmt(x)


def _cell(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def _bullets(items) -> str:
    return "\n".join(f"- {x}" for x in items)


def _drivers_line(d: dict) -> str:
    return ", ".join(f"{k} = {(', '.join(v) or 'none') if isinstance(v, list) else v}" for k, v in d.items())


def _rubric_note(run: dict) -> str:
    r = run["scores"].get("rubric", "v1")
    return {"v3": "v3, badness absolute against the 2026 baseline",
            "v2": "v2, badness relative to the parent world"}.get(r, r)


def _scores_block(run: dict) -> str:
    s = run["scores"]
    ax = s.get("plausibility_axes", {})
    b = s["badness"]
    lines = [
        "| " + " | ".join(b) + " |", "|" + "---|" * len(b),
        "| " + " | ".join(_f(v) for v in b.values()) + " |", "",
        f"Plausibility **{_f(s['plausibility'])}**"
        + (f" (driver fidelity {_f(ax['driver_fidelity'])}, mechanism {_f(ax['mechanism'])}, "
           f"magnitude {_f(ax['magnitude'])})" if ax else "")
        + f" · generativity {_f(s['generativity'])} · judge {s['judge_model']}, rubric {_rubric_note(run)}"
        + (f", {len(run['judge_samples'])} samples averaged" if run.get("judge_samples") else ""),
    ]
    return "\n".join(lines)


def _judge_notes(run: dict) -> str:
    s = run["scores"]
    out = []
    if s.get("least_plausible_claims"):
        out.append("Least plausible claims, quoted by the judge:\n\n" + _bullets(
            f"`{c['field']}`: “{c['quote']}” — {c['why']}" for c in s["least_plausible_claims"]))
    out += [f"**Badness rationale.** {s['rationale']['badness']}",
            f"**Plausibility rationale.** {s['rationale']['plausibility']}",
            f"**Generativity rationale.** {s['rationale']['generativity']}"]
    return "\n\n".join(out)


def _runner_up_line(sel) -> str:
    c = sel.runner_up
    if not c:
        return "No runner-up (every eligible run survived)."
    return (f"Runner-up `{c.run_id}` (parent {c.parent}; axis badness {c.axis_badness:.2f}, plausibility "
            f"{_f(c.plausibility)}; {sel.runner_up_reason}): {c.run['prose']['headline']}")


# ---------------------------------------------------------------- dossiers

def dossier(lineage: str, data: dict, cfg: dict) -> str:
    final = data["steps"][-1]
    entry = data["doc"][final]["lineages"][lineage]
    runs = data["runs"]
    run = runs[entry["source_run"]]
    W, P = run["world"], run["prose"]
    baseline_year = cfg["baseline_year"]
    L = [f"# {lineage} — {P['headline']}", "",
         f"Final lineage {lineage} of the GLP-1000 simulation: the world of {run['year']}, selected at step "
         f"{final} (rank {entry['rank']}, axis badness {entry['axis_badness']:.2f}). Simulated fiction "
         f"(`fictional: true`) built on the researched {baseline_year} baseline (`data/step0_baseline.json`, "
         f"sources in `data/step0_sources.md`). Written by `python sim.py report`.", "",
         "## Ancestry", "",
         "| Step | Year | Run | Selected as | Axis of worst | Axis badness | Plausibility | Headline |",
         "|---|---|---|---|---|---|---|---|",
         f"| 0 | {baseline_year} | baseline | L0 | — | — | — | Researched world, November {baseline_year} |"]
    for rid in entry["ancestry"]:
        a = runs[rid]; sel = a["selection"]
        L.append(f"| {a['step']} | {a['year']} | `{rid}` | {sel['new_lineage']} (rank {sel['rank']}) | "
                 f"{sel['axis']} | {sel['axis_badness']:.2f} | {_f(a['scores']['plausibility'])} | "
                 f"{_cell(a['prose']['headline'])} |")
    L += ["", f"## The world of {run['year']}", "", "### The world in 600 words", "", P["world_in_600_words"], "",
          "### A day in the life", "", P["a_day_in_the_life"], ""]
    pop, acc = W["population"], W["access"]
    L += ["### Key figures", "",
          f"- On drug: **{_f(pop['us_adults_on_drug_pct'])}%** of US adults; ever used {_f(pop['us_adults_ever_used_pct'])}%; "
          f"cycled off and on: {_f(pop['cycled_off_and_on_pct'])}% of ever-users; under 18: {_f(pop['pediatric_under_18_on_drug_pct'])}%",
          f"- By income third: {pop['by_income_third_pct']}; by age band: {pop['by_age_band_pct']}",
          f"- Cash price ${_f(acc['cash_price_usd_month_low'])}–{_f(acc['cash_price_usd_month_high'])}/month; employer coverage "
          f"{_f(acc['employer_coverage_pct'])}%; US generic: {acc['generic_us']}; gray market: {acc['gray_market']}; "
          f"dominant route: {acc['dominant_route']}",
          f"- Public coverage: {acc['public_coverage']}",
          f"- Population note: {pop['note']}", ""]
    for key, title in (("interior_life", "Interior life"), ("state", "The state"),
                       ("body_and_culture", "Body and culture")):
        sec = W[key]
        L += [f"### {title} (generator's severity {sec['severity']})", "",
              _bullets(f"**{k.replace('_', ' ').capitalize()}:** {v}" for k, v in sec.items() if k != "severity"), ""]
    L += [f"### Economy (generator's severity {W['economy']['severity']})", "",
          _bullets(f"**{k.replace('_', ' ')}** ({v['direction']}): {v['state']}"
                   for k, v in W["economy"].items() if isinstance(v, dict)), "",
          "### Drugs", "",
          f"- On market: {'; '.join(W['drugs']['on_market_classes'])}",
          f"- Best efficacy: {_f(W['drugs']['best_efficacy_pct_body_weight'])}% of body weight",
          f"- Indications beyond weight and diabetes: {', '.join(W['drugs']['indications_beyond_weight_and_diabetes']) or 'none'}",
          f"- Pipeline: {W['drugs']['pipeline_note']}", "",
          "### Safety ledger", "",
          _bullets(f"**{x['effect']}** ({x['status']}): {x['prevalence_note']} *Response:* {x['regulatory_response']}"
                   for x in W["safety_ledger"]), "",
          f"### Events, {run['year'] - 2}–{run['year']}", "",
          _bullets(f"**{e['date']}** ({e['driver']}): {e['event']}" for e in W["events"]), ""]
    if W.get("still_true"):
        L += [f"### Still true from {run['year'] - 2}", "", _bullets(W["still_true"]), ""]
    L += ["### Open tensions at the end of the simulation", "", _bullets(W["open_tensions"]), "",
          f"### Drivers drawn for {run['year']}", "", _drivers_line(run["drivers"]), "",
          f"### How the judge scored it", "", _scores_block(run), "", _judge_notes(run), ""]
    L += ["## Step by step", "",
          "Each step drew new drivers for 50 runs from the surviving parents, scored them, and kept the "
          "three worst plausible worlds on that step's axis. Below: what this lineage's world was at each "
          "step, what was drawn, how it scored, and the runner-up it beat.", ""]
    for rid in entry["ancestry"]:
        a = runs[rid]; step = a["step"]; sel = data["sel"][step]; doc = data["doc"][step]
        L += [f"### Step {step} · {a['year']} · axis of worst: {a['selection']['axis']}", "",
              f"**{a['prose']['headline']}** (`{rid}`, from parent {a['parent_lineage']}, selected as "
              f"{a['selection']['new_lineage']} at rank {a['selection']['rank']} of {len(sel.ranking)} eligible; "
              f"plausibility floor {doc['floor_used']}; selected {doc['selected_at']})", "",
              f"Drivers: {_drivers_line(a['drivers'])}", "",
              f"Axis badness {a['selection']['axis_badness']:.2f}.", "", _scores_block(a), "",
              "Events:", "", _bullets(f"**{e['date']}**: {e['event']}" for e in a["world"]["events"]), "",
              _runner_up_line(sel), "",
              "<details><summary>Judge notes</summary>", "", _judge_notes(a), "", "</details>", ""]
    L += ["## Final world state (JSON)", "", "```json", json.dumps(W, indent=2, ensure_ascii=False), "```", ""]
    return "\n".join(L)


def index(data: dict, cfg: dict, money: dict) -> str:
    final = data["steps"][-1]
    runs = data["runs"]
    by_step = {s: [r for r in runs.values() if r["step"] == s] for s in data["steps"]}
    n_runs = sum(len(v) for v in by_step.values())
    rubrics = {s: sorted({r["scores"].get("rubric", "v1") for r in v if r.get("scores")}) for s, v in by_step.items()}
    L = ["# GLP-1000 — final report", "",
         f"The world of GLP-1000 was selected, not written. Starting from the researched state of the GLP-1 era "
         f"in November {cfg['baseline_year']}, a five-step, beam-pruned Monte Carlo sampled {n_runs} candidate "
         f"futures, two years per step, and at each step kept the three worst plausible worlds and sampled "
         f"forward from them. The method is in `METHOD.md`; every run, score and selection is in `runs/`, "
         f"`world/` and `lineage.md`, and this report is re-rendered from them by `python sim.py report`, which "
         f"first checks that the selection rule reproduces every recorded selection.", "",
         "## The finalists", "",
         "| Lineage | Headline | Axis badness | Plausibility | Ancestry |", "|---|---|---|---|---|"]
    for lid, e in data["doc"][final]["lineages"].items():
        r = runs[e["source_run"]]
        L.append(f"| [{lid}]({lid}.md) | {_cell(r['prose']['headline'])} | {e['axis_badness']:.2f} | "
                 f"{_f(r['scores']['plausibility'])} | {' → '.join(f'`{a}`' for a in e['ancestry'])} |")
    L += ["", "## The run, step by step", "",
          "| Step | Year | Axis of worst | Runs | Valid | Floor | Survivors | Runner-up | Rubric |",
          "|---|---|---|---|---|---|---|---|---|"]
    for s in data["steps"]:
        v = by_step[s]; sel = data["sel"][s]; doc = data["doc"][s]
        ok = sum(r["status"] == "ok" for r in v)
        surv = ", ".join(f"{x.lineage} `{x.candidate.run_id}`" for x in sel.survivors)
        ru = f"`{sel.runner_up.run_id}`" if sel.runner_up else "—"
        L.append(f"| {s} | {doc['year']} | {doc['axis']} | {len(v)} | {ok} | {doc['floor_used']} | {surv} | {ru} | "
                 f"{', '.join(rubrics[s])} |")
    gen = sorted({r["generator_model"] for r in runs.values()})
    judges = sorted({r["scores"]["judge_model"] for r in runs.values() if r.get("scores")})
    seeds = sorted({r["seed"] for r in runs.values()})
    L += ["", "## How it was run", "",
          f"- Generator {', '.join(gen)}; judge {', '.join(judges)} (a different model), "
          f"{cfg['judging']['judge_samples']} judge samples per run, averaged.",
          f"- Seed {', '.join(map(str, seeds))}: every driver draw is `random.Random(seed + step*1000 + run_index)`, "
          f"recorded in each run file.",
          f"- Selection: hard magnitude floor {_f(cfg['magnitude_floor'])}, plausibility floor "
          f"{cfg['plausibility_floor']} (never below {cfg['plausibility_floor_min']}), composite plausibility = "
          + " + ".join(f"{_f(w)} × {k}" for k, w in cfg["plausibility_weights"].items())
          + f"; beam {cfg['beam']}, at most {cfg['diversity_guard']['max_from_one_parent']} survivors per parent.",
          "- Badness scale: rubric v2 (steps 1–4) scores badness relative to each step's parent world; rubric v3 "
          "(step 5) scores it as an absolute state against the 2026 baseline, so the final selection picks the "
          "worst 2036 rather than the sharpest last two years. Selection only compares runs within a step.",
          "- Pilot and repeated attempts at step 1 (to fix the output schema, token budget, prompt rules and judge "
          "rubric) were cleared before the final runs; their run files are in git history and their cost is in "
          "`runs/spend_ledger.json`.", "",
          "## Spend", "",
          f"{money['batches']} Message Batches, ${money['total']:.2f} recorded in `runs/spend_ledger.json` "
          f"(actual cost from API-reported usage at batch prices), pilots included:", "",
          "| Step | Recorded spend |", "|---|---|"]
    for s in sorted(money["by_step"]):
        L.append(f"| {s} | ${money['by_step'][s]:.2f} |")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------- command

def build(paths) -> dict[str, str]:
    """{relative path: content} for everything `report` writes. Raises ReportError, writing nothing."""
    cfg = load_sim_config(paths)
    data = load_all(paths, cfg)
    final = data["steps"][-1]
    out = {"lineage.md": render_lineage(paths, cfg, data),
           "report/README.md": index(data, cfg, spend(paths))}
    for lid in data["doc"][final]["lineages"]:
        out[f"report/{lid}.md"] = dossier(lid, data, cfg)
    return out


def main(paths, args) -> int:
    try:
        files = build(paths)
    except ReportError as e:
        print(f"report: {e}")
        return 1
    stale = [p for p in paths.report.glob("*.md") if f"report/{p.name}" not in files] if paths.report.exists() else []
    for p in stale:
        p.unlink()
    for rel, text in files.items():
        write_text_atomic(paths.root / rel, text)
    print("selection reproduced for every step; wrote " + ", ".join(files)
          + (f"; removed stale {', '.join(p.name for p in stale)}" if stale else ""))
    return 0
