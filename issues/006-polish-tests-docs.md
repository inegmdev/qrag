# 006 — Polish: tests, logging, error handling, README

**Type:** HITL  
**Status:** Open  
**Blocked by:** [001](001-scaffold-search-code-e2e.md)–[005](005-mcp-server-install.md)

---

## What to build

Harden the tool for team use: structured logging, actionable error messages, a test suite covering the critical paths, and user-facing documentation. This slice requires human sign-off because "done" depends on team consensus that the tool feels right to use — not just that CI passes.

## Acceptance criteria

- [ ] Unit tests cover: chunker token-split logic, sqlite-vec BLOB round-trip, symbol upsert on re-run
- [ ] Integration test: `prepare` on the fixture C file + fixture PDF, then `search-code` and `search-trm` return expected top result
- [ ] All CLI error paths (missing config, missing DB, bad version name, missing `GITHUB_TOKEN`) print a one-line human-readable message and exit non-zero
- [ ] `--verbose` flag enables structured JSON logging to stderr for all commands
- [ ] `README.md` covers: install, quickstart (prepare → push → download → mcp install → use in Gemini), and CLI reference
- [ ] A `docs/quickstart.md` walkthrough for the AM62x use case is reviewed and approved by at least one team member
- [ ] `pytest` passes cleanly in CI (GitHub Actions workflow committed)
- [ ] Team sign-off recorded in the Updates section below

## Updates

<!-- Append timestamped notes here as work progresses -->
<!-- Record team sign-off here when received -->
