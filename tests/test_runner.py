"""The real Batch API path, end to end, against a fake client. No network, no key."""
import argparse
import copy
import json
from types import SimpleNamespace as NS

import pytest

from glpsim import generate as G
from glpsim import judge as J
from glpsim import batch, runner
from glpsim import select as S
from glpsim.common import load_json, load_sim_config
from glpsim.validate import validate_tree

from conftest import ROOT
from glpsim.common import Paths as _P
ROOT_PATHS = _P(ROOT)

FIXTURE = load_json(ROOT / "tests" / "fixtures" / "s1-L0-r00.fixture.json")
GOOD = {"world": FIXTURE["world"], "prose": FIXTURE["prose"]}


def text_result(cid, text, stop="end_turn", model="served-model"):
    msg = NS(model=model, stop_reason=stop, stop_details=None,
             content=[NS(type="thinking", thinking=""), NS(type="text", text=text)],
             usage=NS(input_tokens=1000, output_tokens=2000))
    return NS(custom_id=cid, result=NS(type="succeeded", message=msg))


def tool_result(cid, obj, model="served-model", stop="tool_use"):
    msg = NS(model=model, stop_reason=stop, stop_details=None,
             content=[NS(type="thinking", thinking=""),
                      NS(type="tool_use", id="toolu_x", name="submit_world", input=obj)],
             usage=NS(input_tokens=1000, output_tokens=2000))
    return NS(custom_id=cid, result=NS(type="succeeded", message=msg))


def test_normalise_reads_the_tool_call_input_before_any_text():
    n = runner.normalise(tool_result("a", GOOD))
    assert json.loads(n["text"]) == GOOD and n["stop_reason"] == "tool_use"
    assert json.loads(runner.normalise(text_result("b", json.dumps(GOOD)))["text"]) == GOOD


def refusal_result(cid):
    msg = NS(model="served-model", stop_reason="refusal", stop_details=NS(category="general_harms"),
             content=[], usage=NS(input_tokens=1000, output_tokens=5))
    return NS(custom_id=cid, result=NS(type="succeeded", message=msg))


def errored_result(cid):
    return NS(custom_id=cid, result=NS(type="errored",
                                       error=NS(error=NS(type="overloaded_error", message="try later"))))


class FakeBatches:
    def __init__(self, responder):
        self.responder = responder
        self.created = {}
        self.retrieve_hook = None

    def create(self, requests):
        bid = f"msgbatch_{len(self.created) + 1:02d}"
        self.created[bid] = json.loads(json.dumps(list(requests)))
        return NS(id=bid)

    def retrieve(self, bid):
        if self.retrieve_hook:
            self.retrieve_hook()
        n = len(self.created[bid])
        return NS(processing_status="ended",
                  request_counts=NS(processing=0, succeeded=n, errored=0, canceled=0, expired=0))

    def results(self, bid):
        for req in self.created[bid]:
            yield self.responder(bid, req)


class FakeClient:
    def __init__(self, responder):
        self.messages = NS(batches=FakeBatches(responder))


def is_repair(req):
    return len(req["params"]["messages"]) == 3 or req.get("_repair")


def bad_world_text():
    w = copy.deepcopy(GOOD)
    w["world"]["access"]["gray_market"] = "everywhere"
    return json.dumps(w)


def gen_responder(bid, req):
    cid = req["custom_id"]
    n_msgs = len(req["params"]["messages"])
    idx = int(cid[-2:])
    if idx == 0:
        return text_result(cid, json.dumps(GOOD))
    if idx == 1:      # invalid, fixed by the repair
        return text_result(cid, json.dumps(GOOD) if n_msgs == 3 else bad_world_text())
    if idx == 2:
        return refusal_result(cid)
    if idx == 3:      # invalid both times
        return text_result(cid, bad_world_text())
    if idx == 4:      # malformed JSON (not a max_tokens cut-off), then a clean answer
        return text_result(cid, json.dumps(GOOD) if n_msgs == 3 else '{"world": {"year": 20')
    return errored_result(cid)


CLAIMS = [  # quotes that exist verbatim in the fixture world / prose
    {"quote": "FDA opens shortage-import pathway", "field": "world/events/0/event", "why": "w1"},
    {"quote": '"us_adults_ever_used_pct": 29', "field": "world/population/us_adults_ever_used_pct", "why": "w2"},
    {"quote": "hand-written placeholder", "field": "prose/headline", "why": "w3"},
]


