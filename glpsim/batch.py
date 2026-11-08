"""Message Batches request building, cost estimation and the cost guardrail.

Structured output: requests use `output_config.format` (JSON schema) rather
than forced tool use, which both configured models reject. The API accepts a
subset of JSON Schema (no numeric bounds, string lengths or array-size
constraints, `additionalProperties` must be false), so `to_api_schema` derives
that subset from the repo schemas. The full repo schema is still applied
locally to every response; that check is what triggers the repair attempt.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

from . import schemas
from .common import write_text_atomic

UNSUPPORTED_KEYS = {
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "pattern", "minItems", "maxItems", "uniqueItems",
    "minProperties", "maxProperties", "$schema", "$id", "title",
}


class SchemaShapeError(ValueError):
    pass


def to_api_schema(node, defs: dict | None = None, where: str = "#"):
    """Repo JSON Schema -> the subset accepted by structured outputs."""
    if isinstance(node, list):
        return [to_api_schema(n, defs, f"{where}/{i}") for i, n in enumerate(node)]
    if not isinstance(node, dict):
        return node
    if defs is None:
        defs = node.get("$defs", {})
    if "$ref" in node:
        ref = node["$ref"]
        if not ref.startswith("#/$defs/"):
            raise SchemaShapeError(f"{where}: only local $defs refs can be inlined, got {ref}")
        return to_api_schema(defs[ref.split("/")[-1]], defs, where)
    out = {}
    for k, v in node.items():
        if k in UNSUPPORTED_KEYS or k == "$defs":
            continue
        if k == "properties":
            out[k] = {p: to_api_schema(s, defs, f"{where}/{p}") for p, s in v.items()}
        elif k in ("items", "anyOf", "allOf"):
            out[k] = to_api_schema(v, defs, f"{where}/{k}")
        else:
            out[k] = copy.deepcopy(v)
    if isinstance(out.get("type"), list):
        types = out.pop("type")
        out = {**({"description": out.pop("description")} if "description" in out else {}),
               "anyOf": [{**out, "type": t} if t != "null" else {"type": "null"} for t in types]}
    if out.get("type") == "object":
        props = set(out.get("properties", {}))
        if out.get("additionalProperties", False) is not False:
            raise SchemaShapeError(f"{where}: additionalProperties must be false for structured output")
        out["additionalProperties"] = False
        if set(out.get("required", [])) != props:
            raise SchemaShapeError(f"{where}: structured output needs every property required "
                                   f"(missing: {sorted(props - set(out.get('required', [])))})")
    return out


NULLABLE_NOTE = "simulated step: always give a number (your best estimate), never null"


def drop_null_unions(node):
    """Collapse every `anyOf: [{type: X}, {type: null}]` to `{type: X}`.

    Union-typed parameters have exponential grammar-compilation cost: with ten
    nullable numbers the generation schema is inside the documented limits yet
    rejected as "The compiled grammar is too large". Nulls exist in the world
    schema for unknown baseline facts; a simulated step is fiction and can always
    commit to a figure, so the API constraint asks for one. The repo schema,
    which still allows null, is applied locally to every response."""
    if isinstance(node, list):
        return [drop_null_unions(n) for n in node]
    if not isinstance(node, dict):
        return node
    out = {k: drop_null_unions(v) for k, v in node.items()}
    branches = out.get("anyOf")
    if isinstance(branches, list) and len(branches) == 2 and {"type": "null"} in branches:
        (keep,) = [b for b in branches if b != {"type": "null"}]
        rest = {k: v for k, v in out.items() if k != "anyOf"}
        desc = "; ".join(d for d in (rest.pop("description", None), NULLABLE_NOTE) if d)
        out = {**keep, **rest, "description": desc}
    return out


def generation_api_schema(paths) -> dict:
    world = drop_null_unions(to_api_schema(schemas.schema(paths, "world_state")))
    world["properties"]["fictional"] = {"type": "boolean", "enum": [True],
                                        "description": "always true for a simulated step"}
    prose = to_api_schema(schemas.schema(paths, "run")["properties"]["prose"])
    return {"type": "object", "additionalProperties": False, "required": ["world", "prose"],
            "properties": {"world": world, "prose": prose}}


def judge_api_schema(paths) -> dict:
    scores = copy.deepcopy(schemas.schema(paths, "run")["properties"]["scores"])
    scores["properties"].pop("judge_model")
    scores["required"] = [r for r in scores["required"] if r != "judge_model"]
    rat = scores["properties"]["rationale"]
    rat.setdefault("additionalProperties", False)
    return to_api_schema(scores)


def local_judge_validator(paths):
    """Validates a judge response: the run schema's `scores` minus judge_model (filled by code)."""
    from jsonschema import Draft202012Validator
    s = copy.deepcopy(schemas.schema(paths, "run")["properties"]["scores"])
    s["properties"].pop("judge_model")
    s["required"] = [r for r in s["required"] if r != "judge_model"]
    return Draft202012Validator(s)


