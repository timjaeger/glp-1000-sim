"""Prompt rendering, API schema derivation, request building, cost estimate, dry runs."""
import copy
import argparse
import json
import sys

import pytest
from jsonschema import Draft202012Validator

from glpsim import batch, render
from glpsim import generate as G
from glpsim import judge as J
from glpsim.batch import UNSUPPORTED_KEYS
from glpsim.common import Paths, load_json, load_sim_config
from glpsim.drivers import driver_names

from conftest import ROOT

FIXTURE = ROOT / "tests" / "fixtures" / "s1-L0-r00.fixture.json"
DCFG = load_json(ROOT / "config" / "drivers.json")


@pytest.fixture
def fixture_run():
    return load_json(FIXTURE)


# ---------------------------------------------------------------- templates

@pytest.mark.parametrize("name", ["generate", "judge"])
def test_templates_split_into_system_and_user_without_preamble(name):
    system, user = render.load_template(Paths(ROOT), name)
    assert system.startswith("You are ")
    assert "Rendered by" not in system + user and "## User" not in system
    assert user.startswith("### ")


def test_fill_rejects_missing_values():
    with pytest.raises(render.RenderError, match="target_year"):
        render.fill("{{parent_year}} -> {{target_year}}", {"parent_year": 2026})


def test_generation_prompt_renders_every_placeholder(baseline, fixture_run):
    system, user = render.generation_prompt(
        Paths(ROOT), parent_world=baseline, parent_prose=None, parent_year=2026,
        target_year=2028, drivers=fixture_run["drivers"], dcfg=DCFG)
    assert "{{" not in system + user
    assert "### The world as of 2026" in user and "end of 2028" in user
    assert render.NO_PARENT_PROSE in user
    assert json.dumps(baseline, indent=2, ensure_ascii=False) in user
    for name in driver_names(DCFG):
        assert f"| `{name}` |" in user
    assert "| +10.3 pp | Share of US adults currently on an incretin drug moves from 11% (2026) " \
           "to about 21.3% by the end of 2028 |" in user
    assert "| alcohol_use_disorder, longevity_wellness | Approved or guideline-endorsed" in user


def test_generation_prompt_uses_parent_prose_when_present(baseline, fixture_run):
    _, user = render.generation_prompt(
        Paths(ROOT), parent_world=fixture_run["world"], parent_prose={"world_in_600_words": "PARENT PROSE"},
        parent_year=2028, target_year=2030, drivers=fixture_run["drivers"], dcfg=DCFG)
    assert "PARENT PROSE" in user and render.NO_PARENT_PROSE not in user
    assert "from 21% (2028) to about 31.3%" in user


def test_driver_without_desc_and_empty_indications():
    assert render.describe_driver("market_shock", "none", DCFG, {}, 2026, 2028) == \
        ("none", "No market shock this step")
    assert render.describe_driver("new_indications", [], DCFG, {}, 2026, 2028)[0] == "none"


def test_judge_prompt_sees_only_parent_drivers_and_candidate(baseline, fixture_run):
    system, user = render.judge_prompt(
        Paths(ROOT), parent_world=baseline, parent_year=2026, target_year=2028,
        drivers=fixture_run["drivers"], candidate_world=fixture_run["world"],
        candidate_prose=fixture_run["prose"])
    text = system + user
    assert "{{" not in text
    assert json.dumps(fixture_run["drivers"], indent=2) in user
    assert fixture_run["prose"]["headline"] in user
    for leak in ("s1-L0-r00", "parent_lineage", "run_id", "axis_badness", "axis of worst",
                 "weights", "generator_model", fixture_run["generator_model"]):
        assert leak not in text


# ---------------------------------------------------------------- API schemas

def _walk(node, path="#"):
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from _walk(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}/{i}")


@pytest.mark.parametrize("which", ["generation", "judge"])
def test_api_schemas_use_only_the_supported_subset(which):
    s = getattr(batch, f"{which}_api_schema")(Paths(ROOT))
    for path, node in _walk(s):
        if path.endswith("/properties"):      # keys here are field names, not schema keywords
            continue
        assert not (UNSUPPORTED_KEYS & set(node)), path
        assert "$ref" not in node and "$defs" not in node, path
        assert not isinstance(node.get("type"), list), path
        if node.get("type") == "object":
            assert node["additionalProperties"] is False, path
            assert set(node["required"]) == set(node["properties"]), path


def test_generation_api_schema_accepts_a_real_world_and_pins_fictional(fixture_run, baseline):
    s = batch.generation_api_schema(Paths(ROOT))
    v = Draft202012Validator(s)
    assert list(v.iter_errors({"world": fixture_run["world"], "prose": fixture_run["prose"]})) == []
    assert list(v.iter_errors({"world": baseline, "prose": fixture_run["prose"]}))  # fictional=false rejected