def scores(p=7, b=6, gen=5, axes=None):
    """A rubric-v2 judge response; by default all three sub-axes = p, so the composite is p."""
    return {"least_plausible_claims": copy.deepcopy(CLAIMS),
            "badness": {d: b for d in ("flourishing", "autonomy", "inequality", "public_health",
                                       "cohesion", "epistemic", "overall")},
            "plausibility_axes": axes or {"driver_fidelity": p, "mechanism": p, "magnitude": p},
            "generativity": gen,
            "rationale": {"badness": "rb", "plausibility": "rp", "generativity": "rg"}}


def single_sample(repo):
    """Pin judge_samples to 1 in the test repo's config (the path most tests exercise)."""
    cfg = load_sim_config(repo)
    cfg["judging"]["judge_samples"] = 1
    (repo.config / "sim.json").write_text(json.dumps(cfg))


def gargs(**kw):
    d = dict(step=1, n=6, seed=None, dry_run=False, yes=False, resume=False, poll_interval=0)
    d.update(kw)
    return argparse.Namespace(**d)


def jargs(**kw):
    d = dict(step=1, dry_run=False, fixture=None, rejudge=False, yes=False, resume=False, poll_interval=0)
    d.update(kw)
    return argparse.Namespace(**d)


@pytest.fixture
def client(monkeypatch):
    c = FakeClient(gen_responder)
    monkeypatch.setattr(runner, "get_client", lambda: c)
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    return c


def run(repo, rid):
    return load_json(repo.run_file(1, "L0", rid))


# ---------------------------------------------------------------- generate

def test_generate_submits_one_batch_validates_and_repairs_once(repo, client, capsys):
    assert G.main(repo, gargs()) == 0
    b = client.messages.batches.created
    assert list(b) == ["msgbatch_01", "msgbatch_02"]              # main + one repair batch
    assert len(b["msgbatch_01"]) == 6
    assert sorted(r["custom_id"] for r in b["msgbatch_02"]) == ["s1-L0-r01", "s1-L0-r03", "s1-L0-r04"]

    cfg = load_sim_config(repo)
    main_req = b["msgbatch_01"][0]["params"]
    assert main_req["model"] == cfg["models"]["generator"] and "temperature" not in main_req

    r0 = run(repo, "s1-L0-r00")
    assert r0["status"] == "ok" and r0["world"]["fictional"] is True
    assert r0["generator_model"] == cfg["models"]["generator"]
    assert r0["provenance"]["generation"][0]["served_model"] == "served-model"
    assert r0["seed"] == cfg["seed"] and r0["run_index"] == 0

    r1 = run(repo, "s1-L0-r01")
    assert r1["status"] == "ok"
    v = r1["validation"]["generation"]
    assert v["repair_attempted"] and v["repaired"] and v["errors"] == [] and v["raw_output"] is None
    assert any("gray_market" in e for e in v["first_errors"])
    assert [c["role"] for c in r1["provenance"]["generation"]] == ["main", "repair"]
    rep = next(r for r in b["msgbatch_02"] if r["custom_id"] == "s1-L0-r01")["params"]["messages"]
    assert rep[1]["role"] == "assistant" and "everywhere" in rep[1]["content"]
    assert "gray_market" in rep[2]["content"] and "did not pass validation" in rep[2]["content"]

    r2 = run(repo, "s1-L0-r02")
    assert r2["status"] == "error" and "refusal" in r2["error"] and "world" not in r2

    r3 = run(repo, "s1-L0-r03")                    # failed after one repair: kept, marked invalid
    assert r3["status"] == "invalid" and "world" not in r3
    assert r3["validation"]["generation"]["repair_attempted"] is True
    assert "everywhere" in r3["validation"]["generation"]["raw_output"]

    r4 = run(repo, "s1-L0-r04")
    assert r4["status"] == "ok" and r4["validation"]["generation"]["repaired"]
    assert "not valid JSON" in r4["validation"]["generation"]["first_errors"][0]

    r5 = run(repo, "s1-L0-r05")
    assert r5["status"] == "error" and "overloaded_error" in r5["error"]

    st = load_json(repo.step_runs(1) / "_state_generate.json")
    assert st["phase"] == "done" and [x["role"] for x in st["batches"]] == ["main", "repair"]
    assert st["batches"][0]["actual_usd"] == pytest.approx((5000 * 2.0 + 8005 * 10.0) / 1e6, abs=1e-4)   # errored result has no usage
    assert (repo.step_runs(1) / "_batch.jsonl").exists()
    assert (repo.step_runs(1) / "_repair_batch.jsonl").exists()

    checked, problems = validate_tree(repo)
    assert problems == []
    assert "runs/step1/_state_generate.json" in checked


