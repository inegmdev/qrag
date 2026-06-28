"""ZIP-based database export / import for offline sharing."""

from __future__ import annotations

import datetime
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import click

from .config import CACHE_DIR, GLOBAL_CONFIG, add_active_version

if TYPE_CHECKING:
    from rich.progress import Progress as RichProgress


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_tracked(path: Path, progress: RichProgress, task_id: int) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
            progress.advance(task_id, len(chunk))
    return h.hexdigest()


def _compress_into_zip(
    zf: zipfile.ZipFile, arcname: str, path: Path, progress: RichProgress, task_id: int
) -> None:
    with zf.open(arcname, "w", force_zip64=True) as dest:
        with open(path, "rb") as src:
            for chunk in iter(lambda: src.read(65536), b""):
                dest.write(chunk)
                progress.advance(task_id, len(chunk))


def _extract_from_zip(
    zf: zipfile.ZipFile, arcname: str, dest: Path, progress: RichProgress, task_id: int
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(arcname) as src:
        with open(dest, "wb") as f:
            for chunk in iter(lambda: src.read(65536), b""):
                f.write(chunk)
                progress.advance(task_id, len(chunk))


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

    config_path = version_dir / "config.json"
    embedding_model = ""
    if config_path.exists():
        with open(config_path) as f:
            embedding_model = json.load(f).get("embedding_model", "")

    total_bytes = sum(p.stat().st_size for p in files.values())
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from rich.progress import (
            BarColumn,
            DownloadColumn,
            Progress,
            TextColumn,
            TimeRemainingColumn,
            TransferSpeedColumn,
        )

        with Progress(
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
        ) as progress:
            # Phase 1: hash each file (read once, show progress)
            hash_task = progress.add_task("Hashing…", total=total_bytes)
            checksums: dict[str, str] = {}
            for fname, fpath in files.items():
                progress.update(hash_task, description=f"Hashing  {fname}")
                checksums[fname] = _sha256_tracked(fpath, progress, hash_task)

            manifest: dict = {
                "version": version,
                "exported_at": datetime.datetime.utcnow().isoformat() + "Z",
                "embedding_model": embedding_model,
                "files": {
                    fname: {"sha256": checksums[fname], "size": files[fname].stat().st_size}
                    for fname in files
                },
            }

            # Phase 2: compress each file into ZIP (stream, show progress)
            compress_task = progress.add_task("Compressing…", total=total_bytes)
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(f"{version}/manifest.json", json.dumps(manifest, indent=2))
                for fname, fpath in files.items():
                    progress.update(compress_task, description=f"Compressing {fname}")
                    _compress_into_zip(zf, f"{version}/{fname}", fpath, progress, compress_task)

    except ImportError:
        # Fallback: per-file status lines, no byte-level bar
        checksums = {}
        for fname, fpath in files.items():
            click.echo(f"  Hashing {fname}…")
            checksums[fname] = _sha256(fpath)

        manifest = {
            "version": version,
            "exported_at": datetime.datetime.utcnow().isoformat() + "Z",
            "embedding_model": embedding_model,
            "files": {
                fname: {"sha256": checksums[fname], "size": files[fname].stat().st_size}
                for fname in files
            },
        }

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{version}/manifest.json", json.dumps(manifest, indent=2))
            for fname, fpath in files.items():
                click.echo(f"  Compressing {fname}…")
                zf.write(fpath, f"{version}/{fname}")

    click.echo(f"\nExported {len(files)} file(s) → {output_path}")
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

    # Build a map of arcname → dest path for all non-manifest entries
    file_meta = manifest.get("files", {})
    total_bytes = sum(m["size"] for m in file_meta.values())

    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            all_entries = [
                info for info in zf.infolist()
                if not info.filename.endswith("/manifest.json")
                and len(Path(info.filename).parts) >= 2
            ]

            try:
                from rich.progress import (
                    BarColumn,
                    DownloadColumn,
                    Progress,
                    TextColumn,
                    TimeRemainingColumn,
                    TransferSpeedColumn,
                )

                with Progress(
                    TextColumn("[bold cyan]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                ) as progress:
                    # Phase 1: extract
                    extract_task = progress.add_task("Extracting…", total=total_bytes)
                    for info in all_entries:
                        parts = Path(info.filename).parts
                        fname = Path(*parts[1:]).name
                        dest = target_dir / Path(*parts[1:])
                        progress.update(extract_task, description=f"Extracting {fname}")
                        _extract_from_zip(zf, info.filename, dest, progress, extract_task)

                    # Phase 2: verify checksums
                    verify_task = progress.add_task("Verifying…", total=total_bytes)
                    for fname, meta in file_meta.items():
                        fpath = target_dir / fname
                        if not fpath.exists():
                            continue
                        progress.update(verify_task, description=f"Verifying  {fname}")
                        actual = _sha256_tracked(fpath, progress, verify_task)
                        if actual != meta["sha256"]:
                            raise click.ClickException(
                                f"Checksum mismatch for {fname}: "
                                f"expected {meta['sha256'][:12]}… got {actual[:12]}…"
                            )

            except ImportError:
                # Fallback: per-file status lines
                for info in all_entries:
                    parts = Path(info.filename).parts
                    fname = Path(*parts[1:]).name
                    dest = target_dir / Path(*parts[1:])
                    click.echo(f"  Extracting {fname}…")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(info.filename))

                for fname, meta in file_meta.items():
                    fpath = target_dir / fname
                    if not fpath.exists():
                        continue
                    click.echo(f"  Verifying {fname}…")
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
    click.echo(f"\nImported '{target_version}' → {target_dir}")
    click.echo(f"  Run: qrag ai active {target_version}")
    return target_version
