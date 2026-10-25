"""resume-design: local, offline resume generation toolkit (stdlib only)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _version() -> str:
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


__version__ = _version()
