"""Load the JSON Schemas in schema/ and build validators that resolve their cross-file $refs."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from .common import Paths, load_json

SCHEMA_FILES = {
    "world_state": "world_state.schema.json",
    "run": "run.schema.json",
    "world_step": "world_step.schema.json",
    "batch_state": "batch_state.schema.json",
}


@lru_cache(maxsize=None)
def _load(root: str) -> tuple[dict, Registry]:
    paths = Paths(Path(root))
    schemas = {}
    for name, fname in SCHEMA_FILES.items():
        p = paths.schema / fname
        if p.exists():
            schemas[name] = load_json(p)
    registry = Registry().with_resources(
        (s["$id"], Resource.from_contents(s)) for s in schemas.values()
    )
    return schemas, registry


def schema(paths: Paths, name: str) -> dict:
    return _load(str(paths.root))[0][name]


def validator(paths: Paths, name: str) -> Draft202012Validator:
    schemas, registry = _load(str(paths.root))
    if name not in schemas:
        raise KeyError(f"schema/{SCHEMA_FILES[name]} not found")
    return Draft202012Validator(schemas[name], registry=registry)


def errors(v: Draft202012Validator, instance) -> list[str]:
    """All validation errors as 'json/path: message', sorted for stable output."""
    out = []
    for e in v.iter_errors(instance):
        loc = "/".join(str(p) for p in e.absolute_path) or "(root)"
        out.append(f"{loc}: {e.message}")
    return sorted(out)


def clear_cache() -> None:
    _load.cache_clear()
