"""
Tiny JSON-file persistence helper so Rin's memory (facts, mood, inside jokes)
survives bot restarts instead of resetting every time the process restarts.
"""
import json
import os
from typing import Any

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def _path(name: str) -> str:
    return os.path.join(DATA_DIR, f"{name}.json")


def load(name: str, default: Any) -> Any:
    """Load JSON data by name, returning `default` if missing or corrupt."""
    path = _path(name)
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save(name: str, data: Any) -> None:
    """Atomically write JSON data by name."""
    path = _path(name)
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f)
        os.replace(tmp_path, path)
    except OSError:
        pass
