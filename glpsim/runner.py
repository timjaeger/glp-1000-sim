"""The real Message Batches path for `generate` and `judge`: submit, poll, collect,
validate, repair once, write run files.

Safety properties:
  * The cost guardrail runs before every submission (main and repair), against
    the step's recorded spend plus this batch's worst-case estimate.
  * A batch's id is written to runs/stepN/_state_<kind>.json the moment it is
    created, so an interrupted command is resumed with --resume, never resubmitted.
  * The API key comes from GLP_SIM_API_KEY, never ANTHROPIC_API_KEY (the cloud
    runtime strips that one), and is handed straight to the client. The client is
    pinned to https://api.anthropic.com so the runtime's own ANTHROPIC_BASE_URL
    cannot redirect it. Nothing here prints, logs or stores the key.
  * Every run ends with a run file: ok, invalid (failed after one repair) or
    error (refusal, API error, expiry), with the raw output kept for invalid ones.

`get_client` is the only place the SDK is constructed; tests replace it.
"""
from __future__ import annotations

import json
import os
import statistics
import time
from datetime import datetime, timezone

from . import batch, render, schemas
from .common import dump_json, load_json, step_year

MAX_ERRORS_IN_REPAIR = 40

API_KEY_ENV = "GLP_SIM_API_KEY"
API_BASE_URL = "https://api.anthropic.com"


class MissingApiKey(RuntimeError):
    pass


def get_client():
    """Build the SDK client from GLP_SIM_API_KEY, pinned to the public API.

    The key and base_url are passed explicitly, so the SDK never falls back to
    ANTHROPIC_API_KEY or ANTHROPIC_BASE_URL from the environment."""
    key = os.environ.get(API_KEY_ENV)
    if not key:
        raise MissingApiKey(f"{API_KEY_ENV} is not set in this environment. Add it to the cloud "
                            f"environment's variables and start a new session (see CLAUDE.md).")
    import anthropic
    return anthropic.Anthropic(api_key=key, base_url=API_BASE_URL)


def client_or_report():
    """get_client(), or print why it failed and return None. Never prints the key."""
    try:
        return get_client()
    except MissingApiKey as e:
        print(f"{e} Nothing submitted.")
    except Exception as e:
        print(f"could not construct the Anthropic client ({type(e).__name__}). Nothing submitted.")
    return None


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- state

def state_path(paths, step: int, kind: str):
    return paths.step_runs(step) / f"_state_{kind}.json"


def load_state(paths, step: int, kind: str) -> dict | None:
    p = state_path(paths, step, kind)
    return load_json(p) if p.exists() else None


def save_state(paths, state: dict) -> None:
    errs = schemas.errors(schemas.validator(paths, "batch_state"), state)
    if errs:
        raise RuntimeError("internal: batch state failed its schema: " + "; ".join(errs))
    dump_json(state_path(paths, state["step"], state["kind"]), state)


def step_spent(paths, step: int) -> float:
    """Recorded spend for the step: actual where collected, worst-case estimate otherwise."""
    total = 0.0
    for kind in ("generate", "judge"):
        st = load_state(paths, step, kind)
        for b in (st or {}).get("batches", []):
            total += b["actual_usd"] if b.get("actual_usd") is not None else b["estimate_usd"]
    return total


# ---------------------------------------------------------------- API calls

class ApiFailure(RuntimeError):
    pass


def _api_error_types():
    try:
        import anthropic
        return (anthropic.APIStatusError, anthropic.APIConnectionError)
    except Exception:
        return (RuntimeError,)


def submit(client, requests: list[dict]) -> str:
    try:
        b = client.messages.batches.create(requests=requests)
    except _api_error_types() as e:
        status = getattr(e, "status_code", None)
        raise ApiFailure(f"batch create failed ({type(e).__name__}{f' {status}' if status else ''}): "
                         f"{getattr(e, 'message', str(e))}") from None
    except TypeError as e:
        # the SDK raises TypeError while building headers when it finds no credentials
        if "authentication" in str(e).lower():
            raise ApiFailure("batch create failed: the anthropic client found no API credentials "
                             f"({API_KEY_ENV} is empty or was not passed to the client)") from None
        raise
    return b.id


