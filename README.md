# qrag

Build semantic RAG databases from your code and docs — once per team, instant for every AI agent.

**Key idea:** One team member prepares the index once; the whole team downloads pre-built SQLite databases and gets instant semantic + structural code/doc search inside their AI agent (Claude, Gemini CLI).

---

## For End Users (consumers)

> Your team has already built a database and shared it. Follow these steps to start using it.

### 1. Install qrag

```bash
uv tool install "git+https://github.com/inegmdev/qrag.git@main[cpu]"
```

> The `[cpu]` extra installs the `onnxruntime` CPU backend, required even for running searches. Consumers never need `[gpu]` — that's only for database preparers running `qrag build`.

> Don't have `uv`? Install it: https://docs.astral.sh/uv/getting-started/installation/

**Upgrade to a newer version of qrag itself:**

```bash
uv tool install --reinstall "git+https://github.com/inegmdev/qrag.git@main[cpu]"
```

### 2. Point qrag at your team's database repository

```bash
export QRAG_GITHUB_URL=https://github.com/your-org/qrag-databases
```

Add this to your shell profile (`.bashrc`, `.zshrc`, etc.) so it persists.

### 3. Download the database

```bash
qrag hub list             # see available versions
qrag hub download v1.0    # download and add to active set
```

You can download multiple databases and search across all of them simultaneously:

```bash
qrag hub download sdk-v1
qrag hub download rtos-v2
qrag hub download trm-v3
# All three are now active — searches fan out across all of them
```

### 4. Set up your AI agent

```bash
qrag ai setup             # auto-detect Claude and/or Gemini
qrag ai setup --ai=claude
qrag ai setup --ai=gemini
```

Verify the setup:

```bash
qrag status
```

Expected output (with multiple active databases):

```
Active versions: sdk-v1, rtos-v2
  [sdk-v1] code.db: /home/user/.qrag/sdk-v1/code.db (exists)
  [sdk-v1] docs.db: /home/user/.qrag/sdk-v1/docs.db (exists)
  [rtos-v2] code.db: /home/user/.qrag/rtos-v2/code.db (exists)
  [rtos-v2] docs.db: /home/user/.qrag/rtos-v2/docs.db (exists)
```

### 5. Use in your AI agent

Restart your AI agent (Claude Code or Gemini CLI). Four tools are now available:

| Tool | Description |
|------|-------------|
| `search_code(query)` | Semantic search across indexed code |
| `search_docs(query)` | Semantic search across documentation sections |
| `get_symbol_definition(symbol)` | Exact definition of a function, struct, macro, etc. |
| `list_symbols(pattern="")` | List all indexed symbols, optionally filtered |

Searches automatically fan out across all active databases, merge results by relevance score, and deduplicate before returning to the agent.

### Managing active databases

```bash
qrag ai active                        # show currently active versions
qrag ai active sdk-v1 rtos-v2        # replace the active list
```

### Updating to a newer database version

```bash
qrag hub list
qrag hub download v1.1    # auto-added to the active set
```

---

## For Database Preparers (builders)

> You are the team member responsible for indexing code/docs and publishing the result.

### Prerequisites

- Python 3.10+
- GitHub CLI (`gh`) authenticated: `gh auth login`
- A GitHub repository to host the databases (e.g. `https://github.com/your-org/qrag-databases`)

### 1. Install qrag with build dependencies

> **Install size:** The CPU install (`[build,cpu]`) downloads **~220 MB**. GPU acceleration (`[build,gpu]`, alias `[full]`) swaps in `onnxruntime-gpu` plus the CUDA/cuDNN runtime (~600 MB, pulled in as ordinary pip packages) — opt in only if you have an NVIDIA GPU.

#### GPU Prerequisites (skip if using CPU)

