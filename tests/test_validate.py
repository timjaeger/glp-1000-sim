from glpsim import schemas
from glpsim.common import dump_json, ensure_step0, load_json
from glpsim.validate import validate_tree

PROSE = {"headline": "h", "world_in_600_words": "w", "a_day_in_the_life": "d"}
DRIVERS = {
    "adoption_delta_pp": 4.2, "price_path": "managed_decline", "coverage_shift": "status_quo",
    "new_indications": ["nicotine"], "safety_signal": "none", "next_gen_launch": "none",
    "market_shock": "none", "cultural_response": "normalisation", "state_action": "none",
    "personality_layer": "niche_side_effect",
}


def make_run(world, run_id="s1-L0-r03", step=1, parent="L0", status="ok"):
    r = {
        "run_id": run_id, "step": step, "year": 2026 + 2 * step, "parent_lineage": parent,
        "seed": 1, "drivers": dict(DRIVERS), "status": status,
        "generator_model": "gen-model", "created_at": "2026-11-08T00:00:00Z",
    }
    if world is not None:
        r["world"] = world
        r["prose"] = dict(PROSE)
    return r


def problems_for(repo, name):
    _, problems = validate_tree(repo)
    return [m for f, m in problems if f.endswith(name)]


def test_baseline_passes_world_state_schema(repo, baseline):
    assert schemas.errors(schemas.validator(repo, "world_state"), baseline) == []


def test_step0_copied_and_valid(repo, baseline):
    assert ensure_step0(repo) is True
    assert ensure_step0(repo) is False  # never overwrites
    assert load_json(repo.world_file(0)) == baseline
    checked, problems = validate_tree(repo)
    assert checked == ["world/step0.json"] and problems == []


def test_step0_edited_fact_is_flagged(repo, baseline):
    ensure_step0(repo)
    w = load_json(repo.world_file(0))
    w["population"]["us_adults_on_drug_pct"] = 12
    dump_json(repo.world_file(0), w)
    assert any("differs from data/step0_baseline.json" in m for m in problems_for(repo, "step0.json"))


def test_step0_must_not_be_fictional(repo, baseline):
    ensure_step0(repo)
    w = load_json(repo.world_file(0)); w["fictional"] = True
    dump_json(repo.world_file(0), w)
    assert any(m.startswith("fictional") for m in problems_for(repo, "step0.json"))


def test_valid_run_passes(repo, fake_world):
    run = make_run(fake_world(2028))
    dump_json(repo.run_file(1, "L0", run["run_id"]), run)
    assert problems_for(repo, "s1-L0-r03.json") == []


def test_run_world_is_checked_through_ref(repo, fake_world):
    w = fake_world(2028)
    w["access"]["gray_market"] = "everywhere"          # not in enum
    del w["open_tensions"]                             # required
    run = make_run(w)
    dump_json(repo.run_file(1, "L0", run["run_id"]), run)
    msgs = problems_for(repo, "s1-L0-r03.json")
    assert any("world/access/gray_market" in m for m in msgs)
    assert any("open_tensions" in m for m in msgs)


def test_simulated_world_must_be_fictional(repo, fake_world):
    run = make_run(fake_world(2028, fictional=False))
    dump_json(repo.run_file(1, "L0", run["run_id"]), run)
    assert any("fictional" in m for m in problems_for(repo, "s1-L0-r03.json"))


def test_run_location_and_ids_must_agree(repo, fake_world):
    run = make_run(fake_world(2028))
    dump_json(repo.runs / "step1" / "L2" / "s1-L0-r03.json", run)   # wrong lineage dir
    assert any("file should be at" in m for m in problems_for(repo, "s1-L0-r03.json"))


def test_ok_run_requires_world(repo):
    run = make_run(None)
    dump_json(repo.run_file(1, "L0", run["run_id"]), run)
    assert any("'world' is missing" in m for m in problems_for(repo, "s1-L0-r03.json"))


def test_invalid_status_run_without_world_is_fine(repo):
    run = make_run(None, status="invalid")
    dump_json(repo.run_file(1, "L0", run["run_id"]), run)
    assert problems_for(repo, "s1-L0-r03.json") == []


def test_unknown_and_malformed_files_are_reported(repo):
    (repo.runs / "step1").mkdir(parents=True)
    (repo.runs / "step1" / "notes.json").write_text("{}")
    (repo.world).mkdir(parents=True)
    (repo.world / "step1.json").write_text("{not json")
    _, problems = validate_tree(repo)
    msgs = dict(problems)
    assert "unrecognised" in msgs["runs/step1/notes.json"]
    assert "not valid JSON" in msgs["world/step1.json"]


def test_dry_run_scratch_is_ignored(repo):
    (repo.dry / "step1").mkdir(parents=True)
    (repo.dry / "step1" / "whatever.json").write_text("{}")
    checked, problems = validate_tree(repo)
    assert checked == [] and problems == []