def poll(client, batch_id: str, interval: float, sleep=time.sleep) -> None:
    last = None
    while True:
        try:
            b = client.messages.batches.retrieve(batch_id)
        except _api_error_types() as e:
            print(f"  poll error ({type(e).__name__}); retrying in {interval:.0f}s")
            sleep(interval)
            continue
        c = b.request_counts
        line = (f"  {batch_id}: {b.processing_status} — processing {c.processing}, "
                f"succeeded {c.succeeded}, errored {c.errored}, canceled {c.canceled}, expired {c.expired}")
        if line != last:
            print(line, flush=True)
            last = line
        if b.processing_status == "ended":
            return
        sleep(interval)


def normalise(result) -> dict:
    """SDK result object -> plain dict (also accepts the same shape from a fake client)."""
    r = result.result
    out = {"custom_id": result.custom_id, "type": r.type, "served_model": None, "stop_reason": None,
           "text": None, "input_tokens": None, "output_tokens": None, "error": None, "refusal": None}
    if r.type == "succeeded":
        m = r.message
        u = m.usage
        out.update(
            served_model=getattr(m, "model", None),
            stop_reason=getattr(m, "stop_reason", None),
            text=next((b.text for b in m.content if getattr(b, "type", None) == "text"), None),
            input_tokens=(getattr(u, "input_tokens", 0) or 0) + (getattr(u, "cache_read_input_tokens", 0) or 0)
                         + (getattr(u, "cache_creation_input_tokens", 0) or 0),
            output_tokens=getattr(u, "output_tokens", 0) or 0,
        )
        if out["stop_reason"] == "refusal":
            sd = getattr(m, "stop_details", None)
            out["refusal"] = getattr(sd, "category", None) or "unspecified"
    elif r.type == "errored":
        e = getattr(r, "error", None)
        inner = getattr(e, "error", e)
        out["error"] = f"{getattr(inner, 'type', 'error')}: {getattr(inner, 'message', str(inner))}"
    else:
        out["error"] = r.type
    return out


def collect(client, batch_id: str) -> dict[str, dict]:
    return {n["custom_id"]: n for n in (normalise(r) for r in client.messages.batches.results(batch_id))}


def call_record(role: str, batch_id: str, model: str, res: dict) -> dict:
    return {"role": role, "batch_id": batch_id, "custom_id": res["custom_id"], "model": model,
            "served_model": res["served_model"], "result_type": res["type"],
            "stop_reason": res["stop_reason"], "input_tokens": res["input_tokens"],
            "output_tokens": res["output_tokens"]}


def usage_totals(results: dict[str, dict]) -> tuple[int, int]:
    return (sum(r["input_tokens"] or 0 for r in results.values()),
            sum(r["output_tokens"] or 0 for r in results.values()))


