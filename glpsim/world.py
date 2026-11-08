"""Load the parent worlds a step builds on."""
from __future__ import annotations

from .common import ensure_step0, load_json, step_year


class MissingParentError(RuntimeError):
    pass


def load_parents(paths, cfg: dict, step: int) -> dict[str, dict]:
    """lineage id -> {"world", "prose", "year"} for the worlds step `step` starts from.

    Step 1 starts from the researched baseline (lineage L0, no prose);
    step N from the survivors in world/step{N-1}.json.
    """
    if step == 1:
        ensure_step0(paths)
        return {"L0": {"world": load_json(paths.world_file(0)), "prose": None,
                       "year": cfg["baseline_year"]}}
    f = paths.world_file(step - 1)
    if not f.exists():
        raise MissingParentError(f"{f.relative_to(paths.root)} does not exist — "
                                 f"run `select --step {step - 1}` first")
    doc = load_json(f)
    return {lid: {"world": e["world"], "prose": e["prose"], "year": step_year(cfg, step - 1)}
            for lid, e in doc["lineages"].items()}
