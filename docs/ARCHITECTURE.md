# qrag — Architecture & Design Decisions

This file documents the key architectural decisions in qrag with Mermaid diagrams.
Update it whenever a design decision is made or changed. Use Mermaid syntax for all diagrams.

---

## System Overview

```mermaid
flowchart TD
    subgraph PREP["PREPARATION — runs once per team"]
        SRC["Source files\nC / C++ / Rust / Python / Go / …"]
        BUILD["Build files\nCMake / Cargo / Makefile / …"]
        DOCS["Docs\n.pdf / .html"]
        SRC & BUILD & DOCS --> CHUNKER["chunker.py\ntree-sitter-language-pack\n305+ grammars"]
        CHUNKER --> EMBEDDER["embedder.py\nall-MiniLM-L6-v2\n384-dim, local"]
        EMBEDDER --> DBPY["database.py\nSQLite + sqlite-vec"]
        DBPY --> CODEDB[("code.db\ncode_chunks\nsymbols\nvec_code")]
        DBPY --> DOCSDB[("docs.db\ndoc_sections\nvec_docs")]
        CODEDB & DOCSDB --> GHDIST["github_distribution.py\nGitHub Releases"]
    end

    GHDIST -->|"qrag hub push"| ASSET[/"GitHub Release Asset"/]
    ASSET  -->|"qrag hub download"| TEAM

    subgraph TEAM["TEAM USAGE — every developer"]
        CFG["~/.qrag/config.json\nactive_versions: v1, v2, …"]
        V1[("~/.qrag/v1/\ncode.db  docs.db")]
        V2[("~/.qrag/v2/\ncode.db  docs.db")]
        CFG --> V1 & V2
        AI["AI Agent\nClaude / Gemini CLI"] <-->|"MCP JSON-RPC"| MCP["mcp_server.py"]
        MCP --> V1 & V2
    end
```

---

## AD-1: Multi-DB Fan-Out Search (IS3)

**Decision:** Users can activate multiple independently-prepared databases at once.
All four MCP tools fan-out across every active DB in parallel, merge results by
score, and deduplicate before returning to the AI agent.

**Why:** Teams work with multiple SDKs, RTOSes, and doc sets simultaneously.
Requiring a merged re-prepare for each new source is prohibitive. Pre-built DBs
downloaded independently must be queryable together without rebuilding.

### Config Migration

```mermaid
flowchart LR
    OLD["config.json\nactive_version: 'v1'\n(string — legacy)"]
    -->|"auto-migrated on first load\nold key never written back"| NEW["config.json\nactive_versions: ['v1']\n(list — current)"]
```

### Fan-Out Flow

```mermaid
flowchart TD
    AGENT["AI Agent"]
    AGENT -->|"tools/call search_code { query }"| MCP["mcp_server.py"]
    MCP --> EMB["embed_one(query)\n→ 384-dim vector"]
    EMB --> POOL["ThreadPoolExecutor\nmax_workers = min(N, 8)"]
    POOL --> DB1[("code.db\nsdk-v1")]
    POOL --> DB2[("code.db\nrtos-v2")]
    POOL --> DBN[("code.db\ntrm-v3")]
    DB1 -->|"top-10"| MERGE
    DB2 -->|"top-10"| MERGE
    DBN -->|"top-10"| MERGE
    MERGE["Sort by similarity_score DESC\nDeduplicate by file_path + line_start\nReturn top-10"]
    MERGE --> AGENT
```

### Per-DB Search (inside database.py)

```mermaid
flowchart TD
    QV["query vector\n384-dim float"]
    QV --> VEC["sqlite-vec\nvec_cosine_distance(vec_code, query_vec)"]
    VEC --> SORT["ORDER BY distance ASC  LIMIT top_k"]
    SORT --> JOIN["JOIN code_chunks ON rowid"]
    JOIN --> OUT["Result row\n{ symbol_name, file_path, line_start, line_end,\n  code_snippet, type, language, similarity_score }"]
```

### Complexity

| Scenario | Wall-clock cost |
|----------|----------------|
| 1 DB | 1× single-DB search latency |
| N DBs (N ≤ 8) | ≈ 1× single-DB search latency (fully parallel) |
| N DBs (N > 8) | ≈ ⌈N/8⌉ × single-DB search latency |