def result_counts(results: dict[str, dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in results.values():
        k = "refusal" if r["refusal"] else r["type"]
        out[k] = out.get(k, 0) + 1
    return out


# ---------------------------------------------------------------- output checks

def parse_json(text: str | None) -> tuple[object, list[str]]:
    if not text:
        return None, ["(root): response contained no text block"]
    try:
        return json.loads(text), []
    except json.JSONDecodeError as e:
        return None, [f"(root): not valid JSON ({e.msg} at char {e.pos}); "
                      "the response may have been cut off by max_tokens"]


def check_generation(paths, obj, year: int) -> list[str]:
    if not isinstance(obj, dict) or set(obj) != {"world", "prose"}:
        return ["(root): must be an object with exactly the keys 'world' and 'prose'"]
    from jsonschema import Draft202012Validator
    errs = [f"world/{e}" for e in schemas.errors(schemas.validator(paths, "world_state"), obj["world"])]
    prose_v = Draft202012Validator(schemas.schema(paths, "run")["properties"]["prose"])
    errs += [f"prose/{e}" for e in schemas.errors(prose_v, obj["prose"])]
    w = obj["world"]
    if isinstance(w, dict):
        if w.get("fictional") is not True:
            errs.append("world/fictional: must be true for a simulated step")
        if w.get("year") != year:
            errs.append(f"world/year: must be {year}")
    return errs


def check_judge(paths, obj) -> list[str]:
    return schemas.errors(batch.local_judge_validator(paths), obj)


def repair_request(paths, original: dict, raw_text: str | None, errors: list[str]) -> dict:
    """The original request plus the bad answer and the error list as a third turn."""
    _, user_t = render.load_template(paths, "repair")
    shown = errors[:MAX_ERRORS_IN_REPAIR]
    more = len(errors) - len(shown)
    msg = render.fill(user_t, {"errors": "\n".join(f"- {e}" for e in shown)
                               + (f"\n- … and {more} more" if more else "")})
    p = json.loads(json.dumps(original["params"]))
    if raw_text:
        p["messages"] = p["messages"] + [{"role": "assistant", "content": raw_text},
                                         {"role": "user", "content": msg}]
    # no text came back at all: there is nothing to correct, so the repair is a clean retry
    return {"custom_id": original["custom_id"], "params": p}


def read_batch_file(path) -> dict[str, dict]:
    return {r["custom_id"]: r for r in (json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l)}


# ---------------------------------------------------------------- shared submit/poll/collect

def guarded_submit(paths, cfg, args, client, state: dict, role: str, requests: list[dict],
                   batch_file, call_cfg: dict, label: str) -> str | None:
    """Estimate, check the cap, write the batch file, submit, record. None = aborted by guardrail."""
    est = batch.estimate(requests, cfg)
    spent = step_spent(paths, state["step"])
    print(batch.format_estimate(label, est, cfg, call_cfg, spent))
    if batch.over_cap(est, cfg, spent) and not args.yes:
        print(f"ABORT: estimate exceeds max_usd_per_step (${cfg['max_usd_per_step']:.2f}). "
              f"Nothing submitted. Re-run with --yes to submit anyway.")
        return None
    batch.write_batch_file(batch_file, requests)
    try:
        batch_id = submit(client, requests)
    except ApiFailure:
        batch_file.unlink(missing_ok=True)   # the record only holds batches that were sent
        raise
    state["batches"].append({
        "role": role, "batch_id": batch_id, "submitted_at": now(), "request_count": len(requests),
        "model": requests[0]["params"]["model"], "estimate_usd": est["usd_max"], "status": "submitted",
        "batch_file": str(batch_file.relative_to(paths.root)), "collected_at": None,
        "input_tokens": None, "output_tokens": None, "actual_usd": None})
    save_state(paths, state)
    print(f"submitted {label} {batch_id} ({len(requests)} requests); state in "
          f"{state_path(paths, state['step'], state['kind']).relative_to(paths.root)}")
    return batch_id


def wait_and_collect(paths, cfg, args, client, state: dict, entry: dict) -> dict[str, dict]:
    print(f"polling {entry['batch_id']} every {args.poll_interval:.0f}s (Ctrl-C is safe: resume with --resume)")
    poll(client, entry["batch_id"], args.poll_interval)
    results = collect(client, entry["batch_id"])
    tin, tout = usage_totals(results)
    entry.update(status="collected", collected_at=now(), input_tokens=tin, output_tokens=tout,
                 actual_usd=round(batch.actual_usd(cfg, entry["model"], tin, tout), 4),
                 result_counts=result_counts(results))
    print(f"  collected {len(results)} result(s): {entry['result_counts']}; "
          f"usage {tin:,} in / {tout:,} out = ${entry['actual_usd']:.2f}")
    return results


def pending_entry(state: dict, role: str) -> dict | None:
    return next((b for b in state["batches"] if b["role"] == role and b["status"] == "submitted"), None)


def check_resume(state, args, kind: str, step: int) -> str | None:
    """Returns an error message if this invocation must not proceed."""
    if state and state["phase"] != "done" and not args.resume:
        b = state["batches"][-1] if state["batches"] else None
        return (f"a {kind} for step {step} is in progress (phase {state['phase']}"
                + (f", batch {b['batch_id']} submitted {b['submitted_at']}" if b else "")
                + f"). Resume it with: python sim.py {kind} --step {step} --resume")
    if args.resume and (not state or state["phase"] == "done"):
        return f"nothing to resume for {kind} step {step}"
    return None


# ---------------------------------------------------------------- generate

def run_generate(paths, cfg, args, step, seed, plan, requests, batch_path) -> int:
    state = load_state(paths, step, "generate")
    msg = check_resume(state, args, "generate", step)
    if msg:
        print(msg); return 1
    if state and state["phase"] == "done":
        print(f"step {step} is already generated ({state_path(paths, step, 'generate').relative_to(paths.root)}). "
              f"The record is append-only: move runs/step{step}/ aside by hand to regenerate.")
        return 1
    if not state and list(paths.step_runs(step).glob("L*/*.json")):
        print(f"runs/step{step}/ already has run files but no generate state; refusing to overwrite them")
        return 1

    client = client_or_report()
    if client is None:
        return 1

    gen_model = cfg["models"]["generator"]
    year = step_year(cfg, step)
    try:
        if not state:
            state = {"kind": "generate", "step": step, "phase": "submitted", "batches": []}
            print(f"step {step} ({year}): {len(plan)} run(s), seed {seed}")
            bid = guarded_submit(paths, cfg, args, client, state, "main", requests, batch_path,
                                 cfg["generation"], "generation batch")
            if bid is None:
                return 2
            created = now()
            for item in plan:
                dump_json(paths.run_file(step, item["parent_lineage"], item["run_id"]), {
                    "run_id": item["run_id"], "step": step, "year": year,
                    "parent_lineage": item["parent_lineage"], "seed": seed, "run_index": item["run_index"],
                    "driver_modifiers": item["driver_modifiers"], "drivers": item["drivers"],
                    "status": "pending", "generator_model": gen_model, "created_at": created})

        runs = {r["run_id"]: (p, r) for p, r in
                ((p, load_json(p)) for p in sorted(paths.step_runs(step).glob("L*/s*.json")))}

        # main batch
        entry = pending_entry(state, "main")
        if entry:
            results = wait_and_collect(paths, cfg, args, client, state, entry)
            repair_ids = []
            for rid, res in results.items():
                p, run = runs[rid]
                run.setdefault("provenance", {})["generation"] = [call_record("main", entry["batch_id"], gen_model, res)]
                if res["refusal"]:
                    run.update(status="error", error=f"refusal (category {res['refusal']})")
                elif res["type"] != "succeeded":
                    run.update(status="error", error=res["error"])
                else:
                    obj, errs = parse_json(res["text"])
                    errs = errs or check_generation(paths, obj, year)
                    if not errs:
                        run.update(status="ok", world=obj["world"], prose=obj["prose"])
                        run.setdefault("validation", {})["generation"] = {"errors": [], "repair_attempted": False}
                    else:
                        run["status"] = "invalid"
                        run.setdefault("validation", {})["generation"] = {
                            "errors": errs, "raw_output": res["text"], "repair_attempted": False}
                        repair_ids.append(rid)
                dump_json(p, run)
            missing = [rid for rid, (_, r) in runs.items() if r["status"] == "pending" and rid not in results]
            for rid in missing:
                p, run = runs[rid]
                run.update(status="error", error="no result returned by the batch")
                dump_json(p, run)
            state["repair_ids"] = sorted(repair_ids)
            state["phase"] = "awaiting_repair" if repair_ids else "done"
            save_state(paths, state)

        # repair batch (one attempt)
        if state["phase"] == "awaiting_repair":
            originals = read_batch_file(paths.root / state["batches"][0]["batch_file"])
            reqs = []
            for rid in state["repair_ids"]:
                v = runs[rid][1]["validation"]["generation"]
                reqs.append(repair_request(paths, originals[rid], v.get("raw_output"), v["errors"]))
            print(f"{len(reqs)} run(s) failed validation; one repair attempt each")
            bid = guarded_submit(paths, cfg, args, client, state, "repair", reqs,
                                 paths.step_runs(step) / "_repair_batch.jsonl", cfg["generation"],
                                 "generation repair batch")
            if bid is None:
                print("the invalid runs are on disk; resume the repair with --resume --yes")
                return 2
            state["phase"] = "repair_submitted"
            save_state(paths, state)

        if state["phase"] == "repair_submitted":
            entry = pending_entry(state, "repair")
            results = wait_and_collect(paths, cfg, args, client, state, entry)
            for rid in state["repair_ids"]:
                p, run = runs[rid]
                v = run["validation"]["generation"]
                v["repair_attempted"] = True
                v.setdefault("first_errors", v["errors"])
                res = results.get(rid)
                if res is None:
                    v.update(errors=["repair: no result returned by the batch"], repaired=False)
                else:
                    run["provenance"]["generation"].append(call_record("repair", entry["batch_id"], gen_model, res))
                    if res["type"] != "succeeded" or res["refusal"]:
                        v.update(errors=[f"repair: {res['error'] or 'refusal ' + str(res['refusal'])}"], repaired=False)
                    else:
                        obj, errs = parse_json(res["text"])
                        errs = errs or check_generation(paths, obj, year)
                        if errs:
                            v.update(errors=errs, raw_output=res["text"], repaired=False)
                        else:
                            run.update(status="ok", world=obj["world"], prose=obj["prose"])
                            v.update(errors=[], raw_output=None, repaired=True)
                dump_json(p, run)
            state["phase"] = "done"
            save_state(paths, state)
    except ApiFailure as e:
        print(f"{e}\nNothing further submitted; state is saved — fix the cause and use --resume if a batch is in flight.")
        return 1
    except KeyboardInterrupt:
        print(f"\ninterrupted; the batch keeps running server-side. Resume with: "
              f"python sim.py generate --step {step} --resume")
        return 130

    return summarise(paths, step, "generate", state)


# ---------------------------------------------------------------- judge

def mean_scores(samples: list[dict]) -> dict:
    if len(samples) == 1:
        return json.loads(json.dumps(samples[0]))
    out = {"badness": {k: round(statistics.fmean(s["badness"][k] for s in samples), 2)
                       for k in samples[0]["badness"]},
           "plausibility": round(statistics.fmean(s["plausibility"] for s in samples), 2),
           "generativity": round(statistics.fmean(s["generativity"] for s in samples), 2),
           "rationale": samples[0]["rationale"]}
    return out


def run_judge(paths, cfg, args, step, loaded, runs, requests) -> int:
    from .judge import judge_custom_ids
    state = load_state(paths, step, "judge")
    msg = check_resume(state, args, "judge", step)
    if msg:
        print(msg); return 1

    client = client_or_report()
    if client is None:
        return 1

    judge_model = cfg["models"]["judge"]
    samples_n = cfg["judging"].get("judge_samples", 1)
    by_id = {r["run_id"]: (p, r) for p, r in loaded}
    cid_to_run = {cid: rid for rid in by_id for cid in judge_custom_ids(rid, samples_n)}
    jfile = paths.step_runs(step) / "_judge_batch.jsonl"
    rfile = paths.step_runs(step) / "_judge_repair_batch.jsonl"

    try:
        if not args.resume:
            # a fresh judging pass; the state file accumulates passes
            state = state or {"kind": "judge", "step": step, "phase": "done", "batches": []}
            state["phase"] = "submitted"
            print(f"step {step}: judging {len(runs)} run(s) × {samples_n} sample(s)")
            if guarded_submit(paths, cfg, args, client, state, "main", requests, jfile,
                              cfg["judging"], "judge batch") is None:
                return 2

        entry = pending_entry(state, "main")
        if entry:
            results = wait_and_collect(paths, cfg, args, client, state, entry)
            repair_ids, touched = [], set()
            for cid, res in sorted(results.items()):
                rid = cid_to_run[cid]
                p, run = by_id[rid]
                if rid not in touched:      # this pass replaces any earlier judgement of the run
                    for k in ("scores", "judge_samples"):
                        run.pop(k, None)
                    run.setdefault("provenance", {})["judge"] = []
                    run.setdefault("validation", {})["judge"] = {"errors": [], "repair_attempted": False}
                    touched.add(rid)
                run["provenance"]["judge"].append(call_record("main", entry["batch_id"], judge_model, res))
                ok, errs, text = judge_result(paths, res)
                if ok is not None:
                    run.setdefault("judge_samples", []).append({"custom_id": cid, **ok})
                else:
                    rec = run["validation"]["judge"]
                    rec["errors"] += [f"{cid}: {e}" for e in errs]
                    rec["raw_output"] = text
                    if res["type"] == "succeeded" and not res["refusal"]:
                        repair_ids.append(cid)      # only bad output is repaired, not API errors
            for rid in touched:
                p, run = by_id[rid]
                finish_judgement(run, judge_model, samples_n, rid)
                dump_json(p, run)
            state["repair_ids"] = sorted(repair_ids)
            state["phase"] = "awaiting_repair" if repair_ids else "done"
            save_state(paths, state)

        if state["phase"] == "awaiting_repair":
            main = [b for b in state["batches"] if b["role"] == "main"][-1]
            originals = read_batch_file(paths.root / main["batch_file"])
            first = collect(client, main["batch_id"])     # failing texts, re-read from the API
            reqs = []
            for cid in state["repair_ids"]:
                _, errs, text = judge_result(paths, first[cid])
                reqs.append(repair_request(paths, originals[cid], text, errs))
            print(f"{len(reqs)} judge response(s) failed validation; one repair attempt each")
            if guarded_submit(paths, cfg, args, client, state, "repair", reqs, rfile,
                              cfg["judging"], "judge repair batch") is None:
                print("resume the repair with --resume --yes")
                return 2
            state["phase"] = "repair_submitted"
            save_state(paths, state)

        if state["phase"] == "repair_submitted":
            entry = pending_entry(state, "repair")
            results = wait_and_collect(paths, cfg, args, client, state, entry)
            for rid in sorted({cid_to_run[c] for c in state["repair_ids"]}):
                p, run = by_id[rid]
                rec = run["validation"]["judge"]
                rec["repair_attempted"] = True
                rec.setdefault("first_errors", list(rec["errors"]))
                for cid in (c for c in state["repair_ids"] if cid_to_run[c] == rid):
                    rec["errors"] = [e for e in rec["errors"] if not e.startswith(cid + ": ")]
                    res = results.get(cid)
                    if res is None:
                        rec["errors"].append(f"{cid}: repair: no result returned by the batch")
                        continue
                    run["provenance"]["judge"].append(call_record("repair", entry["batch_id"], judge_model, res))
                    ok, errs, text = judge_result(paths, res)
                    if ok is not None:
                        run.setdefault("judge_samples", []).append({"custom_id": cid, **ok})
                    else:
                        rec["errors"] += [f"{cid}: repair: {e}" for e in errs]
                        rec["raw_output"] = text
                if not rec["errors"]:
                    rec["repaired"] = True
                finish_judgement(run, judge_model, samples_n, rid)
                dump_json(p, run)
            state["phase"] = "done"
            save_state(paths, state)
    except ApiFailure as e:
        print(f"{e}\nNothing further submitted; state is saved.")
        return 1
    except KeyboardInterrupt:
        print(f"\ninterrupted; the batch keeps running server-side. Resume with: "
              f"python sim.py judge --step {step} --resume")
        return 130

    return summarise(paths, step, "judge", state)


def judge_result(paths, res: dict) -> tuple[dict | None, list[str], str | None]:
    """(parsed scores or None, errors, raw text) for one judge result."""
    if res["refusal"]:
        return None, [f"refusal (category {res['refusal']})"], None
    if res["type"] != "succeeded":
        return None, [f"API {res['error']}"], None
    obj, errs = parse_json(res["text"])
    errs = errs or check_judge(paths, obj)
    return (None, errs, res["text"]) if errs else (obj, [], None)


def finish_judgement(run: dict, judge_model: str, samples_n: int, rid: str) -> None:
    """Fold parsed samples (parked in run['judge_samples'], tagged by custom_id) into `scores`
    once every sample for the run is in. A run missing a sample stays unscored and so is
    excluded by `select`, with the reason in validation.judge.errors."""
    from .judge import judge_custom_ids
    got = {s["custom_id"]: s for s in run.get("judge_samples", [])}
    cids = judge_custom_ids(rid, samples_n)
    if not all(c in got for c in cids):
        return
    samples = [{k: v for k, v in got[c].items() if k != "custom_id"} for c in cids]
    run["scores"] = {"judge_model": judge_model, **mean_scores(samples)}
    if samples_n == 1:
        run.pop("judge_samples", None)
    else:
        run["judge_samples"] = [got[c] for c in cids]
    rec = run["validation"]["judge"]
    rec["errors"] = []
    rec.pop("raw_output", None)


# ---------------------------------------------------------------- summary

def summarise(paths, step: int, kind: str, state: dict) -> int:
    runs = [load_json(p) for p in sorted(paths.step_runs(step).glob("L*/s*.json"))]
    counts: dict[str, int] = {}
    for r in runs:
        k = r["status"] if kind == "generate" else ("scored" if r.get("scores") else
                                                     ("unscored" if r["status"] == "ok" else f"skipped ({r['status']})"))
        counts[k] = counts.get(k, 0) + 1
    spent = sum(b["actual_usd"] or 0 for b in state["batches"])
    print(f"{kind} step {step} done: {counts}; this command's batches cost ${spent:.2f}; "
          f"step total recorded ${step_spent(paths, step):.2f}")
    print("next: " + (f"python sim.py judge --step {step}" if kind == "generate"
                      else f"python sim.py select --step {step}"))
    return 0
