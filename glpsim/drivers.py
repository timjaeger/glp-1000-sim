"""Driver drawing (METHOD §4) and the per-step run plan.

Every draw for run `run_index` of step `step` comes from one
`random.Random(seed + step*1000 + run_index)`, consumed in the fixed order the
drivers appear in config/drivers.json. Weighted choices are implemented here
(cumulative scan in config order over `rng.random()`) rather than via
`rng.choices`, so the draws are pinned to this code and not to a stdlib detail.

Parent-state modifiers are the `parent_modifiers` rules in config/drivers.json:
`{"if": {"path": "a.b", <op>: value}, "set": {...}}`, applied in order, later
rules overriding earlier ones. For numeric drivers `set` replaces distribution
parameters (mean, sd, clip); for categorical/ordinal/multi drivers it replaces
option weights. Ops: eq, ne, gt, gte, lt, lte, in. A missing or null path never matches.
"""
from __future__ import annotations

import random

_MISSING = object()
OPS = {
    "eq": lambda v, x: v == x,
    "ne": lambda v, x: v != x,
    "gt": lambda v, x: isinstance(v, (int, float)) and v > x,
    "gte": lambda v, x: isinstance(v, (int, float)) and v >= x,
    "lt": lambda v, x: isinstance(v, (int, float)) and v < x,
    "lte": lambda v, x: isinstance(v, (int, float)) and v <= x,
    "in": lambda v, x: v in x,
}


def driver_names(drivers_cfg: dict) -> list[str]:
    return [k for k in drivers_cfg if not k.startswith("_")]


def rng_for(seed: int, step: int, run_index: int) -> random.Random:
    return random.Random(seed + step * 1000 + run_index)


def get_path(obj, dotted: str):
    for part in dotted.split("."):
        if not isinstance(obj, dict) or part not in obj:
            return _MISSING
        obj = obj[part]
    return obj


def rule_matches(cond: dict, world: dict | None) -> bool:
    if world is None:
        return False
    ops = [k for k in cond if k != "path"]
    if len(ops) != 1 or ops[0] not in OPS:
        raise ValueError(f"modifier condition must have 'path' and one of {sorted(OPS)}: {cond}")
    v = get_path(world, cond["path"])
    if v is _MISSING or v is None:
        return False
    return OPS[ops[0]](v, cond[ops[0]])


def effective_params(name: str, spec: dict, parent_world: dict | None) -> tuple[dict, list[dict]]:
    """Distribution parameters after parent modifiers, plus the rules that fired."""
    kind = spec["type"]
    if kind == "numeric":
        params = {k: spec[k] for k in ("mean", "sd", "clip")}
    elif kind in ("categorical", "ordinal"):
        params = {"weights": {o: v["w"] for o, v in spec["options"].items()}}
    elif kind == "multi":
        params = {"draws": {int(k): w for k, w in spec["draws"].items()},
                  "weights": {o: v["w"] for o, v in spec["options"].items()}}
    else:
        raise ValueError(f"driver {name}: unknown type {kind!r}")

    fired = []
    for rule in spec.get("parent_modifiers", []):
        if not rule_matches(rule["if"], parent_world):
            continue
        fired.append(rule)
        if kind == "numeric":
            unknown = set(rule["set"]) - {"mean", "sd", "clip"}
            if unknown:
                raise ValueError(f"driver {name}: modifier sets unknown params {unknown}")
            params.update(rule["set"])
        else:
            unknown = set(rule["set"]) - set(params["weights"])
            if unknown:
                raise ValueError(f"driver {name}: modifier sets unknown options {unknown}")
            params["weights"] = {**params["weights"], **rule["set"]}
    return params, fired


def weighted_choice(rng: random.Random, weights: dict):
    total = sum(w for w in weights.values() if w > 0)
    if total <= 0:
        raise ValueError(f"all weights are zero: {weights}")
    x = rng.random() * total
    acc = 0.0
    last = None
    for option, w in weights.items():
        if w <= 0:
            continue
        acc += w
        last = option
        if x < acc:
            return option
    return last  # float edge: x == total


def draw_one(rng: random.Random, name: str, spec: dict, params: dict):
    kind = spec["type"]
    if kind == "numeric":
        if spec.get("distribution", "normal") != "normal":
            raise ValueError(f"driver {name}: only normal distributions are supported")
        lo, hi = params["clip"]
        return round(min(hi, max(lo, rng.normalvariate(params["mean"], params["sd"]))), 1)
    if kind in ("categorical", "ordinal"):
        return weighted_choice(rng, params["weights"])
    if kind == "multi":
        count = weighted_choice(rng, params["draws"])
        remaining = dict(params["weights"])
        picks = []
        for _ in range(count):
            if not any(w > 0 for w in remaining.values()):
                break
            o = weighted_choice(rng, remaining)
            picks.append(o)
            remaining[o] = 0
        return picks
    raise ValueError(f"driver {name}: unknown type {kind!r}")


def draw_drivers(drivers_cfg: dict, parent_world: dict | None, seed: int, step: int,
                 run_index: int) -> tuple[dict, list[dict]]:
    """Draw every driver for one run. Returns (drivers, modifiers_fired)."""
    rng = rng_for(seed, step, run_index)
    drivers, fired_all = {}, []
    for name in driver_names(drivers_cfg):
        spec = drivers_cfg[name]
        params, fired = effective_params(name, spec, parent_world)
        drivers[name] = draw_one(rng, name, spec, params)
        fired_all += [{"driver": name, "if": r["if"], "set": r["set"]} for r in fired]
    return drivers, fired_all


# ---------------------------------------------------------------- run plan

def split_runs(n: int, k: int, cfg: dict) -> list[int]:
    """How many runs each of k parents gets. Uses config beam_split when it fits."""
    split = cfg.get("beam_split")
    if split and len(split) == k and sum(split) == n:
        return list(split)
    base, extra = divmod(n, k)
    return [base + (1 if i < extra else 0) for i in range(k)]


def lineage_sort_key(lid: str) -> int:
    return int(lid[1:])


def plan_step(cfg: dict, drivers_cfg: dict, parents: dict[str, dict], step: int, n: int,
              seed: int) -> list[dict]:
    """The full, deterministic plan for a step: run ids, parents and drawn drivers.

    `parents` maps lineage id -> parent world state. Runs are numbered across
    the whole step (r00..r{n-1}) and assigned to parents in lineage order.
    """
    if n > 100:
        raise ValueError("run_id allows two digits; n must be <= 100")
    order = sorted(parents, key=lineage_sort_key)
    counts = split_runs(n, len(order), cfg)
    plan, idx = [], 0
    for lid, count in zip(order, counts):
        for _ in range(count):
            drivers, fired = draw_drivers(drivers_cfg, parents[lid], seed, step, idx)
            plan.append({"run_index": idx, "run_id": f"s{step}-{lid}-r{idx:02d}",
                         "parent_lineage": lid, "drivers": drivers, "driver_modifiers": fired})
            idx += 1
    return plan
