"""Selection rule (METHOD §7) on hand-made fake runs."""
import argparse
import copy

import pytest

from glpsim import schemas
from glpsim import select as S
from glpsim.common import dump_json, load_json, load_sim_config
from glpsim.validate import validate_tree

from conftest import ROOT

CFG = load_json(ROOT / "config" / "sim.json")
DIMS = S.DIMS

COMBOS = [  # distinct (price_path, cultural_response, personality_layer) per default
    ("managed_decline", "normalisation", "niche_side_effect"),
    ("stalled", "class_stratification", "mainstream_complaint"),
    ("generic_collapse", "backlash_body_politics", "marketed_feature"),
    ("shock_up", "natural_movement", "employer_encouraged"),
    ("managed_decline", "aesthetic_inversion", "unrecognised"),
    ("stalled", "normalisation", "marketed_feature"),
    ("generic_collapse", "class_stratification", "niche_side_effect"),
    ("shock_up", "backlash_body_politics", "mainstream_complaint"),
]


def fake_run(i, *, bad=5.0, plaus=7, gen=5, parent="L0", step=1, combo=None, status="ok",
             dims=None, severity=None, scored=True):
    """One fake run. `bad` sets all six dimensions; `dims` overrides individual ones."""
    pp, cr, pl = combo or COMBOS[i % len(COMBOS)]
    run = {
        "run_id": f"s{step}-{parent}-r{i:02d}", "step": step, "year": 2026 + 2 * step,
        "parent_lineage": parent, "seed": 7, "status": status, "generator_model": "gen",
        "created_at": "2026-11-08T00:00:00Z",
        "drivers": {"adoption_delta_pp": 1.0, "price_path": pp, "coverage_shift": "status_quo",
                    "new_indications": [], "safety_signal": "none", "next_gen_launch": "none",
                    "market_shock": "none", "cultural_response": cr, "state_action": "none",
                    "personality_layer": pl},
        "world": {s: {"severity": severity if severity is not None else 5}
                  for s in ("economy", "body_and_culture", "interior_life", "state")},
        "prose": {"headline": f"headline {i}", "world_in_600_words": "", "a_day_in_the_life": ""},
    }
    if scored:
        b = {d: bad for d in DIMS}
        b.update(dims or {})
        b["overall"] = bad
        run["scores"] = {"judge_model": "judge", "badness": b, "plausibility": plaus,
                         "generativity": gen,
                         "rationale": {"badness": "", "plausibility": "", "generativity": ""}}
    return run


def ids(sel):
    return [s.candidate.run_id for s in sel.survivors]


# ---------------------------------------------------------------- floor

def test_no_floor_drop_when_enough_runs_clear_it():
    runs = [fake_run(i, bad=5 + i * 0.1, plaus=6 + (i % 3)) for i in range(6)]
    sel = S.select_step(runs, CFG, 1)
    assert sel.floor_used == 6 and sel.log == []
    assert len(sel.survivors) == 3


def test_floor_drops_by_one_when_fewer_than_three_clear_it():
    runs = [fake_run(0, bad=9, plaus=5),        # most bad, but below 6
            fake_run(1, bad=6, plaus=7),
            fake_run(2, bad=5, plaus=6),
            fake_run(3, bad=8, plaus=4)]         # still below the lowered floor
    sel = S.select_step(runs, CFG, 1)
    assert sel.floor_used == 5
    assert sel.log == ["only 2 run(s) at plausibility >= 6; lowering floor to 5"]
    assert ids(sel) == ["s1-L0-r00", "s1-L0-r01", "s1-L0-r02"]
    assert [c.run_id for c in sel.below_floor] == ["s1-L0-r03"]


def test_floor_steps_down_twice_and_never_below_four():
    runs = [fake_run(0, bad=9, plaus=4), fake_run(1, bad=9.5, plaus=3),
            fake_run(2, bad=9.9, plaus=2), fake_run(3, bad=3, plaus=8)]
    sel = S.select_step(runs, CFG, 1)
    assert sel.floor_used == 4
    assert sel.log[:2] == ["only 1 run(s) at plausibility >= 6; lowering floor to 5",
                           "only 1 run(s) at plausibility >= 5; lowering floor to 4"]
    assert ids(sel) == ["s1-L0-r00", "s1-L0-r03"]      # the plausibility-3 and -2 runs never get in
    assert sel.log[-1].startswith("WARNING: only 2 survivor(s)")
    assert all(sel.per_run[r]["floor_used"] == 4 for r in sel.per_run)


