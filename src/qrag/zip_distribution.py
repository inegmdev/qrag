"""ZIP-based database export / import for offline sharing."""

from __future__ import annotations

import datetime
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import click

from .config import CACHE_DIR, GLOBAL_CONFIG, add_active_version


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def export_version(version: str, output_path: Path) -> None:
    """Package a local version directory into a self-contained ZIP."""
    version_dir = CACHE_DIR / version
    if not version_dir.exists():
        raise click.ClickException(f"Version '{version}' not found in {CACHE_DIR}")

    candidates = ["code.db", "docs.db", "config.json", "build-report.txt"]
    files = {
        f: version_dir / f
        for f in candidates
        if (version_dir / f).exists()
    }

    if not any(f in files for f in ("code.db", "docs.db")):
        raise click.ClickException(
            f"Nothing to export — no databases found for '{version}'"
        )

    manifest: dict = {
        "version": version,
        "exported_at": datetime.datetime.utcnow().isoformat() + "Z",
        "files": {
            fname: {"sha256": _sha256(fpath), "size": fpath.stat().st_size}
            for fname, fpath in files.items()
        },
    }
    config_path = version_dir / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            cfg = json.load(f)
        manifest["embedding_model"] = cfg.get("embedding_model", "")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{version}/manifest.json", json.dumps(manifest, indent=2))
        for fname, fpath in files.items():
            zf.write(fpath, f"{version}/{fname}")

    click.echo(f"Exported {len(files)} file(s) → {output_path}")
    for fname, fpath in files.items():
        click.echo(f"  {fname}  ({fpath.stat().st_size:,} bytes)")


def import_version(zip_path: Path, version_override: str | None, yes: bool) -> str:
    """Extract a ZIP export, verify checksums, and register the version."""
    with zipfile.ZipFile(zip_path) as zf:
        manifest_names = [n for n in zf.namelist() if n.endswith("/manifest.json")]
        if not manifest_names:
            raise click.ClickException("ZIP has no manifest.json — not a qrag export")
        manifest = json.loads(zf.read(manifest_names[0]))

    embedded_version = manifest["version"]
    target_version = version_override or embedded_version
    target_dir = CACHE_DIR / target_version

    if target_dir.exists():
        if not yes and not click.confirm(
            f"Version '{target_version}' already exists. Overwrite?", default=False
        ):
            raise click.ClickException("Aborted.")
        shutil.rmtree(target_dir)

    try:
        if GLOBAL_CONFIG.exists():
            with open(GLOBAL_CONFIG) as f:
                local_cfg = json.load(f)
            local_model = local_cfg.get("embedding_model", "")
            zip_model = manifest.get("embedding_model", "")
            if local_model and zip_model and local_model != zip_model:
                click.echo(
                    f"Warning: embedding model mismatch "
                    f"(local={local_model!r}, zip={zip_model!r}). "
                    "Search results may be degraded.",
                    err=True,
                )
    except Exception:
        pass

    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if info.filename.endswith("/manifest.json"):
                    continue
                parts = Path(info.filename).parts
                if len(parts) < 2:
                    continue
                dest = target_dir / Path(*parts[1:])
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(info.filename))

        for fname, meta in manifest.get("files", {}).items():
            fpath = target_dir / fname
            if not fpath.exists():
                continue
            actual = _sha256(fpath)
            if actual != meta["sha256"]:
                raise click.ClickException(
                    f"Checksum mismatch for {fname}: "
                    f"expected {meta['sha256'][:12]}… got {actual[:12]}…"
                )
    except click.ClickException:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise

    add_active_version(target_version)
    click.echo(f"Imported '{target_version}' → {target_dir}")
    click.echo(f"  Run: qrag ai active {target_version}")
    return target_version
