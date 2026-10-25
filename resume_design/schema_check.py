"""Minimal JSON-Schema (draft-07 subset) validator: type, enum, required, properties,
items, oneOf, $ref (local), minimum, maximum. Enough for schemas/resume.schema.json."""
from __future__ import annotations

import json

from . import ROOT

_TYPES = {
    "string": lambda v: isinstance(v, str),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
}


def load_schema() -> dict:
    return json.loads((ROOT / "schemas" / "resume.schema.json").read_text(encoding="utf-8"))


def _resolve(root: dict, ref: str) -> dict:
    node = root
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def _check(root, schema, value, path, errors):
    if "$ref" in schema:
        schema = _resolve(root, schema["$ref"])
    t = schema.get("type")
    if t and not _TYPES[t](value):
        errors.append((path, f"expected {t}, got {type(value).__name__}"))
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append((path, f"must be one of {schema['enum']}"))
    if "minimum" in schema and isinstance(value, (int, float)) and value < schema["minimum"]:
        errors.append((path, f"must be >= {schema['minimum']}"))
    if "maximum" in schema and isinstance(value, (int, float)) and value > schema["maximum"]:
        errors.append((path, f"must be <= {schema['maximum']}"))
    if "oneOf" in schema:
        trials = []
        for sub in schema["oneOf"]:
            errs: list = []
            _check(root, sub, value, path, errs)
            trials.append(errs)
        if not any(not e for e in trials):
            # report the most specific failure (fewest errors)
            errors.extend(min(trials, key=len) or [(path, "no alternative matched")])
        return
    if isinstance(value, dict):
        for r in schema.get("required", []):
            if r not in value:
                errors.append((f"{path}.{r}" if path else r, "required field missing"))
        for k, sub in schema.get("properties", {}).items():
            if k in value:
                _check(root, sub, value[k], f"{path}.{k}" if path else k, errors)
    if isinstance(value, list) and "items" in schema:
        for i, v in enumerate(value):
            _check(root, schema["items"], v, f"{path}[{i}]", errors)


def validate_schema(data) -> list[tuple[str, str]]:
    schema = load_schema()
    errors: list[tuple[str, str]] = []
    _check(schema, schema, data, "", errors)
    return errors
