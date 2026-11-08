"""`sim.py generate` — draw drivers, render prompts, build ONE Message Batches request.

--dry-run renders every prompt and writes the batch to runs/stepN/_batch.jsonl
without constructing an API client, plus a readable copy of each prompt in
runs/_dry/stepN/generate/ (gitignored).
"""
from __future__ import annotations

from . import batch, render
from .common import load_drivers_config, load_sim_config, step_year, write_text_atomic
from .drivers import plan_step
from .world import MissingParentError, load_parents


def build(paths, cfg: dict, step: int, n: int, seed: int):
    """Returns (plan, requests). Pure apart from reading config, templates and parent worlds."""
    dcfg = load_drivers_config(paths)
    parents = load_parents(paths, cfg, step)
    plan = plan_step(cfg, dcfg, {lid: p["world"] for lid, p in parents.items()}, step, n, seed)
    schema = batch.generation_api_schema(paths)
    target_year = step_year(cfg, step)
    requests = []
    for item in plan:
        parent = parents[item["parent_lineage"]]
        system, user = render.generation_prompt(
            paths, parent_world=parent["world"], parent_prose=parent["prose"],
            parent_year=parent["year"], target_year=target_year,
            drivers=item["drivers"], dcfg=dcfg)
        requests.append(batch.build_request(item["run_id"], model=cfg["models"]["generator"],
                                            call_cfg=cfg["generation"], system=system, user=user,
                                            schema=schema, tool=batch.GENERATION_TOOL))
    return plan, requests


def check_models(cfg: dict) -> None:
    if cfg["models"]["generator"] == cfg["models"]["judge"]:
        raise SystemExit("config/sim.json: judge model must differ from generator model (METHOD §6)")


def main(paths, args) -> int:
    cfg = load_sim_config(paths)
    check_models(cfg)
    step = args.step
    n = args.n if args.n is not None else cfg["runs_per_step"]
    seed = args.seed if args.seed is not None else cfg["seed"]
    try:
        plan, requests = build(paths, cfg, step, n, seed)
    except MissingParentError as e:
        print(e)
        return 1

    batch_path = paths.step_runs(step) / "_batch.jsonl"
    if args.dry_run:
        batch.write_batch_file(batch_path, requests)
        out = paths.dry / f"step{step}" / "generate"
        for req in requests:
            p = req["params"]
            write_text_atomic(out / f"{req['custom_id']}.md", render.as_markdown(
                req["custom_id"], p["system"], p["messages"][-1]["content"],
                f"model {p['model']} · effort {p['output_config']['effort']} · max_tokens {p['max_tokens']}"))
        est = batch.estimate(requests, cfg)
        print(f"DRY RUN — nothing submitted. step {step} ({step_year(cfg, step)}), seed {seed}, "
              f"{len(plan)} run(s) from {', '.join(sorted({i['parent_lineage'] for i in plan}))}")
        from .runner import step_spent
        print(batch.format_estimate("generation batch", est, cfg, cfg["generation"], step_spent(paths, step)))
        if batch.over_cap(est, cfg):
            print("  (a real submit would abort here without --yes)")
        print(f"wrote {batch_path.relative_to(paths.root)} ({len(requests)} requests)")
        print(f"wrote readable prompts to {out.relative_to(paths.root)}/")
        return 0

    from .runner import run_generate
    return run_generate(paths, cfg, args, step, seed, plan, requests, batch_path)
