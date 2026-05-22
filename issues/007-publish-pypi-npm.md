# 007 — Publish Python package to PyPI + reserve npm package

**Type:** AFK  
**Status:** Open  
**Blocked by:** [006](006-polish-tests-docs.md)

---

## What to build

Publish `raghub` to PyPI via a GitHub Actions tag-triggered workflow so users can `pip install raghub`. In parallel, reserve the `raghub` name on npm with a stub package (README pointing to PyPI) to prevent name squatting before a JS wrapper is ever needed.

## Acceptance criteria

- [ ] GitHub Actions workflow at `.github/workflows/publish.yml` triggers on `v*` tag push
- [ ] Workflow builds the sdist + wheel (`python -m build`) and publishes to PyPI using `PYPI_TOKEN` repo secret
- [ ] `pyproject.toml` version is the single source of truth; workflow reads it, not a hardcoded string
- [ ] npm stub package `raghub` committed under `npm/` (or similar): `package.json` + `README.md` pointing users to PyPI
- [ ] npm publish step in the same workflow using `NPM_TOKEN` repo secret, triggered on the same tag
- [ ] Smoke test step in the workflow: `pip install raghub==$VERSION && raghub --version` passes
- [ ] Both PyPI and npm package pages show correct description, version, and links

## Updates

<!-- Append timestamped notes here as work progresses -->
