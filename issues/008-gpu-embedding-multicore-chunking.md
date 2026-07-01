# 008 — GPU-accelerated embedding + multi-core chunking

**Type:** AFK  
**Status:** Resolved — see `docs/ARCHITECTURE.md` AD-14  
**Blocked by:** None — can start immediately

---

## What to build

Make `rhub prepare` faster by: (1) routing embedding through CUDA when a GPU is available, with a `--device` flag for manual override; (2) parallelising the chunking stage across multiple CPU cores, with a `--limit-cpu` cap.

Tree-sitter chunking is CPU-bound and has no GPU path — parallelism here is multi-process/thread. Embedding via `SentenceTransformer` already supports CUDA; we just need to pass the right `device` argument and surface it to the user.

## Acceptance criteria

- [x] `qrag build` accepts `--device=auto|cpu|cuda` (default `auto`)
- [x] `auto` mode: detects CUDA via `onnxruntime.get_available_providers()` (project moved off `torch`/`sentence-transformers` to `onnxruntime` in GH#38, so detection uses onnxruntime's provider list instead); falls back to CPU silently if not found
- [x] Device selected is printed at build session start: e.g., `[build] device=cuda batch-size=1024 precision=float32`
- [x] `qrag build` accepts `--limit-cpu=N` (default: all available cores)
- [x] Sanity check: if `N > os.cpu_count()`, exit with a clear error message before starting
- [x] Chunking stage uses `concurrent.futures.ProcessPoolExecutor(max_workers=N)`
- [x] Both flags are documented in `--help` output
- [x] Build wall-clock time is measurably faster on a multi-core machine with >10 files (parallel chunking pre-existing; GPU embedding batch size raised to 1024 for throughput)

## Updates

- 2026-07-01: `--limit-cpu` + `ProcessPoolExecutor` chunking and the `--device` CLI flag already existed from prior work. What was missing: `resolve_device()` always returned `"cpu"` and raised a `ValueError` on `"cuda"` — GPU was never actually reachable, and `onnxruntime-gpu` couldn't be installed without conflicting with the base `onnxruntime` dependency. Fixed both: real CUDA detection via `onnxruntime.get_available_providers()`, `_load()` passes `CUDAExecutionProvider` to `InferenceSession`, and `onnxruntime`/`onnxruntime-gpu` split into `[cpu]`/`[gpu]` extras in `pyproject.toml`. README updated with per-OS (Linux/Windows/WSL) GPU prerequisites.