def test_nothing_reaches_minimum_floor_raises():
    with pytest.raises(S.SelectionError):
        S.select_step([fake_run(0, plaus=3), fake_run(1, plaus=2)], CFG, 1)


# ---------------------------------------------------------------- exclusion

def test_non_ok_and_unscored_runs_are_excluded_even_if_worst():
    runs = [fake_run(0, bad=10, status="invalid", scored=False),
            fake_run(1, bad=10, status="error", scored=False),
            fake_run(2, bad=10, status="pending", scored=False),
            fake_run(3, bad=10, scored=False),
            fake_run(4, bad=10, status="invalid"),            # has scores but invalid
            fake_run(5, bad=4), fake_run(6, bad=3), fake_run(7, bad=2)]
    sel = S.select_step(runs, CFG, 1)
    assert ids(sel) == ["s1-L0-r05", "s1-L0-r06", "s1-L0-r07"]
    assert sel.excluded == {"s1-L0-r00": "status=invalid", "s1-L0-r01": "status=error",
                            "s1-L0-r02": "status=pending", "s1-L0-r03": "unscored",
                            "s1-L0-r04": "status=invalid"}
    assert sel.per_run["s1-L0-r00"] == {"axis": "health", "survived": False,
                                        "new_lineage": None, "floor_used": 6}


# ---------------------------------------------------------------- weighting and ranking

def test_axis_weights_double_the_step_dimensions():
    # Same unweighted mean (5.5). Step 1 doubles flourishing + public_health.
    a = fake_run(0, bad=5, dims={"flourishing": 8, "public_health": 8, "cohesion": 2, "epistemic": 2})
    b = fake_run(1, bad=5, dims={"flourishing": 2, "public_health": 2, "cohesion": 8, "epistemic": 8})
    assert S.axis_badness(a, CFG["axes"]["1"], 2) == pytest.approx((2*8 + 5 + 5 + 2*8 + 2 + 2) / 8)
    assert S.axis_badness(a, CFG["axes"]["1"], 2) > S.axis_badness(b, CFG["axes"]["1"], 2)
    # Step 4 doubles autonomy + epistemic and adds state severity ×2
    sev = S.axis_badness(b, CFG["axes"]["4"], 2)
    assert sev == pytest.approx((2 + 2*5 + 5 + 2 + 8 + 2*8 + 2*5) / 10)


def test_section_severity_counts_on_axes_that_name_one():
    a = fake_run(0, bad=5, step=2, parent="L1", severity=9)
    b = fake_run(1, bad=5, step=2, parent="L2", severity=2)
    assert S.axis_badness(a, CFG["axes"]["1"], 2) == S.axis_badness(b, CFG["axes"]["1"], 2)  # step 1: none
    assert S.axis_badness(a, CFG["axes"]["2"], 2) == pytest.approx((5 * 7 + 2 * 9) / 9)
    sel = S.select_step([b, a, fake_run(2, bad=5, step=2, parent="L3", severity=5)], CFG, 2)
    assert ids(sel)[0] == "s2-L1-r00"


def test_tie_breaks_plausibility_then_generativity_then_run_id():
    runs = [fake_run(0, bad=6, plaus=7, gen=9),
            fake_run(1, bad=6, plaus=8, gen=1),   # wins on plausibility
            fake_run(2, bad=6, plaus=7, gen=9),   # ties r00 fully -> run_id order
            fake_run(3, bad=6, plaus=7, gen=3)]
    sel = S.select_step(runs, CFG, 1)
    assert [c.run_id for c in sel.ranking] == ["s1-L0-r01", "s1-L0-r00", "s1-L0-r02", "s1-L0-r03"]
    assert sel.runner_up.run_id == "s1-L0-r03" and sel.runner_up_reason == "ranked 4"


# ---------------------------------------------------------------- diversity guard

