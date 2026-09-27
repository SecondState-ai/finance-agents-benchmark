"""Minimal dotenv value loading with no shell evaluation or expansion."""

from __future__ import annotations

import re
from pathlib import Path


def read_dotenv_value(path: Path, requested_key: str) -> str | None:
    if not path.is_file():
        return None
    found: str | None = None
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or key != requested_key:
            continue
        if found is not None:
            raise ValueError(f"Duplicate {requested_key} in {path} at line {line_number}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        found = value
    return found
