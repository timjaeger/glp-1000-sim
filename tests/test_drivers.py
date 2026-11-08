import copy
import random

import pytest

from glpsim import drivers as D
from glpsim.common import load_json

from conftest import ROOT

DCFG = load_json(ROOT / "config" / "drivers.json")
CFG = load_json(ROOT / "config" / "sim.json")
BASE = load_json(ROOT / "data" / "step0_baseline.json")
SEED = CFG["seed"]


def test_same_seed_gives_identical_draws():
    a = D.plan_step(CFG, DCFG, {"L0": BASE}, 1, 50, SEED)
    b = D.plan_step(CFG, DCFG, {"L0": copy.deepcopy(BASE)}, 1, 50, SEED)
    assert a == b


def test_rng_is_seed_plus_step_times_1000_plus_run_index():
    # step 2 run 5 and step 1 run 1005 share an RNG seed under the formula
    assert D.draw_drivers(DCFG, BASE, SEED, 2, 5) == D.draw_drivers(DCFG, BASE, SEED, 1, 1005)
    assert D.rng_for(SEED, 3, 7).random() == random.Random(SEED + 3007).random()


def test_different_seed_step_or_index_gives_different_draws():
    base = [D.draw_drivers(DCFG, BASE, SEED, 1, i)[0] for i in range(20)]
    assert len({repr(d) for d in base}) == 20
    assert base != [D.draw_drivers(DCFG, BASE, SEED + 1, 1, i)[0] for i in range(20)]
    assert base != [D.draw_drivers(DCFG, BASE, SEED, 2, i)[0] for i in range(20)]


def test_pinned_draw_for_the_configured_seed():
    """Golden values: if this changes, already-run steps are no longer reproducible."""
    d, fired = D.draw_drivers(DCFG, BASE, 20261107, 1, 0)
    assert d == PINNED_S1_R00
    assert fired == []


PINNED_S1_R00 = {
    "adoption_delta_pp": 10.3, "price_path": "generic_collapse", "coverage_shift": "public_expansion",
    "new_indications": ["alcohol_use_disorder", "longevity_wellness"],
    "safety_signal": "vision_class_label", "next_gen_launch": "monthly_or_implant",
    "market_shock": "generic_flood_counterfeits", "cultural_response": "class_stratification",
    "state_action": "subsidy", "personality_layer": "marketed_feature",
}


def test_draws_are_valid_values():
    for i in range(300):
        d, _ = D.draw_drivers(DCFG, BASE, SEED, 1, i)
        assert list(d) == D.driver_names(DCFG)
        lo, hi = DCFG["adoption_delta_pp"]["clip"]
        assert lo <= d["adoption_delta_pp"] <= hi
        assert round(d["adoption_delta_pp"], 1) == d["adoption_delta_pp"]
        for name in D.driver_names(DCFG):
            spec = DCFG[name]
            if spec["type"] in ("categorical", "ordinal"):
                assert d[name] in spec["options"]
        ni = d["new_indications"]
        assert len(ni) <= 2 and len(set(ni)) == len(ni)
        assert all(x in DCFG["new_indications"]["options"] for x in ni)


def test_new_indication_counts_follow_the_draws_distribution():
    counts = {0: 0, 1: 0, 2: 0}
    for i in range(3000):
        counts[len(D.draw_drivers(DCFG, BASE, SEED, 1, i)[0]["new_indications"])] += 1
    # config weights 2:5:3
    assert 0.15 < counts[0] / 3000 < 0.25
    assert 0.45 < counts[1] / 3000 < 0.55
    assert 0.25 < counts[2] / 3000 < 0.35


# ---------------------------------------------------------------- parent modifiers

def test_no_modifier_fires_on_the_baseline():
    for name in D.driver_names(DCFG):
        _, fired = D.effective_params(name, DCFG[name], BASE)
        assert fired == []


def test_generic_us_reweights_price_path():
    w = copy.deepcopy(BASE)
    w["access"]["generic_us"] = True
    params, fired = D.effective_params("price_path", DCFG["price_path"], w)
    assert params["weights"] == {"generic_collapse": 0.5, "managed_decline": 4, "stalled": 3, "shock_up": 1}
    assert len(fired) == 1
    _, recorded = D.draw_drivers(DCFG, w, SEED, 2, 0)
    assert recorded == [{"driver": "price_path", "if": {"path": "access.generic_us", "eq": True},
                         "set": {"generic_collapse": 0.5, "stalled": 3}}]


def test_adoption_modifiers_apply_in_order_later_overrides():
    w = copy.deepcopy(BASE)
    w["population"]["us_adults_on_drug_pct"] = 35
    assert D.effective_params("adoption_delta_pp", DCFG["adoption_delta_pp"], w)[0]["mean"] == 2.5
    w["population"]["us_adults_on_drug_pct"] = 50
    params, fired = D.effective_params("adoption_delta_pp", DCFG["adoption_delta_pp"], w)
    assert (params["mean"], params["sd"], len(fired)) == (0.5, 3.5, 2)


def test_marketed_personality_parent_never_draws_unrecognised():
    w = copy.deepcopy(BASE)
    w["interior_life"]["personality_layer"] = "marketed_feature"
    seen = {D.draw_drivers(DCFG, w, SEED, 3, i)[0]["personality_layer"] for i in range(500)}
    assert "unrecognised" not in seen and "employer_encouraged" in seen


def test_null_or_missing_path_never_matches():
    assert D.rule_matches({"path": "population.cycled_off_and_on_pct", "gte": 0}, BASE) is False
    assert D.rule_matches({"path": "no.such.path", "eq": None}, BASE) is False
    with pytest.raises(ValueError):
        D.rule_matches({"path": "access.generic_us", "approx": True}, BASE)


def test_modifiers_read_the_parent_not_the_baseline():
    """Two parents in one step get their own modifiers."""
    gen = copy.deepcopy(BASE); gen["access"]["generic_us"] = True
    plan = D.plan_step(CFG, DCFG, {"L1": BASE, "L2": gen, "L3": BASE}, 2, 50, SEED)
    by_parent = {}
    for p in plan:
        by_parent.setdefault(p["parent_lineage"], set()).update(m["driver"] for m in p["driver_modifiers"])
    assert by_parent.get("L1", set()) == set() and by_parent["L2"] == {"price_path"}


# ---------------------------------------------------------------- run plan

def test_plan_splits_17_17_16_with_step_wide_run_indices():
    plan = D.plan_step(CFG, DCFG, {"L2": BASE, "L1": BASE, "L3": BASE}, 2, 50, SEED)
    ids = [p["run_id"] for p in plan]
    assert ids[0] == "s2-L1-r00" and ids[16] == "s2-L1-r16"
    assert ids[17] == "s2-L2-r17" and ids[33] == "s2-L2-r33"
    assert ids[34] == "s2-L3-r34" and ids[-1] == "s2-L3-r49"
    assert [p["run_index"] for p in plan] == list(range(50))


def test_plan_small_n_and_single_parent():
    assert D.split_runs(5, 3, CFG) == [2, 2, 1]
    assert D.split_runs(50, 2, CFG) == [25, 25]
    plan = D.plan_step(CFG, DCFG, {"L0": BASE}, 1, 5, SEED)
    assert [p["run_id"] for p in plan] == [f"s1-L0-r0{i}" for i in range(5)]
    # the first 5 runs of a 50-run plan are the same draws: --n 5 is a true prefix
    assert plan == D.plan_step(CFG, DCFG, {"L0": BASE}, 1, 50, SEED)[:5]