# ---------------------------------------------------------------- requests

def build_request(custom_id: str, *, model: str, call_cfg: dict, system: str, user: str,
                  schema: dict, prior: list[dict] | None = None) -> dict:
    """One Message Batches request. `prior` prepends earlier turns (used by repair)."""
    params = {
        "model": model,
        "max_tokens": call_cfg["max_tokens"],
        "system": system,
        "messages": (prior or []) + [{"role": "user", "content": user}],
        "output_config": {"effort": call_cfg["effort"],
                          "format": {"type": "json_schema", "schema": schema}},
    }
    if call_cfg.get("temperature") is not None:
        params["temperature"] = call_cfg["temperature"]
    return {"custom_id": custom_id, "params": params}


def write_batch_file(path: Path, requests: list[dict]) -> None:
    write_text_atomic(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in requests))


def request_text_chars(req: dict) -> int:
    p = req["params"]
    n = len(p.get("system", ""))
    for m in p["messages"]:
        c = m["content"]
        n += len(c) if isinstance(c, str) else sum(len(b.get("text", "")) for b in c)
    n += len(json.dumps(p["output_config"]["format"]["schema"]))
    return n


# ---------------------------------------------------------------- cost

def prices(cfg: dict, model: str) -> tuple[float, float]:
    table = cfg.get("pricing_usd_per_mtok", {})
    if model not in table:
        raise KeyError(f"no price for {model} in config/sim.json pricing_usd_per_mtok; "
                       "cannot estimate cost, refusing to continue")
    d = cfg["batch_discount"]
    return table[model]["input"] * d, table[model]["output"] * d


def estimate(requests: list[dict], cfg: dict) -> dict:
    """Worst-case estimate: input from character count, output = max_tokens for every request."""
    if not requests:
        return {"requests": 0, "input_tokens": 0, "output_tokens_max": 0, "usd_max": 0.0, "models": []}
    cpt = cfg["chars_per_token_estimate"]
    usd = 0.0
    tin = tout = 0
    models = set()
    for r in requests:
        p = r["params"]
        i = math.ceil(request_text_chars(r) / cpt)
        o = p["max_tokens"]
        pin, pout = prices(cfg, p["model"])
        usd += (i * pin + o * pout) / 1e6
        tin += i
        tout += o
        models.add(p["model"])
    return {"requests": len(requests), "input_tokens": tin, "output_tokens_max": tout,
            "usd_max": round(usd, 2), "models": sorted(models)}


def actual_usd(cfg: dict, model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = prices(cfg, model)
    return (input_tokens * pin + output_tokens * pout) / 1e6


def format_estimate(label: str, est: dict, cfg: dict, call_cfg: dict, spent: float = 0.0) -> str:
    model = est["models"][0] if est["models"] else "?"
    pin, pout = prices(cfg, model) if est["models"] else (0, 0)
    cap = cfg["max_usd_per_step"]
    total = spent + est["usd_max"]
    verdict = "within cap" if total <= cap else "OVER CAP"
    return "\n".join([
        f"{label}: {est['requests']} request(s) to {', '.join(est['models'])} "
        f"(effort {call_cfg['effort']}, max_tokens {call_cfg['max_tokens']})",
        f"  input  ~{est['input_tokens']:,} tokens (estimated at {cfg['chars_per_token_estimate']} chars/token, incl. schema)",
        f"  output <={est['output_tokens_max']:,} tokens (max_tokens per request; thinking is billed as output)",
        f"  cost   <=${est['usd_max']:.2f} at batch prices (${pin:.2f}/MTok in, ${pout:.2f}/MTok out)",
        f"  step budget: ${spent:.2f} already recorded + ${est['usd_max']:.2f} = ${total:.2f} "
        f"vs max_usd_per_step ${cap:.2f} -> {verdict}",
    ])


def over_cap(est: dict, cfg: dict, spent: float = 0.0) -> bool:
    return spent + est["usd_max"] > cfg["max_usd_per_step"]