def test_truncated_generation_is_invalid_and_never_repaired(repo, monkeypatch):
    def responder(bid, req):     # every call cut off mid tool call, as in step 1 attempt 3
        cid = req["custom_id"]
        if int(cid[-2:]) == 0:
            return text_result(cid, json.dumps(GOOD))
        return tool_result(cid, {}, stop="max_tokens")
    c = FakeClient(responder)
    monkeypatch.setattr(runner, "get_client", lambda: c)
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    assert G.main(repo, gargs()) == 0
    assert list(c.messages.batches.created) == ["msgbatch_01"]          # no repair batch
    assert run(repo, "s1-L0-r00")["status"] == "ok"
    r1 = run(repo, "s1-L0-r01")
    v = r1["validation"]["generation"]
    assert r1["status"] == "invalid" and "world" not in r1 and v["repair_attempted"] is False
    assert "truncated at max_tokens" in v["errors"][0]
    assert load_json(repo.step_runs(1) / "_state_generate.json")["phase"] == "done"
    assert validate_tree(repo)[1] == []


def test_cost_guardrail_aborts_before_submitting(repo, client, capsys):
    cfg = load_sim_config(repo)
    cfg["max_usd_per_submission"] = 0.01
    (repo.config / "sim.json").write_text(json.dumps(cfg))
    assert G.main(repo, gargs()) == 2
    assert client.messages.batches.created == {}
    assert not list(repo.step_runs(1).glob("L*/*.json"))
    assert "ABORT" in capsys.readouterr().out
    assert G.main(repo, gargs(yes=True)) == 0                # --yes overrides
    assert len(client.messages.batches.created) == 2


def test_interrupted_poll_resumes_without_resubmitting(repo, client, capsys):
    def boom():
        raise KeyboardInterrupt
    client.messages.batches.retrieve_hook = boom
    assert G.main(repo, gargs()) == 130
    st = load_json(repo.step_runs(1) / "_state_generate.json")
    assert st["phase"] == "submitted" and st["batches"][0]["batch_id"] == "msgbatch_01"
    assert run(repo, "s1-L0-r00")["status"] == "pending"
    assert validate_tree(repo)[1] == []                       # pending runs are valid records

    assert G.main(repo, gargs()) == 1                         # refuses to start a second batch
    assert "--resume" in capsys.readouterr().out
    client.messages.batches.retrieve_hook = None
    assert G.main(repo, gargs(resume=True)) == 0
    assert list(client.messages.batches.created) == ["msgbatch_01", "msgbatch_02"]
    assert run(repo, "s1-L0-r00")["status"] == "ok"


def test_completed_step_is_not_regenerated(repo, client, capsys):
    assert G.main(repo, gargs()) == 0
    assert G.main(repo, gargs()) == 1
    assert "already generated" in capsys.readouterr().out
    assert G.main(repo, gargs(resume=True)) == 1


def test_missing_key_or_client_failure_submits_nothing(repo, monkeypatch, capsys):
    def no_client():
        raise RuntimeError("no credentials")
    monkeypatch.setattr(runner, "get_client", no_client)
    assert G.main(repo, gargs()) == 1
    assert not repo.step_runs(1).exists() or not list(repo.step_runs(1).glob("L*/*.json"))
    assert "Nothing submitted" in capsys.readouterr().out


# ---------------------------------------------------------------- judge, then select

def judge_responder_factory(plaus_by_run=None, bad_once=()):
    plaus_by_run = plaus_by_run or {}

    def responder(bid, req):
        cid = req["custom_id"]
        rid = cid.split("-j")[0]
        assert "s1-L0" not in json.dumps(req["params"])       # judge never sees the run id
        n_msgs = len(req["params"]["messages"])
        if rid in bad_once and n_msgs == 1:
            s = scores(); s["plausibility_axes"]["magnitude"] = 11                # out of range -> repair
            return text_result(cid, json.dumps(s))
        idx = int(rid[-2:])
        j = int(cid.split("-j")[1]) if "-j" in cid else 0
        return text_result(cid, json.dumps(scores(p=plaus_by_run.get(rid, 7), b=4 + idx + j * 0.5)))
    return responder


