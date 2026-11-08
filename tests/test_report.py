"""`sim.py report`: reproduces every selection, re-renders lineage.md, writes report/."""
import argparse

from glpsim import report as R
from glpsim import select as S
from glpsim.common import dump_json, ensure_step0, load_json

from test_select import fake_run


def _select(repo, step):
    assert S.main(repo, argparse.Namespace(step=step, force=False)) == 0


def two_steps(repo, fake_world):
    """Fake judged step 1 (from L0) and step 2 (from L1-L3), both selected."""
    ensure_step0(repo)
    for i in range(6):
        r = fake_run(i, bad=4 + i * 0.5, plaus=7)
        r["world"] = fake_world(2028)
        dump_json(repo.run_file(1, "L0", r["run_id"]), r)
    _select(repo, 1)
    for i, parent in enumerate(["L1", "L1", "L2", "L2", "L3", "L3"]):
        r = fake_run(i, bad=4 + i * 0.4, plaus=7, step=2, parent=parent)
        r["world"] = fake_world(2030)
        dump_json(repo.run_file(2, parent, r["run_id"]), r)
    _select(repo, 2)


def test_report_reproduces_lineage_and_writes_dossiers(repo, fake_world, capsys):
    two_steps(repo, fake_world)
    lineage_by_select = repo.lineage_md.read_text()
    assert R.main(repo, argparse.Namespace()) == 0
    assert repo.lineage_md.read_text() == lineage_by_select           # same sections, same timestamps
    assert sorted(p.name for p in repo.report.iterdir()) == ["L1.md", "L2.md", "L3.md", "README.md"]
    final = load_json(repo.world_file(2))
    l1 = (repo.report / "L1.md").read_text()
    anc = final["lineages"]["L1"]["ancestry"]
    assert len(anc) == 2 and all(f"`{rid}`" in l1 for rid in anc)
    assert "## Ancestry" in l1 and "### Step 1 · 2028" in l1 and "### Step 2 · 2030" in l1
    assert "Runner-up `" in l1 and "## Final world state (JSON)" in l1
    assert "new_indications = none" in l1
    idx = (repo.report / "README.md").read_text()
    assert "sampled 12 candidate futures" in idx and "[L1](L1.md)" in idx
    assert "selection reproduced for every step" in capsys.readouterr().out


def test_report_is_deterministic(repo, fake_world):
    two_steps(repo, fake_world)
    first = R.build(repo)
    assert R.build(repo) == first


def test_report_refuses_when_a_recorded_selection_does_not_reproduce(repo, fake_world, capsys):
    two_steps(repo, fake_world)
    before = repo.lineage_md.read_text()
    doc = load_json(repo.world_file(2))
    doc["lineages"]["L1"]["source_run"], doc["lineages"]["L2"]["source_run"] = (
        doc["lineages"]["L2"]["source_run"], doc["lineages"]["L1"]["source_run"])
    dump_json(repo.world_file(2), doc)
    assert R.main(repo, argparse.Namespace()) == 1
    assert "step 2: the selection rule" in capsys.readouterr().out
    assert not repo.report.exists() and repo.lineage_md.read_text() == before


def test_report_refuses_a_gap_in_steps(repo, fake_world, capsys):
    two_steps(repo, fake_world)
    repo.world_file(1).unlink()
    assert R.main(repo, argparse.Namespace()) == 1
    assert "without gaps" in capsys.readouterr().out


def test_report_removes_stale_dossiers(repo, fake_world):
    two_steps(repo, fake_world)
    repo.report.mkdir()
    (repo.report / "L4.md").write_text("old")
    assert R.main(repo, argparse.Namespace()) == 0
    assert not (repo.report / "L4.md").exists()
