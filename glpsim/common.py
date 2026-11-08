"""Paths, JSON I/O and config loading shared by every command.

Every function that touches the filesystem takes a `Paths` so tests can run
against a temporary copy of the repo.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Paths:
    root: Path = REPO_ROOT

    @property
    def config(self) -> Path: return self.root / "config"
    @property
    def schema(self) -> Path: return self.root / "schema"
    @property
    def prompts(self) -> Path: return self.root / "prompts"
    @property
    def data(self) -> Path: return self.root / "data"
    @property
    def world(self) -> Path: return self.root / "world"
    @property
    def runs(self) -> Path: return self.root / "runs"
    @property
    def dry(self) -> Path: return self.root / "runs" / "_dry"
    @property
    def lineage_md(self) -> Path: return self.root / "lineage.md"
    @property
    def report(self) -> Path: return self.root / "report"
    @property
    def baseline(self) -> Path: return self.data / "step0_baseline.json"

    def step_runs(self, step: int) -> Path:
        return self.runs / f"step{step}"

    def world_file(self, step: int) -> Path:
        return self.world / f"step{step}.json"

    def run_file(self, step: int, parent_lineage: str, run_id: str) -> Path:
        return self.step_runs(step) / parent_lineage / f"{run_id}.json"


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dumps(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def write_text_atomic(path: Path, text: str) -> None:
    """Write via a temp file + rename so an interrupted run never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def dump_json(path: Path, obj) -> None:
    write_text_atomic(path, dumps(obj))


def load_sim_config(paths: Paths) -> dict:
    return load_json(paths.config / "sim.json")


def load_drivers_config(paths: Paths) -> dict:
    return load_json(paths.config / "drivers.json")


def step_year(cfg: dict, step: int) -> int:
    return cfg["baseline_year"] + step * cfg["years_per_step"]


def ensure_step0(paths: Paths) -> bool:
    """Copy the researched baseline to world/step0.json if it is not there yet.

    Returns True if a copy was made. Never overwrites: if world/step0.json
    exists and differs, `validate` reports it rather than silently replacing it.
    """
    dest = paths.world_file(0)
    if dest.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(paths.baseline, dest)
    return True
