# 008 — GPU-accelerated embedding + multi-core chunking

**Type:** AFK  
**Status:** Open  
**Blocked by:** None — can start immediately

---

## What to build

Make `rhub prepare` faster by: (1) routing embedding through CUDA when a GPU is available, with a `--device` flag for manual override; (2) parallelising the chunking stage across multiple CPU cores, with a `--limit-cpu` cap.

Tree-sitter chunking is CPU-bound and has no GPU path — parallelism here is multi-process/thread. Embedding via `SentenceTransformer` already supports CUDA; we just need to pass the right `device` argument and surface it to the user.

## Acceptance criteria

- [ ] `rhub prepare` accepts `--device=auto|cpu|cuda` (default `auto`)
- [ ] `auto` mode: detects CUDA via `torch.cuda.is_available()`; falls back to CPU silently if not found
- [ ] Device selected is printed at prepare session start: e.g., `[prepare] embedding device: cuda` or `[prepare] embedding device: cpu`
- [ ] `rhub prepare` accepts `--limit-cpu=N` (default: all available cores)
- [ ] Sanity check: if `N > os.cpu_count()`, exit with a clear error message before starting
- [ ] Chunking stage uses `concurrent.futures.ProcessPoolExecutor(max_workers=N)` (or equivalent)
- [ ] Both flags are documented in `--help` output
- [ ] Prepare wall-clock time is measurably faster on a multi-core machine with >10 files

## Updates

<!-- Append timestamped notes here as work progresses -->