def test_parent_diversity_top_three_from_one_parent_is_broken():
    runs = [fake_run(0, bad=9, parent="L1", step=2), fake_run(1, bad=8.5, parent="L1", step=2),
            fake_run(2, bad=8, parent="L1", step=2),      # would make all three L1
            fake_run(3, bad=4, parent="L2", step=2), fake_run(4, bad=3, parent="L3", step=2)]
    sel = S.select_step(runs, CFG, 2)
    assert ids(sel) == ["s2-L1-r00", "s2-L1-r01", "s2-L2-r03"]
    assert sel.skipped == [("s2-L1-r02", "parent L1 already has 2 survivors")]
    assert sel.runner_up.run_id == "s2-L1-r02"
    assert sel.runner_up_reason.startswith("skipped by diversity guard: parent L1")


def test_parent_rule_waived_when_only_one_lineage_has_eligible_runs():
    # step 1: everything descends from L0
    sel = S.select_step([fake_run(i, bad=9 - i) for i in range(5)], CFG, 1)
    assert ids(sel) == ["s1-L0-r00", "s1-L0-r01", "s1-L0-r02"] and sel.skipped == []
    # step 2: L2's runs exist but all fall below the floor -> only L1 is eligible
    runs = [fake_run(i, bad=9 - i, parent="L1", step=2) for i in range(3)]
    runs.append(fake_run(3, bad=10, parent="L2", step=2, plaus=3))
    sel = S.select_step(runs, CFG, 2)
    assert ids(sel) == ["s2-L1-r00", "s2-L1-r01", "s2-L1-r02"]


def test_distinct_drivers_identical_combo_is_skipped():
    same = ("managed_decline", "normalisation", "niche_side_effect")
    runs = [fake_run(0, bad=9, combo=same), fake_run(1, bad=8, combo=same),
            fake_run(2, bad=7), fake_run(3, bad=6)]
    runs[2]["drivers"]["price_path"] = "stalled"          # differs on one key -> distinct
    runs[2]["drivers"]["cultural_response"] = "normalisation"
    runs[2]["drivers"]["personality_layer"] = "niche_side_effect"
    sel = S.select_step(runs, CFG, 1)
    assert ids(sel) == ["s1-L0-r00", "s1-L0-r02", "s1-L0-r03"]
    assert sel.skipped == [("s1-L0-r01",
                            "same drivers managed_decline/normalisation/niche_side_effect as s1-L0-r00")]


def test_other_drivers_do_not_count_for_distinctness():
    same = ("stalled", "normalisation", "marketed_feature")
    a, b = fake_run(0, bad=9, combo=same), fake_run(1, bad=8, combo=same)
    b["drivers"]["safety_signal"] = "anhedonia_labelled"   # not in distinct_on
    sel = S.select_step([a, b, fake_run(2, bad=1)], CFG, 1)
    assert "s1-L0-r01" not in ids(sel)


def test_both_guard_rules_together():
    same = ("stalled", "class_stratification", "employer_encouraged")
    runs = [fake_run(0, bad=9, parent="L1", step=2, combo=same),
            fake_run(1, bad=8.8, parent="L2", step=2, combo=same),   # combo clash with r00
            fake_run(2, bad=8.6, parent="L1", step=2),
            fake_run(3, bad=8.4, parent="L1", step=2),               # third from L1
            fake_run(4, bad=8.2, parent="L3", step=2)]
    sel = S.select_step(runs, CFG, 2)
    assert ids(sel) == ["s2-L1-r00", "s2-L1-r02", "s2-L3-r04"]
    assert [r for r, _ in sel.skipped] == ["s2-L2-r01", "s2-L1-r03"]


def test_guard_shortfall_lowers_floor_rather_than_relaxing_rules():
    same = ("stalled", "normalisation", "marketed_feature")
    runs = [fake_run(i, bad=9 - i, combo=same) for i in range(4)]     # one usable combo at floor 6
    runs += [fake_run(10, bad=2, plaus=5), fake_run(11, bad=1, plaus=5)]
    sel = S.select_step(runs, CFG, 1)
    assert sel.floor_used == 5
    assert sel.log == ["diversity guard filled only 1 of 3 at floor 6; lowering floor to 5"]
    assert ids(sel) == ["s1-L0-r00", "s1-L0-r10", "s1-L0-r11"]