`qrag[gpu]` installs the CUDA 12.x/cuDNN 9 runtime **as pip packages** (`nvidia-cuda-runtime-cu12`, `nvidia-cudnn-cu12`) — no system-wide CUDA Toolkit install is required. The only thing you need at the system level is the **NVIDIA driver** itself (drivers require a kernel module and can't be pip-installed).

<details><summary><b>Linux</b></summary>

Install the latest NVIDIA driver via your distro's package manager or NVIDIA's repo, then verify with `nvidia-smi`.

</details>

<details><summary><b>Windows</b></summary>

Install the latest NVIDIA driver from https://www.nvidia.com/Download/index.aspx, then verify with `nvidia-smi`.

</details>

<details><summary><b>WSL (Windows Subsystem for Linux)</b></summary>

> **Do not install an NVIDIA driver inside WSL.** GPU passthrough is provided by the Windows host driver alone — installing a Linux driver inside the WSL distro breaks it.

Install the NVIDIA driver on the **Windows host only** (not inside WSL) from https://www.nvidia.com/Download/index.aspx — it includes WSL2 GPU passthrough support. Then verify with `nvidia-smi` run *inside* WSL — it should report the host's GPU.

</details>

#### with uv (recommended)

```bash
# CPU — ~220 MB
uv tool install "git+https://github.com/inegmdev/qrag.git@main[build,cpu]"

# GPU-accelerated — requires an NVIDIA driver (see prerequisites above)
uv tool install "git+https://github.com/inegmdev/qrag.git@main[build,gpu]"
# or, equivalently:
uv tool install "git+https://github.com/inegmdev/qrag.git@main[full]"
```

#### with pipx

```bash
# CPU — ~220 MB
pipx install "git+https://github.com/inegmdev/qrag.git[build,cpu]"

# GPU-accelerated — requires an NVIDIA driver (see prerequisites above)
pipx install "git+https://github.com/inegmdev/qrag.git[full]"
```

#### with pip

```bash
# CPU — ~220 MB
pip install "git+https://github.com/inegmdev/qrag.git[build,cpu]"

# GPU-accelerated — requires an NVIDIA driver (see prerequisites above)
pip install "git+https://github.com/inegmdev/qrag.git[full]"
```

### 2. Configure the distribution repository

```bash
export QRAG_GITHUB_URL=https://github.com/your-org/qrag-databases
```

### 3. Build the index

Point `qrag` at directories containing source code and/or docs. Content type is detected automatically from file extensions and filenames.

```bash
qrag build \
  -i /path/to/source/ \
  -i /path/to/docs/ \
  -o v1.0
```

`--device` defaults to `auto`, which uses the GPU automatically if `[gpu]` is installed and CUDA is detected, falling back to CPU otherwise. Pass `--device=cpu` or `--device=cuda` to force a choice. The device in use is printed at the start of the build, e.g. `[build] device=cuda batch-size=1024 precision=float32`.

**Supported source types:**

- **Code:** C, C++, Rust, Python, Go, JavaScript, TypeScript, Java, C#, Ruby, Swift, Kotlin, Lua, Zig, and 30+ more languages via tree-sitter
- **Build files:** CMakeLists.txt, Makefile, Cargo.toml, package.json, go.mod, pom.xml, *.cmake, *.gradle, and more — indexed as first-class code
- **Docs:** PDF and HTML files, chunked section-by-section

What happens under the hood:

1. Source files are parsed with tree-sitter (305+ grammars); functions, structs, classes, macros, etc. are extracted into `code.db`
2. PDF/HTML files are parsed section-by-section into `docs.db`
3. Embeddings are generated locally using `all-MiniLM-L6-v2` (bundled, no network call)
4. Both databases are stored at `~/.qrag/v1.0/` and the version is added to the active set

### 4. Verify locally before pushing

```bash
qrag search code "memory allocation"
qrag search docs "configuration guide"
qrag search symbol "HAL_Init"
```

### 5. Push to GitHub for team distribution

```bash
qrag hub push v1.0
```

Notify your team to run `qrag hub download v1.0`.

### Updating the database

```bash
qrag build -i /path/to/source/ -i /path/to/docs/ -o v1.1
qrag hub push v1.1
```

---

## CLI Reference

```
qrag [--verbose] [--version] COMMAND [OPTIONS]
```

| Command | Description |
|---------|-------------|
| `build -i DIR -o NAME` | Parse, embed, and store code/docs into a named database |
| `status` | Show active versions and database file paths |
| `info` | Show active version metadata |
| `ai active [VERSION ...]` | Show or set active version(s); pass multiple to search across all |
| `ai setup [--ai claude\|gemini] [--global] [--mcp-only] [--skills-only]` | Install AI harness |
| `hub list` | List available versions on the configured repository |
| `hub download VERSION` | Download a version and add it to the active set |
| `hub push VERSION [--force]` | Push a version to the repository |
| `hub delete VERSION` | Delete a local version |
| `search QUERY` | Search code + docs + symbols; auto-detects best match |
| `search code QUERY [--top-k N]` | Semantic search over code |
| `search docs QUERY [--top-k N]` | Semantic search over docs |
| `search symbol NAME` | Exact symbol definition lookup |

Global flags: `--verbose` emits structured JSON logs to stderr.

---

## Troubleshooting

**Q: "No active version set"**  
A: Run `qrag hub download <version>` to download one — it is automatically added to the active set.

**Q: "code.db not found" / "docs.db not found"**  
A: Run `qrag hub download <version>` or ask your database preparer to publish one.

**Q: MCP tools not showing in Claude/Gemini**  
A: Re-run `qrag ai setup`, then restart the AI tool.

**Q: MCP server shows "Disconnected"**  
A: Ensure qrag is installed and on PATH, then re-run `qrag ai setup`.

**Q: Search returns no results**  
A: Run `qrag status` to confirm databases exist; check that `QRAG_GITHUB_URL` is set if using `hub` commands.

**Q: "No GitHub authentication"**  
A: Set the `GITHUB_TOKEN` environment variable or run `gh auth login`.

**Q: `build` fails with a missing-dependency error**  
A: You need the build extras. Reinstall with:
```bash
uv tool install --reinstall "git+https://github.com/inegmdev/qrag.git@main[build,cpu]"
```

**Q: How do I check if GPU acceleration is set up correctly before running a full build?**  
A: Run this one-liner — it should list `CUDAExecutionProvider`:
```bash
python -c "import onnxruntime; print(onnxruntime.get_available_providers())"
```
If it's missing, confirm you installed `[gpu]` (not `[cpu]`) and have a working NVIDIA driver — see [GPU Prerequisites](#gpu-prerequisites-skip-if-using-cpu).

**Q: `qrag build --device=cuda` fails with "CUDA requested but onnxruntime has no CUDAExecutionProvider available"**  
A: `onnxruntime-gpu` isn't installed — reinstall with `qrag[build,gpu]`.

**Q: `qrag build --device=cuda` fails with "Failed to initialize the CUDA execution provider" / `libcudart.so` not found**  
A: `qrag[gpu]` installs the CUDA/cuDNN runtime as pip packages and pins `onnxruntime-gpu` to a version compatible with them (`>=1.21,<1.27`) — if you pinned a different `onnxruntime-gpu` version yourself, or have a system-wide CUDA install with a mismatched major version on your library path, that's the likely cause. Reinstall with `uv tool install --reinstall 'qrag[build,gpu]'` and make sure the NVIDIA driver is up to date.

**Q: `qrag build --device=cuda` prints a warning like `[W:onnxruntime:Default, device_discovery.cc:283 GetGpuDevices] Failed to detect devices under "/sys/class/drm/card0": ... Failed to open file: ".../device/vendor"` — is the GPU actually being used?**  
A: This warning is safe to ignore. It comes from onnxruntime's hardware-enumeration/logging pass, which walks `/sys/class/drm/*` to log device info — it's unrelated to whether `CUDAExecutionProvider` actually initializes via the NVIDIA driver/CUDA runtime. The sysfs PCI attributes it's looking for are commonly missing under WSL2 and other virtualized/containerized GPU passthrough setups even when the GPU is fully usable. Confirm the GPU is really in use by checking `nvidia-smi` for a utilization spike during the build, or watching for `[build] device=cuda` in the build's own startup line.

---

## For Developers

See [DEVELOPMENT.md](DEVELOPMENT.md) for local setup, running tests, and contributing.

---

## License

[Your License Here]
