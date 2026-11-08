"""`sim.py judge` — score every ok run of a step in ONE Message Batches request.

Judge independence (METHOD §6): the prompt carries only the parent world, the
drawn drivers and the candidate. The custom_id (run id) is batch metadata the
model never sees; axis weighting is applied later in `select`.

--dry-run writes runs/stepN/_judge_batch.jsonl and readable prompts in
runs/_dry/stepN/judge/. With --fixture PATH (a run file) and no generated runs,
the dry run renders against that hand-made run instead and writes only under
runs/_dry/, so nothing fake lands in the record.
"""
from __future__ import annotations

from pathlib import Path

from . import batch, render
from .common import load_json, load_sim_config, step_year, write_text_atomic
from .generate import check_models
from .select import load_step_runs
from .world import MissingParentError, load_parents


def judge_custom_ids(run_id: str, samples: int) -> list[str]:
    return [run_id] if samples == 1 else [f"{run_id}-j{k}" for k in range(samples)]


def build(paths, cfg: dict, step: int, runs: list[dict]) -> list[dict]:
    parents = load_parents(paths, cfg, step)
    schema = batch.judge_api_schema(paths)
    samples = cfg["judging"].get("judge_samples", 1)
    requests = []
    for run in runs:
        parent = parents[run["parent_lineage"]]
        system, user = render.judge_prompt(
            paths, parent_world=parent["world"], parent_year=parent["year"],
            target_year=step_year(cfg, step), drivers=run["drivers"],
            candidate_world=run["world"], candidate_prose=run["prose"])
        for cid in judge_custom_ids(run["run_id"], samples):
            requests.append(batch.build_request(cid, model=cfg["models"]["judge"],
                                                call_cfg=cfg["judging"], system=system, user=user,
                                                schema=schema))
    return requests


def judgeable(runs: list[dict], rejudge: bool = False) -> list[dict]:
    return [r for r in runs if r.get("status") == "ok" and (rejudge or not r.get("scores"))]


def main(paths, args) -> int:
    cfg = load_sim_config(paths)
    check_models(cfg)
    step = args.step
    loaded = load_step_runs(paths, step)
    if getattr(args, "resume", False) and not args.dry_run:
        from .runner import run_judge
        return run_judge(paths, cfg, args, step, loaded, [], [])
    runs = judgeable([r for _, r in loaded], getattr(args, "rejudge", False))
    fixture = getattr(args, "fixture", None)
    use_fixture = False
    if not runs:
        if args.dry_run and fixture:
            runs = [load_json(Path(fixture))]
            use_fixture = True
        else:
            print(f"no unjudged ok runs in runs/step{step}/" +
                  (" (pass --fixture PATH to dry-run against a hand-made run)" if args.dry_run else ""))
            return 1
    try:
        requests = build(paths, cfg, step, runs)
    except MissingParentError as e:
        print(e)
        return 1

    if args.dry_run:
        base = paths.dry / f"step{step}" if use_fixture else paths.step_runs(step)
        batch_path = base / "_judge_batch.jsonl"
        batch.write_batch_file(batch_path, requests)
        out = paths.dry / f"step{step}" / "judge"
        for req in requests:
            p = req["params"]
            write_text_atomic(out / f"{req['custom_id']}.md", render.as_markdown(
                req["custom_id"], p["system"], p["messages"][-1]["content"],
                f"model {p['model']} · effort {p['output_config']['effort']} · max_tokens {p['max_tokens']}"))
        est = batch.estimate(requests, cfg)
        print(f"DRY RUN — nothing submitted. step {step}: judging {len(runs)} run(s)"
              + (f" (FIXTURE {fixture}, not a generated run)" if use_fixture else ""))
        print(batch.format_estimate("judge batch", est, cfg, cfg["judging"]))
        print(f"wrote {batch_path.relative_to(paths.root)} ({len(requests)} requests)")
        print(f"wrote readable prompts to {out.relative_to(paths.root)}/")
        return 0

    from .runner import run_judge
    return run_judge(paths, cfg, args, step, loaded, runs, requests)