def test_judge_api_schema_is_rubric_v2_with_claims_first():
    s = batch.judge_api_schema(Paths(ROOT))
    for k in ("judge_model", "rubric", "plausibility"):          # filled by code, never asked for
        assert k not in s["properties"] and k not in s["required"]
    assert list(s["properties"]) == ["least_plausible_claims", "badness", "plausibility_axes",
                                     "generativity", "rationale"]
    assert list(s["properties"]["plausibility_axes"]["properties"]) == ["driver_fidelity", "mechanism", "magnitude"]
    claim = {"quote": "q", "field": "world/x", "why": "w"}
    ok = {"least_plausible_claims": [claim] * 3,
          "badness": {d: 5 for d in ("flourishing", "autonomy", "inequality", "public_health",
                                     "cohesion", "epistemic", "overall")},
          "plausibility_axes": {"driver_fidelity": 7, "mechanism": 6, "magnitude": 5},
          "generativity": 6,
          "rationale": {"badness": "b", "plausibility": "p", "generativity": "g"}}
    assert list(Draft202012Validator(s).iter_errors(ok)) == []
    local = batch.local_judge_validator(Paths(ROOT))
    assert list(local.iter_errors(ok)) == []
    bad = copy.deepcopy(ok); bad["plausibility_axes"]["magnitude"] = 11     # bounds enforced locally only
    assert list(local.iter_errors(bad))
    bad = copy.deepcopy(ok); bad["least_plausible_claims"] = [claim] * 2    # exactly three, locally
    assert list(Draft202012Validator(s).iter_errors(bad)) == [] and list(local.iter_errors(bad))


def test_schema_shape_errors_are_caught():
    with pytest.raises(batch.SchemaShapeError):
        batch.to_api_schema({"type": "object", "properties": {"a": {"type": "string"}}, "required": []})
    with pytest.raises(batch.SchemaShapeError):
        batch.to_api_schema({"type": "object", "properties": {}, "required": [], "additionalProperties": True})


# ---------------------------------------------------------------- requests and cost

def test_build_request_omits_null_temperature_and_uses_config_values():
    cfg = load_json(ROOT / "config" / "sim.json")
    r = batch.build_request("x", model=cfg["models"]["generator"], call_cfg=cfg["generation"],
                            system="S", user="U", schema={"type": "object"})
    assert "temperature" not in r["params"]
    assert r["params"]["max_tokens"] == cfg["generation"]["max_tokens"]
    assert r["params"]["output_config"]["effort"] == cfg["generation"]["effort"]
    assert r["params"]["messages"] == [{"role": "user", "content": "U"}]
    r = batch.build_request("x", model="m", call_cfg={**cfg["generation"], "temperature": 0.3},
                            system="S", user="U", schema={})
    assert r["params"]["temperature"] == 0.3


def test_generation_requests_carry_the_schema_as_one_non_strict_tool():
    cfg = load_json(ROOT / "config" / "sim.json")
    req = batch.build_request("g", model="claude-opus-5-5", call_cfg=cfg["generation"], system="s",
                              user="u", schema=batch.generation_api_schema(Paths(ROOT)),
                              tool=batch.GENERATION_TOOL)
    p = req["params"]
    assert "format" not in p["output_config"] and p["output_config"]["effort"] == cfg["generation"]["effort"]
    (tool,) = p["tools"]
    assert tool["name"] == "submit_world" and "strict" not in tool and "tool_choice" not in p
    assert tool["input_schema"] == batch.generation_api_schema(Paths(ROOT))
    assert batch.request_schema(req) is tool["input_schema"]
    judge = batch.build_request("j", model="m", call_cfg=cfg["judging"], system="s", user="u", schema={"a": 1})
    assert "tools" not in judge["params"] and batch.request_schema(judge) == {"a": 1}


def test_estimate_and_guardrail():
    cfg = load_json(ROOT / "config" / "sim.json")
    req = batch.build_request("x", model="claude-opus-5-5", call_cfg={"max_tokens": 1000, "effort": "high"},
                              system="a" * 35, user="b" * 35, schema={})
    est = batch.estimate([req] * 10, cfg)
    assert est["input_tokens"] == 10 * 21                    # (35+35+2 chars of "{}")/3.5 -> 21
    assert est["output_tokens_max"] == 10_000
    assert est["usd_max"] == round((210 * 2.0 + 10_000 * 10.0) / 1e6, 2)
    assert not batch.over_cap(est, cfg)
    assert batch.over_cap(est, cfg, spent=cfg["max_usd_per_step"])
    with pytest.raises(KeyError, match="no price"):
        batch.prices(cfg, "some-unpriced-model")


# ---------------------------------------------------------------- dry runs end to end

def _no_anthropic(monkeypatch):
    """Make any attempt to import the SDK fail: dry runs must not need it (or a key)."""
    monkeypatch.setitem(sys.modules, "anthropic", None)


