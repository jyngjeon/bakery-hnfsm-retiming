"""Helpers to save / load experiment results so notebooks only read files."""

from __future__ import annotations

import json
import platform
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd


def _git_rev() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return None


def save_json(path: Path, payload: dict) -> Path:
    """Write payload plus run metadata (timestamp, python, git revision)."""
    payload = dict(payload)
    payload.setdefault("meta", {})
    payload["meta"].update({
        "created": datetime.now().isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "git_rev": _git_rev(),
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=_default)
    return path


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_csv(path: Path, df: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


def _default(o):
    if hasattr(o, "item"):
        return o.item()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"not JSON serializable: {type(o)}")