sqlite-vec cosine search is **O(rows)** per DB. At ~4 MB per DB (~10k chunks),
a single search completes in <50 ms on CPU. 100 DBs with 8 workers = ~13 rounds
≈ 650 ms worst case — acceptable for an AI-agent tool call.

### CLI Usage

```
# Set one active version
qrag ai active sdk-v1

# Set multiple active versions (replaces the list)
qrag ai active sdk-v1 rtos-v2 trm-v3

# Show current active versions
qrag ai active

# prepare and hub download auto-add to the list
qrag prepare -i /path/to/code -o sdk-v1      # → active_versions gains "sdk-v1"
qrag hub download rtos-v2                    # → active_versions gains "rtos-v2"
```

---

## AD-2: Dependency Split — Consumer vs Builder (GH#13)

**Decision:** Builder dependencies (parsing, grammar, doc parsing) are optional
extras. The consumer install only needs `click + sqlite-vec + sentence-transformers`.

**Why:** `sentence-transformers` pulls in `torch` and GPU deps. `tree-sitter-language-pack`
is large. Teams that only download and query pre-built DBs shouldn't pay that cost.

```mermaid
flowchart LR
    subgraph BASE["Base install\nuv tool install qrag"]
        CL["click >= 8.1"]
        SV["sqlite-vec >= 0.1.6"]
        ST["sentence-transformers >= 3.0"]
    end

    subgraph BUILD["[build] extra"]
        TS["tree-sitter >= 0.22"]
        TSP["tree-sitter-language-pack >= 0.7.2"]
        MU["pymupdf >= 1.24"]
        H2["html2text >= 2024.2"]
        BS["beautifulsoup4 >= 4.12"]
    end

    subgraph GPU["[build-gpu] extra"]
        TO["torch >= 2.0"]
    end

    BASE --> CONSUMER["Consumer\ndownload + MCP search"]
    BASE & BUILD --> BUILDER["Builder\nqrag prepare"]
    BASE & BUILD & GPU --> FULL["Full\nqrag[full]"]
```

**Guard in `prepare()`:** `_ensure_build_deps()` probes `tree_sitter`, `fitz`,
`tree_sitter_language_pack` → prints reinstall instructions and exits 1 if missing.

---

## AD-3: Embedding Model — Bundled Local (all-MiniLM-L6-v2)

**Decision:** `all-MiniLM-L6-v2` (384-dim) is bundled inside the wheel under
`src/qrag/models/`. No HuggingFace call at runtime.

**Why:** Air-gapped embedded-systems environments cannot reach HuggingFace.
Startup time must be deterministic. The model is small (≈22 MB).

**Trade-off:** Wheel is larger. Model version is pinned and must be explicitly
updated. A future model upgrade requires a new wheel release.

```mermaid
flowchart LR
    WHEEL["qrag wheel\nsrc/qrag/models/all-MiniLM-L6-v2/"]
    -->|"_get_model() loads at first embed call"| MODEL["in-process model\nno network call"]
    MODEL --> EMB["384-dim embedding vector"]
```

---

## AD-4: SQLite + sqlite-vec (no external vector DB)

**Decision:** All storage is a single SQLite file with sqlite-vec for vector
search. No Chroma, Pinecone, or other external service.

**Why:** Pre-built DBs are distributed as GitHub Release assets and downloaded
by the team. A single-file format requires zero server infra, works offline,
and is trivially versioned via GitHub Releases.

**Trade-off:** sqlite-vec cosine search is O(n) — no ANN index. At current
scale (~10k chunks per DB) this is fast enough. If a single DB exceeds ~1M
chunks, an ANN index (e.g. FAISS) would be needed.

```mermaid
flowchart LR
    subgraph DB["Single SQLite file  (~4 MB per DB)"]
        CC["code_chunks\n(symbol_name, file_path, language, …)"]
        SYM["symbols\n(name, type, language, …)"]
        VC["vec_code\n(rowid → 384-dim blob)"]
        DS["doc_sections\n(title, content, page_range, …)"]
        VD["vec_docs\n(rowid → 384-dim blob)"]
    end

    Q["query vector"] -->|"vec_cosine_distance"| VC & VD
    VC -->|"JOIN"| CC
    VD -->|"JOIN"| DS
```

---

## AD-5: Multi-Language Parsing — Registry-Driven (C0)

**Decision:** `chunker.py` uses `tree-sitter-language-pack` (305+ grammars)
with a registry-driven rule engine. `chunk_type` is a free-form string, not an enum.