def test_generate_dry_run_writes_batch_and_no_run_files(repo, monkeypatch, capsys):
    _no_anthropic(monkeypatch)
    args = argparse.Namespace(step=1, n=5, seed=None, dry_run=True)
    assert G.main(repo, args) == 0
    lines = (repo.step_runs(1) / "_batch.jsonl").read_text().splitlines()
    reqs = [json.loads(l) for l in lines]
    assert [r["custom_id"] for r in reqs] == [f"s1-L0-r0{i}" for i in range(5)]
    cfg = load_sim_config(repo)
    assert {r["params"]["model"] for r in reqs} == {cfg["models"]["generator"]}
    assert not list(repo.step_runs(1).glob("L*/*.json"))
    assert (repo.dry / "step1" / "generate" / "s1-L0-r00.md").exists()
    out = capsys.readouterr().out
    assert "DRY RUN — nothing submitted" in out and "cost   <=$" in out


def test_judge_dry_run_with_fixture_stays_in_dry_dir(repo, monkeypatch, capsys):
    _no_anthropic(monkeypatch)
    args = argparse.Namespace(step=1, dry_run=True, fixture=str(FIXTURE), rejudge=False)
    assert J.main(repo, args) == 0
    reqs = [json.loads(l) for l in (repo.dry / "step1" / "_judge_batch.jsonl").read_text().splitlines()]
    cfg = load_sim_config(repo)
    assert len(reqs) == cfg["judging"]["judge_samples"] == 3            # one request per judge sample
    assert [r["custom_id"] for r in reqs] == ["s1-L0-r00-j0", "s1-L0-r00-j1", "s1-L0-r00-j2"]
    assert reqs[0]["params"]["model"] == cfg["models"]["judge"]
    body = json.dumps(reqs[0]["params"])
    assert "s1-L0-r00" not in body                 # custom_id is metadata, not prompt
    assert not repo.step_runs(1).exists()


def test_judge_dry_run_without_runs_or_fixture_fails(repo, capsys):
    assert J.main(repo, argparse.Namespace(step=1, dry_run=True, fixture=None, rejudge=False)) == 1


def test_judge_samples_fan_out_custom_ids():
    assert J.judge_custom_ids("s1-L0-r00", 1) == ["s1-L0-r00"]
    assert J.judge_custom_ids("s1-L0-r00", 3) == ["s1-L0-r00-j0", "s1-L0-r00-j1", "s1-L0-r00-j2"]


def test_same_model_for_generator_and_judge_is_refused(repo):
    cfg = load_sim_config(repo)
    cfg["models"]["judge"] = cfg["models"]["generator"]
    (repo.config / "sim.json").write_text(json.dumps(cfg))
    with pytest.raises(SystemExit, match="must differ"):
        G.main(repo, argparse.Namespace(step=1, n=1, seed=None, dry_run=True))


def test_generation_requires_still_true_before_events(fixture_run):
    s = batch.generation_api_schema(Paths(ROOT))
    world = s["properties"]["world"]
    keys = list(world["properties"])
    assert "still_true" in world["required"] and keys.index("still_true") == keys.index("events") - 1
    from glpsim import runner
    good = {"world": copy.deepcopy(fixture_run["world"]), "prose": fixture_run["prose"]}
    assert runner.check_generation(Paths(ROOT), good, 2028) == []
    del good["world"]["still_true"]
    assert any("still_true" in e for e in runner.check_generation(Paths(ROOT), good, 2028))
    good["world"]["still_true"] = ["only one"]
    assert any("still_true" in e for e in runner.check_generation(Paths(ROOT), good, 2028))


def test_population_bounds_render_into_the_prompt(baseline):
    from glpsim import render
    b = render.population_bounds(baseline, {"adoption_delta_pp": 7.1})   # parent 11% on, 15% ever
    assert b == {"parent_on_drug_pct": "11", "adoption_delta_pp": "7.1", "current_use_low": "16.1",
                 "current_use_high": "20.1", "parent_ever_used_pct": "15", "ever_rise_max": "13.1",
                 "ever_use_max": "28.1"}
    neg = render.population_bounds(baseline, {"adoption_delta_pp": -8})
    assert (neg["current_use_low"], neg["current_use_high"]) == ("1", "5")
    assert neg["ever_rise_max"] == "0" and neg["ever_use_max"] == "15"   # ever-use never falls


def test_generation_prompt_carries_the_new_rules(baseline):
    from glpsim import render
    from glpsim.common import load_drivers_config
    drivers = {"adoption_delta_pp": 7.1, "price_path": "stalled", "coverage_shift": "employer_retreat",
               "new_indications": [], "safety_signal": "none", "next_gen_launch": "triple_agonist_30pct",
               "market_shock": "none", "cultural_response": "aesthetic_inversion",
               "state_action": "restriction", "personality_layer": "marketed_feature"}
    _, user = render.generation_prompt(Paths(ROOT), parent_world=baseline, parent_prose=None,
                                       parent_year=2026, target_year=2028, drivers=drivers,
                                       dcfg=load_drivers_config(Paths(ROOT)))
    assert "{{" not in user
    assert "between **16.1** and\n     **20.1**" in user and "**28.1**" in user
    for phrase in ("no earlier than 12 months after its stated filing", "before 2031",
                   "one named\n   demographic, city or industry", "fill `still_true` with\n    five",
                   "must all be possible under the `access`, `drugs`\n    and `state` you wrote"):
        assert phrase in user, phrase
