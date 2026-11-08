"""Render prompts/generate.md and prompts/judge.md.

Each template has a preamble (notes for humans, not sent), a `---` line, then a
`## System` section and a `## User` section. Placeholders are `{{name}}`;
rendering fails loudly on a missing value or a leftover placeholder.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
NO_PARENT_PROSE = ("(None. The step-0 baseline is researched fact and has no prose rendering; "
                   "the JSON above is the whole of it.)")


class RenderError(ValueError):
    pass


def split_template(text: str) -> tuple[str, str]:
    """Return (system_template, user_template) from a prompt file."""
    lines = text.splitlines(keepends=True)
    try:
        sep = next(i for i, l in enumerate(lines) if l.strip() == "---")
    except StopIteration:
        raise RenderError("template has no '---' separator after its preamble")
    body = "".join(lines[sep + 1:])
    m = re.search(r"^## System[ \t]*\n(.*?)^## User[ \t]*\n(.*)\Z", body, re.S | re.M)
    if not m:
        raise RenderError("template body must contain '## System' then '## User'")
    return m.group(1).strip() + "\n", m.group(2).strip() + "\n"


def fill(template: str, values: dict) -> str:
    missing = sorted({k for k in PLACEHOLDER.findall(template) if k not in values})
    if missing:
        raise RenderError(f"no value for placeholder(s): {', '.join(missing)}")
    out = PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), template)
    if "{{" in out:
        raise RenderError("a value introduced an unrendered '{{' sequence")
    return out


def load_template(paths, name: str) -> tuple[str, str]:
    return split_template((paths.prompts / f"{name}.md").read_text(encoding="utf-8"))


def pretty(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------- drivers table

NONE_LABEL = {"market_shock": "market shock", "state_action": "state action",
              "next_gen_launch": "next-generation launch", "safety_signal": "safety signal"}


def _cell(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def describe_driver(name: str, value, dcfg: dict, parent_world: dict, parent_year: int,
                    target_year: int) -> tuple[str, str]:
    """(value cell, meaning cell) for the generation prompt's drivers table."""
    spec = dcfg[name]
    if name == "adoption_delta_pp":
        start = parent_world["population"]["us_adults_on_drug_pct"]
        return (f"{value:+.1f} pp",
                f"Share of US adults currently on an incretin drug moves from {start:g}% "
                f"({parent_year}) to about {start + value:.1f}% by the end of {target_year}")
    if spec["type"] == "multi":
        if not value:
            return "none", "No new on-label or quasi-official indication arrives this step"
        return ", ".join(value), "; ".join(spec["options"][v]["desc"] for v in value)
    desc = spec["options"][value].get("desc")
    if desc is None:
        desc = f"No {NONE_LABEL.get(name, name.replace('_', ' '))} this step"
    return value, desc


def drivers_table(drivers: dict, dcfg: dict, parent_world: dict, parent_year: int,
                  target_year: int) -> str:
    rows = []
    for name, value in drivers.items():
        v, meaning = describe_driver(name, value, dcfg, parent_world, parent_year, target_year)
        rows.append(f"| `{name}` | {_cell(v)} | {_cell(meaning)} |")
    return "\n".join(rows)


# ---------------------------------------------------------------- prompts

def generation_prompt(paths, *, parent_world: dict, parent_prose: dict | None, parent_year: int,
                      target_year: int, drivers: dict, dcfg: dict) -> tuple[str, str]:
    system_t, user_t = load_template(paths, "generate")
    values = {
        "parent_year": parent_year,
        "target_year": target_year,
        "parent_world_json": pretty(parent_world),
        "parent_prose_world_in_600_words": (parent_prose or {}).get("world_in_600_words") or NO_PARENT_PROSE,
        "drivers_table": drivers_table(drivers, dcfg, parent_world, parent_year, target_year),
        **population_bounds(parent_world, drivers),
    }
    return fill(system_t, values), fill(user_t, values)


def _pct(x: float) -> str:
    return f"{round(x, 1):g}"


def population_bounds(parent_world: dict, drivers: dict) -> dict:
    """The numbers behind generate.md rule 3: current use = parent + adoption_delta_pp ±2;
    ever-use rises by at most adoption_delta_pp + 6 and never falls (so the rise is capped
    at no less than 0 when adoption_delta_pp < -6)."""
    pop = parent_world["population"]
    on, ever, delta = pop["us_adults_on_drug_pct"], pop["us_adults_ever_used_pct"], drivers["adoption_delta_pp"]
    rise = max(delta + 6, 0)
    return {
        "parent_on_drug_pct": _pct(on),
        "adoption_delta_pp": _pct(delta),
        "current_use_low": _pct(min(100, max(0, on + delta - 2))),
        "current_use_high": _pct(min(100, max(0, on + delta + 2))),
        "parent_ever_used_pct": _pct(ever),
        "ever_rise_max": _pct(rise),
        "ever_use_max": _pct(min(100, ever + rise)),
    }


def judge_prompt(paths, *, parent_world: dict, parent_year: int, target_year: int, drivers: dict,
                 candidate_world: dict, candidate_prose: dict) -> tuple[str, str]:
    """Only what METHOD §6 allows the judge to see: parent world, drivers, the candidate."""
    system_t, user_t = load_template(paths, "judge")
    values = {
        "parent_year": parent_year,
        "target_year": target_year,
        "parent_world_json": pretty(parent_world),
        "drivers_json": pretty(drivers),
        "candidate_world_json": pretty(candidate_world),
        "candidate_headline": candidate_prose["headline"],
        "candidate_world_in_600_words": candidate_prose["world_in_600_words"],
        "candidate_a_day_in_the_life": candidate_prose["a_day_in_the_life"],
    }
    return fill(system_t, values), fill(user_t, values)


def as_markdown(custom_id: str, system: str, user: str, params_note: str = "") -> str:
    """Human-readable copy of a rendered request, for reading dry-run output."""
    return (f"<!-- rendered request {custom_id}{(' · ' + params_note) if params_note else ''} -->\n\n"
            f"# SYSTEM\n\n{system}\n# USER\n\n{user}")