def test_judge_then_select_end_to_end(repo, client, monkeypatch):
    assert G.main(repo, gargs()) == 0
    single_sample(repo)
    jc = FakeClient(judge_responder_factory(bad_once=("s1-L0-r04",)))
    monkeypatch.setattr(runner, "get_client", lambda: jc)
    assert J.main(repo, jargs()) == 0

    created = jc.messages.batches.created
    assert len(created["msgbatch_01"]) == 3                  # the three ok runs only
    assert {r["params"]["model"] for r in created["msgbatch_01"]} == {load_sim_config(repo)["models"]["judge"]}
    assert [r["custom_id"] for r in created["msgbatch_02"]] == ["s1-L0-r04"]

    r0 = run(repo, "s1-L0-r00")
    assert r0["scores"]["judge_model"] == load_sim_config(repo)["models"]["judge"]
    assert r0["scores"]["plausibility"] == 7 and "judge_samples" not in r0
    r4 = run(repo, "s1-L0-r04")
    assert r4["scores"]["plausibility"] == 7 and r4["validation"]["judge"]["repaired"] is True
    assert "scores" not in run(repo, "s1-L0-r03")            # invalid runs are never judged

    assert validate_tree(repo)[1] == []
    assert S.main(repo, argparse.Namespace(step=1, force=False)) == 0
    doc = load_json(repo.world_file(1))
    assert [e["source_run"] for e in doc["lineages"].values()] == ["s1-L0-r04", "s1-L0-r01", "s1-L0-r00"]
    assert validate_tree(repo)[1] == []


def test_judge_samples_are_averaged(repo, client, monkeypatch):
    assert G.main(repo, gargs()) == 0
    cfg = load_sim_config(repo)
    cfg["judging"]["judge_samples"] = 3
    (repo.config / "sim.json").write_text(json.dumps(cfg))
    jc = FakeClient(judge_responder_factory())
    monkeypatch.setattr(runner, "get_client", lambda: jc)
    assert J.main(repo, jargs()) == 0
    r0 = run(repo, "s1-L0-r00")
    assert len(jc.messages.batches.created["msgbatch_01"]) == 9
    assert r0["scores"]["badness"]["flourishing"] == pytest.approx(4.5)   # mean of 4, 4.5, 5
    assert [s["custom_id"] for s in r0["judge_samples"]] == ["s1-L0-r00-j0", "s1-L0-r00-j1", "s1-L0-r00-j2"]
    assert validate_tree(repo)[1] == []


def test_judge_refusal_leaves_run_unscored_with_reason(repo, client, monkeypatch):
    assert G.main(repo, gargs()) == 0
    single_sample(repo)

    def responder(bid, req):
        cid = req["custom_id"]
        return refusal_result(cid) if cid == "s1-L0-r00" else text_result(cid, json.dumps(scores()))
    jc = FakeClient(responder)
    monkeypatch.setattr(runner, "get_client", lambda: jc)
    assert J.main(repo, jargs()) == 0
    r0 = run(repo, "s1-L0-r00")
    assert "scores" not in r0 and "refusal" in r0["validation"]["judge"]["errors"][0]
    assert len(jc.messages.batches.created) == 1             # refusals are not "repaired"
    assert validate_tree(repo)[1] == []


# ---------------------------------------------------------------- the real SDK, mock transport

def test_real_sdk_accepts_our_requests_and_sends_them_unchanged(repo):
    """The anthropic SDK builds the batch POST from our dicts. An in-process mock transport
    captures it: nothing leaves the machine, and an explicit dummy key means no env lookup."""
    anthropic = pytest.importorskip("anthropic")
    httpx2 = pytest.importorskip("httpx2")
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json={
            "id": "msgbatch_mock", "type": "message_batch", "processing_status": "in_progress",
            "request_counts": {"processing": 1, "succeeded": 0, "errored": 0, "canceled": 0, "expired": 0},
            "ended_at": None, "created_at": "2026-11-08T00:00:00Z", "expires_at": "2026-11-09T00:00:00Z",
            "cancel_initiated_at": None, "archived_at": None, "results_url": None})

    client = anthropic.Anthropic(api_key="dummy-not-a-key", base_url="http://mock.invalid",
                                 http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)))
    _, requests = G.build(repo, load_sim_config(repo), 1, 2, load_sim_config(repo)["seed"])
    assert runner.submit(client, requests) == "msgbatch_mock"
    assert seen["url"].endswith("/v1/messages/batches")
    assert seen["body"]["requests"] == requests


