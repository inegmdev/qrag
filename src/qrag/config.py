import json
import os
import shutil
from pathlib import Path

CACHE_DIR = Path.home() / ".qrag"
GLOBAL_CONFIG = CACHE_DIR / "config.json"

_DEFAULTS = {
    "repo_type": "github",
    "repo_url": "",
    "active_versions": [],
    "remotes": {},
    "cache_dir": str(CACHE_DIR),
}

_OLD_CACHE_DIR = Path.home() / ".raghub"


def _migrate_if_needed() -> None:
    """Migrate ~/.raghub to ~/.qrag on first run if old dir exists and new does not."""
    if _OLD_CACHE_DIR.exists() and not CACHE_DIR.exists():
        shutil.copytree(_OLD_CACHE_DIR, CACHE_DIR)
        print(f"[qrag] Migrated existing data from {_OLD_CACHE_DIR} to {CACHE_DIR}")


def load_global() -> dict:
    _migrate_if_needed()
    if GLOBAL_CONFIG.exists():
        with open(GLOBAL_CONFIG) as f:
            cfg = json.load(f)
        merged = {**_DEFAULTS, **cfg}
        # Migrate active_version (str) → active_versions (list)
        if "active_version" in merged:
            old = merged.pop("active_version")
            if "active_versions" not in cfg:
                merged["active_versions"] = [old] if old else []
        # Migrate legacy single repo_url/repo_type → remotes["default"]
        if not merged.get("remotes") and merged.get("repo_url"):
            merged["remotes"] = {
                "default": {"type": merged.get("repo_type", "github"), "url": merged["repo_url"]}
            }
        return merged
    return dict(_DEFAULTS)


def save_global(cfg: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cfg.pop("active_version", None)  # never persist the old key
    with open(GLOBAL_CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)


def active_version_dirs() -> list[Path]:
    cfg = load_global()
    return [CACHE_DIR / v for v in cfg.get("active_versions", []) if v]


def code_db_paths() -> list[Path]:
    return [d / "code.db" for d in active_version_dirs()]


def docs_db_paths() -> list[Path]:
    return [d / "docs.db" for d in active_version_dirs()]


def add_active_version(version: str) -> None:
    """Add a version to the active list (deduplicated)."""
    cfg = load_global()
    versions = cfg.get("active_versions", [])
    if version not in versions:
        versions.append(version)
    cfg["active_versions"] = versions
    save_global(cfg)


def remove_active_version(version: str) -> bool:
    """Drop a version from the active list. Returns True if it was active."""
    cfg = load_global()
    versions = cfg.get("active_versions", [])
    if version in versions:
        versions.remove(version)
        cfg["active_versions"] = versions
        save_global(cfg)
        return True
    return False


def repo_url() -> str | None:
    env_url = os.getenv("QRAG_GITHUB_URL")
    if env_url:
        return env_url
    cfg = load_global()
    return cfg.get("repo_url")


def set_repo_url(url: str) -> None:
    cfg = load_global()
    cfg["repo_url"] = url
    save_global(cfg)


def manifest_path(version: str) -> Path:
    return CACHE_DIR / version / "manifest.json"


# ---------------------------------------------------------------------------
# Named remotes registry (multi-remote distribution)
# ---------------------------------------------------------------------------

def get_remotes() -> dict:
    """Return the {name: {type, url}} remote registry."""
    return load_global().get("remotes", {})


def get_remote(name: str) -> dict | None:
    return get_remotes().get(name)


def default_remote() -> tuple[str, dict] | None:
    """Return (name, cfg) of the default remote, or the first one, or None."""
    remotes = get_remotes()
    if "default" in remotes:
        return "default", remotes["default"]
    if remotes:
        name = next(iter(remotes))
        return name, remotes[name]
    return None


def add_remote(name: str, remote_type: str, url: str) -> None:
    cfg = load_global()
    cfg.setdefault("remotes", {})[name] = {"type": remote_type, "url": url}
    save_global(cfg)


def remove_remote(name: str) -> bool:
    """Remove a remote by name. Returns True if it existed."""
    cfg = load_global()
    existed = name in cfg.get("remotes", {})
    if existed:
        del cfg["remotes"][name]
        save_global(cfg)
    return existed