**Why:** Individual `tree-sitter-c/cpp` packages don't scale to 30+ languages.
Free-form `chunk_type` means new language support never requires a DB schema
migration — just a new registry entry.

```mermaid
flowchart TD
    FILE["Input file\n(path + extension / filename)"]
    FILE --> REG{"_EXT_REGISTRY\n_FILENAME_REGISTRY"}
    REG -->|"match"| LANG["_LangConfig\n{ ts_name, rules: [_Rule] }"]
    REG -->|"no match"| SKIP["skip file"]
    LANG --> PARSER["tree-sitter-language-pack\nget_parser(ts_name)"]
    PARSER --> AST["Parse tree\nAST node traversal"]
    AST --> RULE["_Rule\n{ node_types → chunk_type\n  extract_name callable }"]
    RULE --> CHUNK["CodeChunk\n{ symbol_name, chunk_type, language\n  file_path, file_name, line_start, line_end\n  code_text, parent_name, call_depth, chunk_index=0 }"]
    CHUNK -->|"large chunk"| SPLIT["auto-split with\noverlap (512 tok max)\nchunk_index=0,1,2,…"]
    CHUNK & SPLIT --> OUT["insert into code_chunks + symbols"]
```

---

## AD-6: Rich Code Metadata — IS5

**Decision:** `code_chunks` gains four new columns: `file_name` (basename), `parent_name`
(enclosing block), `call_depth` (nesting level), `chunk_index` (sub-chunk index within
a split symbol). Existing DBs are auto-migrated via `ALTER TABLE` on open.

**Why:** The AI agent needs precise citation (file + line range), structural context
(what class/namespace owns this function), and sub-chunk tracking (which slice of a
large function it is looking at) to answer questions accurately.

```mermaid
flowchart TD
    ROOT["AST root\ndepth=0, parent=''"]
    ROOT -->|"rule.recurse=True\nname='MyClass'"| CLASS["CodeChunk\nsymbol_name='MyClass'\ncall_depth=0\nparent_name=''"]
    CLASS -->|"recurse children\ndepth=1, parent='MyClass'"| METHOD["CodeChunk\nsymbol_name='my_method'\ncall_depth=1\nparent_name='MyClass'"]
    ROOT -->|"rule.recurse=False\nname='free_fn'"| FREE["CodeChunk\nsymbol_name='free_fn'\ncall_depth=0\nparent_name=''"]
    FREE -->|"> 512 tokens"| SPLIT["sub-chunks\nfree_fn#0, free_fn#1, …\nchunk_index=0,1,…"]
```

**Schema migration:** `_open_code()` runs `ALTER TABLE code_chunks ADD COLUMN …` for
each new column on every open; `sqlite3.OperationalError` is swallowed when the column
already exists. `init_code_db` includes all columns in `CREATE TABLE IF NOT EXISTS`.

---

## AD-7: Rich Doc Metadata — IS4

**Decision:** `doc_sections` gains five new columns: `doc_name`, `doc_revision`,
`doc_status`, `word_count`, `fig_table_refs`. Extracted at parse time from the filename
and section content. Existing DBs are auto-migrated on open via `_open_docs()`.

**Why:** LLMs need to cite documents precisely (which document, which revision, which
status). Figure/table references let the agent locate companion material. Word count
helps the agent judge whether content has been truncated.

```mermaid
flowchart LR
    FILE["PDF / HTML file\n'STM32F4_RM_rev3_draft.pdf'"]
    FILE -->|"path.stem"| META["doc_name = 'STM32F4_RM_rev3_draft.pdf'\ndoc_revision = '3'  (_REV_RE)\ndoc_status = 'draft'  (_STATUS_KEYWORDS)"]
    FILE -->|"parse content"| CONTENT["section content text"]
    CONTENT -->|"_extract_fig_table_refs"| REFS["fig_table_refs = 'Figure 3-1,Table 4-2'"]
    CONTENT -->|"len(split)"| WC["word_count = N"]
    META & REFS & WC --> DB[("doc_sections row")]
```

**Revision extraction:** `_REV_RE = r'[_\\-\\s](?:rev?|ver?|version)\\.?\\s*(\\d+[.\\d]*)'`
matches `_rev3`, `_v2`, `_Rev1.2` etc. from the filename stem.

**Status extraction:** first match of `released | approved | final | review | draft | obsolete`
in the lowercased filename stem. Empty string if none matched.