def test_missing_credentials_at_request_time_is_reported_and_leaves_no_trace(repo, monkeypatch, capsys):
    """The SDK constructs fine without a key and raises TypeError when building the request."""
    class NoAuthBatches(FakeBatches):
        def create(self, requests):
            raise TypeError('"Could not resolve authentication method. Expected one of api_key, ..."')
    c = FakeClient(gen_responder)
    c.messages.batches = NoAuthBatches(gen_responder)
    monkeypatch.setattr(runner, "get_client", lambda: c)
    assert G.main(repo, gargs()) == 1
    out = capsys.readouterr().out
    assert "no API credentials" in out and "Traceback" not in out
    assert not (repo.step_runs(1) / "_batch.jsonl").exists()
    assert not (repo.step_runs(1) / "_state_generate.json").exists()


# ---------------------------------------------------------------- client construction

def test_client_is_pinned_to_public_api_and_reads_glp_sim_api_key(monkeypatch):
    """The cloud runtime sets its own ANTHROPIC_BASE_URL; it must not redirect our client,
    and the key must come from GLP_SIM_API_KEY, not ANTHROPIC_API_KEY."""
    pytest.importorskip("anthropic")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://runtime-proxy.invalid")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "wrong-key")
    monkeypatch.setenv("GLP_SIM_API_KEY", "dummy-not-a-key")
    c = runner.get_client()
    assert str(c.base_url).rstrip("/") == "https://api.anthropic.com"
    assert c.api_key == "dummy-not-a-key"


