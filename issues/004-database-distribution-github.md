# 004 — Database distribution via GitHub Releases

**Type:** AFK  
**Status:** Open  
**Blocked by:** [002](002-prepare-sdk-tree-sitter.md), [003](003-prepare-docs-pdf-html.md)

---

## What to build

Implement the push/download workflow so one team member can publish a versioned database set and the rest of the team can download it in one command. Distribution uses GitHub Releases (assets), not Git LFS or repo blobs, to avoid binary-in-repo problems. JForge support is deferred and will be added once access is provided.

## Acceptance criteria

- [ ] `raghub push <version> --repo github` uploads `code.db`, `docs.db`, `config.json`, and `manifest.json` as assets to a GitHub Release tagged `<version>`
- [ ] `raghub list-databases --repo github` lists all available release tags with their SoC and SDK version metadata
- [ ] `raghub download <version>` fetches the release assets into `~/.raghub/<version>/` with a progress bar; completes in under 60 seconds for a ≤500 MB package on a typical office connection
- [ ] `raghub delete <version>` removes the local `~/.raghub/<version>/` directory after confirmation prompt
- [ ] GitHub auth uses the `GITHUB_TOKEN` env var (or `gh` CLI credential); missing auth produces a clear error message
- [ ] `push` refuses to overwrite an existing release tag without `--force`
- [ ] Downloaded assets are checksum-verified against a `manifest.json` SHA-256 hash before use

## Notes

- JForge (`--repo jforge`) flag is stubbed with a `NotImplementedError` and a message directing the user to wait for access credentials.

## Updates

<!-- Append timestamped notes here as work progresses -->
