import json
import os
from pathlib import Path

CACHE_DIR = Path.home() / ".quickrag-ti"
GLOBAL_CONFIG = CACHE_DIR / "config.json"

_DEFAULTS = {
    "repo_type": "github",
    "repo_url": "",
    "active_version": "",
    "cache_dir": str(CACHE_DIR),
}


def load_global() -> dict:
    if GLOBAL_CONFIG.exists():
        with open(GLOBAL_CONFIG) as f:
            cfg = json.load(f)
        return {**_DEFAULTS, **cfg}
    return dict(_DEFAULTS)


def save_global(cfg: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(GLOBAL_CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)


def active_version_dir() -> Path | None:
    cfg = load_global()
    if not cfg.get("active_version"):
        return None
    return CACHE_DIR / cfg["active_version"]


def code_db_path() -> Path | None:
    d = active_version_dir()
    if d is None:
        return None
    return d / "code.db"
