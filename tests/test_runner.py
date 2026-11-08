"""The real Batch API path, end to end, against a fake client. No network, no key."""
import argparse
import copy
import json
from types import SimpleNamespace as NS

import pytest

from glpsim import generate as G
from glpsim import judge as J
from glpsim import runner
from glpsim import select as S
from glpsim.common import load_json, load_sim_config
from glpsim.validate import validate_tree

from conftest import ROOT

FIXTURE = load_json(ROOT / "tests" / "fixtures" / "s1-L0-r00.fixture.json")
GOOD = {"world": FIXTURE["world"], "prose": FIXTURE["prose"]}


def text_result(cid, text, stop="end_turn", model="served-model"):
    msg = NS(model=model, stop_reason=stop, stop_details=None,
             content=[NS(type="thinking", thinking=""), NS(type="text", text=text)],
             usage=NS(input_tokens=1000, output_tokens=2000))
    return NS(custom_id=cid, result=NS(type="succeeded", message=msg))


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
    if idx == 4:      # truncated by max_tokens, then a clean answer
        return text_result(cid, json.dumps(GOOD) if n_msgs == 3 else '{"world": {"year": 20',
                           stop="end_turn" if n_msgs == 3 else "max_tokens")
    return errored_result(cid)


def scores(p=7, b=6, gen=5):
    return {"badness": {d: b for d in ("flourishing", "autonomy", "inequality", "public_health",
                                       "cohesion", "epistemic", "overall")},
            "plausibility": p, "generativity": gen,
            "rationale": {"badness": "rb", "plausibility": "rp", "generativity": "rg"}}


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
    assert "max_tokens" in r4["validation"]["generation"]["first_errors"][0]

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


def test_cost_guardrail_aborts_before_submitting(repo, client, capsys):
    cfg = load_sim_config(repo)
    cfg["max_usd_per_step"] = 0.01
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
            s = scores(); s["plausibility"] = 11                # out of range -> repair
            return text_result(cid, json.dumps(s))
        idx = int(rid[-2:])
        j = int(cid.split("-j")[1]) if "-j" in cid else 0
        return text_result(cid, json.dumps(scores(p=plaus_by_run.get(rid, 7), b=4 + idx + j * 0.5)))
    return responder


def test_judge_then_select_end_to_end(repo, client, monkeypatch):
    assert G.main(repo, gargs()) == 0
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
