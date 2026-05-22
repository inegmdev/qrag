# 010 — Watch folder for live database updates (`--watch`)

**Type:** AFK  
**Status:** Open  
**Blocked by:** [009](009-incremental-database-update.md)

---

## What to build

Add a `--watch` / `-w` flag to `rhub prepare` that keeps the process running after the initial prepare, watching the `-i` directories for file system changes and triggering incremental updates automatically. Runs as a foreground process; Ctrl+C to stop.

This slice is intentionally thin — it delegates all diff logic to the incremental update machinery from issue 009 and only adds the file-watching loop on top.

## Design decisions

- **Interface:** `rhub prepare -i <dir> -o <name> --watch` (or `-w`). No separate `raghub watch` command.
- **Library:** [`watchdog`](https://pypi.org/project/watchdog/) — cross-platform, actively maintained, event-based (no polling).
- **Debouncing:** coalesce rapid successive events (e.g., editor save → temp file → final file) with a short debounce window (default 500 ms) before triggering a prepare cycle.
- **Mode:** foreground only. No daemon, no PID files. Users who need persistence can wrap with `tmux` or a systemd unit.

## Acceptance criteria

- [ ] `rhub prepare -i <dir> -o <name> --watch` (and `-w`) runs a normal prepare then enters watch mode
- [ ] Watch mode prints `[watch] watching <dirs> — press Ctrl+C to stop`
- [ ] Any file change in `-i` directories triggers an incremental update (reuses issue 009 logic)
- [ ] Rapid saves within the debounce window (500 ms default) result in a single prepare cycle, not N cycles
- [ ] Ctrl+C exits cleanly with `[watch] stopped`
- [ ] `watchdog` added to `pyproject.toml` dependencies
- [ ] `--watch` / `-w` documented in `--help` output
- [ ] `--watch` cannot be combined with `--force` (full rebuild on every change makes no sense); exit with error if both are passed

## Updates

<!-- Append timestamped notes here as work progresses -->