def test_missing_glp_sim_api_key_is_a_clear_error(repo, monkeypatch, capsys):
    monkeypatch.delenv("GLP_SIM_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "would-be-ignored")
    with pytest.raises(runner.MissingApiKey, match="GLP_SIM_API_KEY"):
        runner.get_client()
    assert G.main(repo, gargs()) == 1
    out = capsys.readouterr().out
    assert "GLP_SIM_API_KEY is not set" in out and "Nothing submitted" in out
    assert "would-be-ignored" not in out and "Traceback" not in out
    assert not (repo.step_runs(1) / "_state_generate.json").exists()


# ---------------------------------------------------------------- spend ledger

def test_spend_ledger_survives_clearing_a_step_and_never_double_counts(repo, client):
    import shutil
    assert G.main(repo, gargs()) == 0
    led = runner.load_ledger(repo)
    assert [b["role"] for b in led["batches"]] == ["main", "repair"]
    assert all(b["status"] == "collected" and b["actual_usd"] is not None for b in led["batches"])
    first = runner.step_spent(repo, 1)
    assert first == pytest.approx(sum(b["actual_usd"] for b in led["batches"]))
    shutil.rmtree(repo.step_runs(1))                    # a failed attempt cleared before a rerun
    assert runner.step_spent(repo, 1) == pytest.approx(first)
    assert G.main(repo, gargs()) == 0                   # attempt 2: counted on top, once
    assert len(runner.load_ledger(repo)["batches"]) == 4
    assert runner.step_spent(repo, 1) == pytest.approx(2 * first)
    assert runner.step_spent(repo, 2) == 0
    assert validate_tree(repo)[1] == []


def test_total_cap_counts_every_attempt_but_the_submission_cap_does_not(repo, client, capsys):
    import shutil
    assert G.main(repo, gargs()) == 0
    spent = runner.total_spent(repo)
    assert spent == pytest.approx(runner.step_spent(repo, 1)) and spent > 0
    shutil.rmtree(repo.step_runs(1))                    # a cleared pilot still counts toward the total
    assert runner.total_spent(repo) == pytest.approx(spent)
    est = batch.estimate(G.build(repo, load_sim_config(repo), 1, 6, load_sim_config(repo)["seed"])[1],
                         load_sim_config(repo))
    cfg = load_sim_config(repo)
    cfg["max_usd_total"] = spent + est["usd_max"] - 0.01   # the batch alone fits; with history it does not
    (repo.config / "sim.json").write_text(json.dumps(cfg))
    capsys.readouterr()
    assert G.main(repo, gargs()) == 2
    out = capsys.readouterr().out
    assert f"total: ${spent:.2f} recorded" in out and "exceeds max_usd_total" in out
    assert "exceeds max_usd_per_submission" not in out
    cfg["max_usd_total"] = 150                          # raise the total: the same batch now goes
    (repo.config / "sim.json").write_text(json.dumps(cfg))
    assert G.main(repo, gargs()) == 0
    assert runner.total_spent(repo) == pytest.approx(2 * spent)


def test_total_spans_steps(repo):
    led = {"batches": [
        {"step": s, "kind": "generate", "role": "main", "batch_id": f"b{s}", "model": "m",
         "submitted_at": "t", "request_count": 1, "estimate_usd": 9.0, "status": "collected",
         "actual_usd": a} for s, a in ((1, 1.5), (2, 2.25), (3, None))]}
    repo.runs.mkdir(parents=True, exist_ok=True)
    (repo.runs / "spend_ledger.json").write_text(json.dumps(led))
    assert runner.total_spent(repo) == pytest.approx(1.5 + 2.25 + 9.0)   # uncollected: estimate
    assert runner.step_spent(repo, 2) == pytest.approx(2.25)


# ---------------------------------------------------------------- rubric v2

def test_v2_composite_is_the_weighted_sub_axes_and_misquotes_are_repaired(repo, client, monkeypatch):
    assert G.main(repo, gargs()) == 0
    single_sample(repo)
    axes = {"driver_fidelity": 8, "mechanism": 5, "magnitude": 4}

    def responder(bid, req):
        cid = req["custom_id"]
        s = scores(axes=dict(axes))
        if cid == "s1-L0-r01" and len(req["params"]["messages"]) == 1:
            s["least_plausible_claims"][1]["quote"] = "a sentence the candidate never wrote"
        return text_result(cid, json.dumps(s))
    jc = FakeClient(responder)
    monkeypatch.setattr(runner, "get_client", lambda: jc)
    assert J.main(repo, jargs()) == 0

    r0 = run(repo, "s1-L0-r00")["scores"]
    assert r0["rubric"] == "v2" and r0["plausibility_axes"] == axes
    assert r0["plausibility"] == pytest.approx(5.1)                  # 0.2·8 + 0.3·5 + 0.5·4, in code
    assert r0["plausibility_weights"] == {"driver_fidelity": 0.2, "mechanism": 0.3, "magnitude": 0.5}
    assert [c["field"] for c in r0["least_plausible_claims"]][0] == "world/events/0/event"
    assert [r["custom_id"] for r in jc.messages.batches.created["msgbatch_02"]] == ["s1-L0-r01"]
    rep = jc.messages.batches.created["msgbatch_02"][0]["params"]["messages"][2]["content"]
    assert "least_plausible_claims/1/quote: not found verbatim" in rep
    r1 = run(repo, "s1-L0-r01")
    assert r1["scores"]["plausibility"] == pytest.approx(5.1) and r1["validation"]["judge"]["repaired"]
    assert validate_tree(repo)[1] == []


def test_quote_matching_ignores_case_whitespace_and_typographic_quotes():
    run_ = {"world": {"note": "Imported ‘near-generic’ semaglutide —  under shortage"},
            "prose": {"headline": "Thin  Got Cheap"}}
    ok = [{"quote": "imported 'near-generic' semaglutide - under", "field": "f", "why": "w"},
          {"quote": "“Thin Got Cheap.”", "field": "f", "why": "w"},
          {"quote": '"note": "Imported', "field": "f", "why": "w"}]
    assert runner.quote_errors(ok, run_) == []
    assert len(runner.quote_errors([{"quote": "Thin got expensive", "field": "f", "why": "w"}], run_)) == 1


def test_rejudge_keeps_the_superseded_scores(repo, client, monkeypatch):
    assert G.main(repo, gargs()) == 0
    jc = FakeClient(lambda bid, req: text_result(req["custom_id"], json.dumps(scores(p=5))))
    monkeypatch.setattr(runner, "get_client", lambda: jc)
    assert J.main(repo, jargs()) == 0
    first = run(repo, "s1-L0-r00")["scores"]
    jc2 = FakeClient(lambda bid, req: text_result(req["custom_id"], json.dumps(scores(p=8))))
    monkeypatch.setattr(runner, "get_client", lambda: jc2)
    assert J.main(repo, jargs(rejudge=True)) == 0
    r0 = run(repo, "s1-L0-r00")
    assert r0["scores"]["plausibility"] == 8
    (old,) = r0["superseded_scores"]
    assert {k: v for k, v in old.items() if k != "superseded_at"} == first and old["superseded_at"]
    assert validate_tree(repo)[1] == []


def test_each_judging_pass_keeps_its_own_batch_file(repo, client, monkeypatch):
    assert G.main(repo, gargs()) == 0
    jc = FakeClient(lambda bid, req: text_result(req["custom_id"], json.dumps(scores())))
    monkeypatch.setattr(runner, "get_client", lambda: jc)
    assert J.main(repo, jargs()) == 0
    p1 = (repo.step_runs(1) / "_judge_batch.jsonl").read_text()
    assert J.main(repo, jargs(rejudge=True, dry_run=True)) == 0
    assert (repo.step_runs(1) / "_judge_batch.jsonl").read_text() == p1          # dry run left it alone
    assert J.main(repo, jargs(rejudge=True)) == 0
    assert (repo.step_runs(1) / "_judge_batch.jsonl").read_text() == p1
    st = load_json(repo.step_runs(1) / "_state_judge.json")
    assert [b["batch_file"] for b in st["batches"]] == ["runs/step1/_judge_batch.jsonl",
                                                         "runs/step1/_judge_batch_p2.jsonl"]


def test_three_samples_average_sub_axes_then_weight_the_composite():
    w = load_sim_config(ROOT_PATHS)["plausibility_weights"]
    s = [scores(axes={"driver_fidelity": f, "mechanism": m, "magnitude": g})
         for f, m, g in ((9, 6, 4), (8, 7, 5), (7, 8, 6))]
    out = runner.mean_scores(s, w)
    assert out["plausibility_axes"] == {"driver_fidelity": 8, "mechanism": 7, "magnitude": 5}
    assert out["plausibility"] == pytest.approx(0.2 * 8 + 0.3 * 7 + 0.5 * 5)   # 6.2
    assert out["least_plausible_claims"] == s[0]["least_plausible_claims"]


def test_world_sent_as_a_json_string_is_decoded_not_repaired(repo, monkeypatch):
    def responder(bid, req):
        cid = req["custom_id"]
        return tool_result(cid, {"world": json.dumps(GOOD["world"]), "prose": GOOD["prose"]})
    c = FakeClient(responder)
    monkeypatch.setattr(runner, "get_client", lambda: c)
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    assert G.main(repo, gargs()) == 0
    assert list(c.messages.batches.created) == ["msgbatch_01"]           # no repair batch
    r0 = run(repo, "s1-L0-r00")
    assert r0["status"] == "ok" and r0["world"] == GOOD["world"]
    assert r0["validation"]["generation"]["decoded_string_fields"] == ["world"]
    assert validate_tree(repo)[1] == []


def test_decode_leaves_non_json_strings_for_validation_to_reject():
    obj, decoded = runner.decode_string_fields({"world": "not json", "prose": "[1, 2]"})
    assert decoded == [] and obj == {"world": "not json", "prose": "[1, 2]"}


# ---------------------------------------------------------------- judge cut-offs

def cut_off_result(cid):
    return text_result(cid, '{"least_plausible_claims": [{"quote": "FDA op', stop="max_tokens")


def judge_with(repo, monkeypatch, responder):
    jc = FakeClient(responder)
    monkeypatch.setattr(runner, "get_client", lambda: jc)
    assert J.main(repo, jargs()) == 0
    return jc


def test_cut_off_sample_is_discarded_and_re_requested_clean(repo, client, monkeypatch):
    assert G.main(repo, gargs()) == 0
    def responder(bid, req):
        cid = req["custom_id"]
        if cid == "s1-L0-r00-j1" and bid == "msgbatch_01":
            return cut_off_result(cid)
        return text_result(cid, json.dumps(scores(axes={"driver_fidelity": 8, "mechanism": 6, "magnitude": 7})))
    jc = judge_with(repo, monkeypatch, responder)
    (retry,) = jc.messages.batches.created["msgbatch_02"]
    original = next(r for r in jc.messages.batches.created["msgbatch_01"] if r["custom_id"] == "s1-L0-r00-j1")
    assert retry == original                                   # the same request again: nothing of the cut-off kept
    r0 = run(repo, "s1-L0-r00")
    assert [s["custom_id"] for s in r0["judge_samples"]] == ["s1-L0-r00-j0", "s1-L0-r00-j1", "s1-L0-r00-j2"]
    assert r0["scores"]["plausibility_axes"]["magnitude"] == 7 and "dropped_samples" not in r0["validation"]["judge"]
    assert [c["role"] for c in r0["provenance"]["judge"]] == ["main", "main", "main", "repair"]
    assert validate_tree(repo)[1] == []


def test_sample_cut_off_twice_is_dropped_and_the_run_scored_from_two(repo, client, monkeypatch):
    assert G.main(repo, gargs()) == 0
    def responder(bid, req):
        cid = req["custom_id"]
        if cid == "s1-L0-r00-j2":
            return cut_off_result(cid)                       # main and retry both cut off
        mag = 6 if cid.endswith("j0") else 8
        return text_result(cid, json.dumps(scores(axes={"driver_fidelity": 8, "mechanism": 6, "magnitude": mag})))
    judge_with(repo, monkeypatch, responder)
    r0 = run(repo, "s1-L0-r00")
    assert [s["custom_id"] for s in r0["judge_samples"]] == ["s1-L0-r00-j0", "s1-L0-r00-j1"]
    assert r0["scores"]["plausibility_axes"]["magnitude"] == 7          # mean of the two completed, not three
    (d,) = r0["validation"]["judge"]["dropped_samples"]
    assert d["custom_id"] == "s1-L0-r00-j2" and "cut off" in d["reason"]
    assert r0["validation"]["judge"]["errors"] == []
    assert validate_tree(repo)[1] == []


def test_fewer_than_two_completed_samples_leaves_the_run_unscored_and_excluded(repo, client, monkeypatch):
    assert G.main(repo, gargs()) == 0
    def responder(bid, req):
        cid = req["custom_id"]
        if cid in ("s1-L0-r00-j1", "s1-L0-r00-j2"):
            return cut_off_result(cid)
        return text_result(cid, json.dumps(scores()))
    judge_with(repo, monkeypatch, responder)
    r0 = run(repo, "s1-L0-r00")
    assert "scores" not in r0
    assert any("only 1 of 3 judge sample(s) completed (need 2)" in e for e in r0["validation"]["judge"]["errors"])
    sel = S.select_step([run(repo, f"s1-L0-r{i:02d}") for i in range(6)], load_sim_config(repo), 1)
    assert sel.excluded["s1-L0-r00"] == "unscored"
    assert validate_tree(repo)[1] == []


def test_rejudge_appends_to_the_call_history(repo, client, monkeypatch):
    assert G.main(repo, gargs()) == 0
    judge_with(repo, monkeypatch, lambda bid, req: text_result(req["custom_id"], json.dumps(scores())))
    jc = FakeClient(lambda bid, req: text_result(req["custom_id"], json.dumps(scores())))
    monkeypatch.setattr(runner, "get_client", lambda: jc)
    assert J.main(repo, jargs(rejudge=True)) == 0
    assert len(run(repo, "s1-L0-r00")["provenance"]["judge"]) == 6       # 3 from each pass



def test_finish_judgement_records_the_rubric_it_was_given():
    w = load_sim_config(ROOT_PATHS)["plausibility_weights"]
    run = {"judge_samples": [{"custom_id": f"r-j{i}", **scores()} for i in range(3)],
           "validation": {"judge": {"errors": [], "repair_attempted": False}}}
    runner.finish_judgement(run, "judge", 3, "r", w, 2, "v3")
    assert run["scores"]["rubric"] == "v3"
    run2 = {"judge_samples": [{"custom_id": "r", **scores()}],
            "validation": {"judge": {"errors": [], "repair_attempted": False}}}
    runner.finish_judgement(run2, "judge", 1, "r", w)
    assert run2["scores"]["rubric"] == "v2"
