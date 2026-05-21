"""GitHub Releases-based database distribution."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import click


def _get_github_token() -> str | None:
    """Get GitHub token from env var or gh CLI."""
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return None


def _run_gh_cmd(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run gh CLI command with error handling."""
    try:
        return subprocess.run(args, capture_output=True, text=True, check=check)
    except FileNotFoundError:
        click.echo("Error: 'gh' CLI not found. Install it from https://cli.github.com", err=True)
        sys.exit(1)


def _compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    hash_obj = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()


def _create_manifest(version_dir: Path) -> dict[str, Any]:
    """Create manifest.json with checksums for all assets."""
    manifest = {"version": version_dir.name, "files": {}}

    config_path = version_dir / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            version_cfg = json.load(f)
        manifest["soc"] = version_cfg.get("soc", "")
        manifest["embedding_model"] = version_cfg.get("embedding_model", "")

    for fname in ["code.db", "docs.db", "config.json"]:
        fpath = version_dir / fname
        if fpath.exists():
            manifest["files"][fname] = {
                "sha256": _compute_sha256(fpath),
                "size": fpath.stat().st_size,
            }

    return manifest


def push_to_github(
    repo_url: str,
    version: str,
    version_dir: Path,
    force: bool = False,
) -> None:
    """Push version databases to GitHub Releases."""
    if not _get_github_token():
        click.echo(
            "Error: No GitHub authentication found.\n"
            "  Set GITHUB_TOKEN env var or ensure 'gh auth login' has been run.",
            err=True,
        )
        sys.exit(1)

    # Extract owner/repo from URL
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]
    repo_path = repo_url.split("github.com/", 1)[-1] if "github.com" in repo_url else repo_url

    # Check if release exists
    check_result = _run_gh_cmd(
        ["gh", "release", "view", version, "--repo", repo_path],
        check=False,
    )

    if check_result.returncode == 0 and not force:
        click.echo(f"Release '{version}' already exists. Use --force to overwrite.", err=True)
        sys.exit(1)

    # Create or update release
    if check_result.returncode == 0:
        click.echo(f"Deleting existing release '{version}'...")
        _run_gh_cmd(["gh", "release", "delete", version, "--repo", repo_path, "--yes"])

    click.echo(f"Creating release '{version}'...")
    _run_gh_cmd([
        "gh", "release", "create", version,
        "--repo", repo_path,
        "--title", f"Database v{version}",
    ])

    # Create and upload manifest
    manifest = _create_manifest(version_dir)
    manifest_path = version_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Upload all assets
    assets_to_upload = []
    for fname in ["code.db", "docs.db", "config.json", "manifest.json"]:
        fpath = version_dir / fname
        if fpath.exists():
            assets_to_upload.append(str(fpath))

    if not assets_to_upload:
        click.echo("Warning: No files to upload.", err=True)
        return

    click.echo(f"Uploading {len(assets_to_upload)} asset(s)...")
    with click.progressbar(assets_to_upload, label="  Uploading", width=60) as bar:
        for asset in bar:
            _run_gh_cmd([
                "gh", "release", "upload", version,
                asset,
                "--repo", repo_path,
                "--clobber",
            ])

    click.echo(f"✓ Published to {repo_url}/releases/tag/{version}")


def list_databases(repo_url: str) -> None:
    """List available databases on GitHub Releases."""
    if not _get_github_token():
        click.echo(
            "Error: No GitHub authentication found.\n"
            "  Set GITHUB_TOKEN env var or ensure 'gh auth login' has been run.",
            err=True,
        )
        sys.exit(1)

    # Extract owner/repo from URL
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]
    repo_path = repo_url.split("github.com/", 1)[-1] if "github.com" in repo_url else repo_url

    result = _run_gh_cmd([
        "gh", "release", "list",
        "--repo", repo_path,
        "--json", "tagName,name",
    ])

    if result.returncode != 0:
        click.echo(f"Error fetching releases: {result.stderr}", err=True)
        sys.exit(1)

    try:
        releases = json.loads(result.stdout)
    except json.JSONDecodeError:
        click.echo("Error parsing releases.", err=True)
        sys.exit(1)

    if not releases:
        click.echo("No releases found.")
        return

    click.echo("Available databases:")
    for rel in releases:
        click.echo(f"  {rel['tagName']} — {rel['name']}")


def download_database(
    repo_url: str,
    version: str,
    output_dir: Path,
) -> None:
    """Download version database from GitHub Releases."""
    if not _get_github_token():
        click.echo(
            "Error: No GitHub authentication found.\n"
            "  Set GITHUB_TOKEN env var or ensure 'gh auth login' has been run.",
            err=True,
        )
        sys.exit(1)

    # Extract owner/repo from URL
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]
    repo_path = repo_url.split("github.com/", 1)[-1] if "github.com" in repo_url else repo_url

    # Create output directory
    version_dir = output_dir / version
    version_dir.mkdir(parents=True, exist_ok=True)

    # Get release info
    result = _run_gh_cmd([
        "gh", "release", "view", version,
        "--repo", repo_path,
        "--json", "assets",
    ])

    if result.returncode != 0:
        click.echo(f"Release '{version}' not found.", err=True)
        sys.exit(1)

    try:
        release = json.loads(result.stdout)
        assets = release.get("assets", [])
    except json.JSONDecodeError:
        click.echo("Error parsing release.", err=True)
        sys.exit(1)

    if not assets:
        click.echo(f"Release '{version}' has no assets.", err=True)
        sys.exit(1)

    click.echo(f"Downloading {len(assets)} file(s)...")
    manifest_data = None

    with click.progressbar(assets, label="  Downloading", width=60) as bar:
        for asset in bar:
            fname = asset["name"]
            fpath = version_dir / fname

            result = _run_gh_cmd([
                "gh", "release", "download", version,
                "--repo", repo_path,
                "-p", fname,
                "-D", str(version_dir),
            ])

            if result.returncode != 0:
                click.echo(f"Failed to download {fname}", err=True)
                sys.exit(1)

            if fname == "manifest.json" and fpath.exists():
                with open(fpath) as f:
                    manifest_data = json.load(f)

    # Verify checksums
    if manifest_data:
        click.echo("Verifying checksums...")
        for fname, info in manifest_data.get("files", {}).items():
            fpath = version_dir / fname
            if not fpath.exists():
                continue

            expected_sha256 = info.get("sha256")
            if not expected_sha256:
                continue

            actual_sha256 = _compute_sha256(fpath)
            if actual_sha256 != expected_sha256:
                click.echo(
                    f"Checksum mismatch for {fname}:\n"
                    f"  Expected: {expected_sha256}\n"
                    f"  Actual: {actual_sha256}",
                    err=True,
                )
                sys.exit(1)

        click.echo("✓ All checksums verified.")

    click.echo(f"✓ Downloaded to {version_dir}")


def delete_database(version_dir: Path) -> None:
    """Delete a local database version."""
    if not version_dir.exists():
        click.echo(f"Version directory not found: {version_dir}", err=True)
        sys.exit(1)

    if click.confirm(f"Delete {version_dir.name}?"):
        import shutil
        shutil.rmtree(version_dir)
        click.echo(f"✓ Deleted {version_dir}")
    else:
        click.echo("Cancelled.")