# ---------------------------------------------------------------- lineage ids and output

def test_lineage_ids_in_rank_order_with_parents_and_ancestry():
    runs = [fake_run(0, bad=4, parent="L2", step=2), fake_run(1, bad=9, parent="L1", step=2),
            fake_run(2, bad=6, parent="L3", step=2)]
    sel = S.select_step(runs, CFG, 2)
    assert [(s.lineage, s.candidate.run_id) for s in sel.survivors] == [
        ("L1", "s2-L1-r01"), ("L2", "s2-L3-r02"), ("L3", "s2-L2-r00")]
    doc = S.world_step_doc(sel, 2030, {"L1": ["s1-L0-r07"], "L2": ["s1-L0-r03"], "L3": ["s1-L0-r11"]}, "t")
    assert doc["lineages"]["L2"]["parent_lineage"] == "L3"
    assert doc["lineages"]["L2"]["ancestry"] == ["s1-L0-r11", "s2-L3-r02"]
    assert sel.per_run["s2-L3-r02"]["new_lineage"] == "L2"


def test_upsert_section_appends_then_replaces():
    t = S.upsert_section(None, 1, "<!-- step:1:begin -->\nA\n<!-- step:1:end -->\n")
    t = S.upsert_section(t, 2, "<!-- step:2:begin -->\nB\n<!-- step:2:end -->\n")
    t2 = S.upsert_section(t, 1, "<!-- step:1:begin -->\nA2\n<!-- step:1:end -->\n")
    assert t.startswith(S.LINEAGE_HEADER)
    assert t2.count("step:1:begin") == 1 and "A2" in t2 and "\nA\n" not in t2
    assert t2.index("A2") < t2.index("\nB\n")


def test_lineage_section_counts_every_parent_not_just_eligible():
    runs = [fake_run(i, bad=9 - i, parent="L1", step=2) for i in range(3)]
    runs += [fake_run(3, bad=2, parent="L2", step=2, plaus=5),
             fake_run(4, bad=2, parent="L3", step=2, status="invalid", scored=False)]
    sel = S.select_step(runs, CFG, 2)
    md = S.lineage_section(sel, CFG, 2030, runs, "t")
    assert "from 5 run(s) of parent lineage(s) L1, L2, L3" in md
    assert "Excluded before ranking: 1 status=invalid; below floor: 1; eligible and ranked: 3" in md


# ---------------------------------------------------------------- end to end on disk

def _write_judged_step1(repo, fake_world):
    for i in range(6):
        r = fake_run(i, bad=4 + i * 0.5, plaus=7)
        r["world"] = fake_world(2028)
        dump_json(repo.run_file(1, "L0", r["run_id"]), r)


def test_select_main_writes_valid_world_file_and_lineage(repo, fake_world, capsys):
    from glpsim.common import ensure_step0
    ensure_step0(repo)
    _write_judged_step1(repo, fake_world)
    args = argparse.Namespace(step=1, force=False)
    assert S.main(repo, args) == 0

    doc = load_json(repo.world_file(1))
    assert list(doc["lineages"]) == ["L1", "L2", "L3"]
    assert doc["lineages"]["L1"]["source_run"] == "s1-L0-r05"
    assert doc["lineages"]["L1"]["ancestry"] == ["s1-L0-r05"]
    run = load_json(repo.run_file(1, "L0", "s1-L0-r05"))
    assert run["selection"]["survived"] is True and run["selection"]["new_lineage"] == "L1"
    md = repo.lineage_md.read_text()
    assert "## Step 1 · 2028 · axis of worst: health" in md
    assert "Runner-up: `s1-L0-r02`" in md

    checked, problems = validate_tree(repo)
    assert problems == [] and "world/step1.json" in checked

    # rerun refuses; --force rewrites rather than duplicating the section
    assert S.main(repo, args) == 1
    assert S.main(repo, argparse.Namespace(step=1, force=True)) == 0
    assert repo.lineage_md.read_text().count("<!-- step:1:begin -->") == 1
