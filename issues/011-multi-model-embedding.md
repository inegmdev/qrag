# 011 — Multi-model embedding support

**Type:** AFK
**Status:** Open
**Blocked by:** None — can start after 008-perf lands

---

## Motivation

`all-MiniLM-L6-v2` is baked into `embedder.py` as `MODEL_NAME` and written into
`config.json` as `"embedding_model": "all-MiniLM-L6-v2"`. Users who need higher
recall (e.g. `bge-large-en-v1.5`, 1024-dim) or a smaller footprint (e.g.
`all-MiniLM-L4-v2`, 256-dim) cannot switch without editing source.

The model used to build the DB is a **shared contract**: the query embedding at
search time must use the exact same model or cosine similarity comparisons are
meaningless. This issue makes that contract explicit and enforced.

## What to build

- Add `--model` option to `qrag prepare` (default: `all-MiniLM-L6-v2`)
- Store chosen model name in the version's `config.json` as `embedding_model`
- Detect model mismatch on incremental re-run: if the manifest exists with a
  different model, exit with a clear message and suggest `--force`
- Derive `EMBEDDING_DIM` from `SentenceTransformer.get_sentence_embedding_dimension()`
  at runtime instead of hardcoding 384; pass the correct dim to `init_code_db` /
  `init_docs_db` when creating the virtual tables
- `qrag search` (and the MCP server) read `embedding_model` from the active
  version's `config.json` and load that model for query embedding — not a
  hardcoded constant

## Acceptance criteria

- [ ] `qrag prepare --model bge-large-en-v1.5 -i src/ -o my-db` completes end-to-end
- [ ] Second `qrag prepare -i src/ -o my-db` with same model re-uses existing DB (incremental)
- [ ] `qrag prepare --model all-MiniLM-L4-v2 -i src/ -o my-db` on an existing DB with
      a different model exits non-zero with a clear message; `--force` rebuilds cleanly
- [ ] `qrag search code "foo"` loads whichever model is recorded in `config.json`
- [ ] `EMBEDDING_DIM` is derived at runtime, not a compile-time constant
- [ ] MCP tools use the model from `config.json`, not a hardcoded import

## Files affected

- `src/qrag/embedder.py` — `MODEL_NAME`, `EMBEDDING_DIM`, `_get_model()`
- `src/qrag/database.py` — `init_code_db`, `init_docs_db` (receive dim as param)
- `src/qrag/cli.py` — `prepare` (`--model` flag, mismatch check), `search` (load model from cfg)
- `src/qrag/mcp_server.py` — load model from active version's config
- `src/qrag/config.py` — no change; model stored in per-version `config.json`

## Notes

Scope: local HuggingFace sentence-transformer models only. Provider selection
(OpenAI embeddings, Cohere, etc.) is explicitly out of scope for this issue.
