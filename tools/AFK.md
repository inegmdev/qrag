# AFK Script — System Design

Automated task execution for raghub issues using AI agents (Claude, Gemini, OpenCode).

---

## Project Context

raghub is a semantic code/document indexer. Issues in `issues/INDEX.md` have explicit
`Blocked by` dependencies. The AFK script automates working through these issues using AI
agents, handling failures, retries, and parallel execution where dependencies permit.

---

## Decided Design Decisions

### 1. Double Ctrl+C — Graceful Shutdown

**Decision:** First Ctrl+C prints a warning and starts a 5-second confirmation window.
Second Ctrl+C within the window sets a flag to stop after the current iteration finishes.
The main loop checks the flag before starting the next iteration and exits cleanly with
the session footer.

**Rationale:** Prevents accidental aborts mid-task. No orphan processes. Maintains clean
git state. Matches standard UX (Docker, systemd).

**Implementation:**
- Module-level `_abort_after_current = False`
- `signal.signal(signal.SIGINT, _sigint_handler)` registered before main loop
- Handler on first press: print warning, start `threading.Timer(5, _reset_abort)`
- Handler on second press: set `_abort_after_current = True`
- Main loop checks flag before next iteration → break, print footer, `sys.exit(0)`

### 2. Rate Limits — Skipped

**Decision:** No detection or handling for HTTP 429 / rate limit errors.

**Rationale:** User deemed them rare enough not to warrant dedicated logic.

### 3. Session Limits — Detect, Extract RetryDelay, Wait or Abort

**Decision:** Parse both stderr and stdout JSON events for provider-specific session limit
patterns. If Gemini includes a `retryDelay`, wait that duration + 5s buffer and retry.
For Claude and OpenCode (no reset timestamp in output), abort with informative message.

**Provider detection patterns:**

| Provider | stdout JSON signal | stderr text signal | Reset time available? |
|---|---|---|---|
| Claude | `"is_error":true` + `"api_error_status":429` in `type:"result"` events | `"session limit"`, `"rate limited"` | No |
| Gemini | `"status"` != `"success"` in `type:"result"` event | `"quota exceeded"`, `"429"`, `"RESOURCE_EXHAUSTED"` | Sometimes — `retryDelay` in error JSON (e.g. `"retryDelay": "13s"`) |
| OpenCode | `"type":"error"` event | N/A | No |

**Rationale:** Gemini is the only provider that emits a parseable `retryDelay`. Claude uses
a 5-hour rolling window but never includes a reset timestamp in stream-json output. Waiting
hours is impractical for AFK mode — aborting is more useful.

**Implementation:**
- After `proc.wait()`, scan stderr + accumulated JSON events for patterns
- If session limit detected AND `retryDelay` parsed (Gemini): sleep X+5 seconds, retry
- If session limit detected AND no `retryDelay`: abort with message + timestamp

### 4. Idle Timeout — Detect Stdout Silence

**Decision:** Replace `for raw in proc.stdout` (blocks indefinitely) with `select.poll()`
on `proc.stdout.fileno()`. If no data arrives for N seconds, terminate the process.

**Rationale:** Task complexity varies — a complex refactor legitimately takes longer than
a simple edit. Wall-clock timeout would kill long-running but healthy iterations. Idle
timeout only kills when the AI agent stops producing output (stuck/hung).

**Implementation:**
- `select.poll()` with configurable timeout (default: 300s = 5 min silence)
- On timeout: `proc.terminate()`, `proc.wait()`, treat as failure

### 5. Retry on Failure — Up to N Retries with Logging

**Decision:** When an iteration fails (idle timeout, non-zero exit, session limit without
retryDelay), retry up to N times (default: 3, user-configurable). Log each failed attempt
to a session log file with timestamps, error type, and iteration number.

**Rationale:** Transient failures (network blips, API hiccups) should not kill an AFK
session. A few retries absorb flakiness without wasting hours on genuinely broken tasks.

**Implementation:**
- `--max-retries N` CLI flag (default: 3)
- Log file: `.afk-session.log` in CWD
- Log format: `[ISO timestamp] Iteration {n}, Issue {id}, Attempt {a}/{max}, Error: {type} — {detail}`
- After exhausting retries: mark task as failed, proceed to next eligible task

### 6. Task Dependency Graph — Parse issues/INDEX.md

**Decision:** Parse the `Blocked by` column in `issues/INDEX.md` to build a dependency
graph. Use BFS from root issues (no blockers). Before starting a task, verify all its
blockers are marked "Done" in the INDEX.

**Rationale:** The dependency structure already exists in the issue tracker — no new
format needed. The AI prompt currently tells the agent to "find the next incomplete
task" by reading INDEX.md, but this is fragile (AI may misread dependencies). Moving
dependency resolution to the AFK script is more reliable.

**Root assumption:** If `Blocked by` is "—" or empty, the issue has no dependencies and
can be scheduled immediately. If no `Blocked by` column exists at all, assume all tasks
are sequential (safe default).

**Implementation:**
- Parse INDEX.md markdown table → list of `{id, title, type, status, blocked_by: [ids]}`
- BFS queue: start with issues where `blocked_by` is empty
- After each task completes: update its status in INDEX.md, re-scan for newly unblocked tasks
- Skip HITL tasks (they require human interaction)

### 7. Failed Task Pruning

**Decision:** When a task fails after exhausting all retries (default: 3), mark it as
failed in INDEX.md. All tasks that depend on it are blocked indefinitely — their paths
in the dependency tree are pruned. Independent parallel paths continue executing.

**Rationale:** Wasted time on impossible tasks cascades down the dependency tree. Pruning
prevents hours of failed iterations on tasks that can't succeed without their blocker.

**Implementation:**
- After N retries: update INDEX.md status to "Failed", print red marker
- On next BFS pass: skip any issue whose `blocked_by` contains a "Failed" issue
- Continue BFS on remaining independent paths

### 8. Parallel Execution for Independent Tasks

**Decision:** When multiple tasks have all blockers satisfied, execute them concurrently
using separate `subprocess.Popen` instances — one AI agent per task, each with its own
stdout pipe. Limit concurrency to N simultaneous agents (default: 2, configurable).

**Rationale:** Maximizes throughput on independent work. Issues 008 and 009 in raghub
have no blockers — they could run simultaneously instead of sequentially.

**Root assumption:** If the INDEX.md structure doesn't clearly separate parallel paths,
assume sequential execution (safe default). Parallel execution only activates when the
BFS level has multiple unblocked tasks.

**Implementation:**
- After BFS resolves eligible tasks at a level, launch up to N concurrent `run_ai()` calls
- Each runs in its own thread with its own `proc` handle
- Shared state: task statuses updated via thread-safe dict + INDEX.md writes
- `--max-concurrent N` CLI flag (default: 2)

---

## Visualization — Terminal Tree

Real-time tree rendering via ANSI escape codes in a dedicated render thread.

```
  raghub AFK session
  ┌─────────────────────────────────────────┐
  │                                          │
  │  001 ● ──→ 002 ● ──→ 004 ◐ ──→ 006 ◌  │
  │                │                       │
  │                └──→ 005 ● ──→ 007 ○   │
  │                                        │
  │  003 ● ─────→ 008 ◐   009 ○          │
  │                       010 ○            │
  │                                        │
  └─────────────────────────────────────────┘
  Iteration: 7  |  Claude (haiku)  |  00:23:45
```

**Legend:**
- `○` Open (gray)
- `◐` In progress — blinking yellow (ANSI blink or periodic redraw)
- `●` Done (green)
- `✖` Failed (red)
- `◌` Blocked (dim gray, strikethrough if blocked by failed task)

**Implementation:**
- Dedicated render thread polls task state every 1 second
- Redraws tree using ANSI cursor movement (`\033[A`, `\033[J`)
- No external dependencies (no `rich`, no `ncurses`) — raw ANSI escape codes
- Tree layout computed from dependency graph (topological sort → indentation)

---

## Open Questions

| Item | Options | Notes |
|---|---|---|
| **Config format** | CLI flags only / YAML config file / TOML config file | CLI flags are simpler; config file allows reuse across sessions |
| **JSON event parsing** | Structured (parse `type:"error"` from stdout) / Text-only (scan stderr) | Structured is more reliable but adds code for each provider's event schema |
| **Log file location** | CWD `.afk-session.log` / `~/.raghub/afk-session.log` | CWD keeps logs per-project; home dir keeps them centralized |
| **Concurrency limit default** | 1 (safe) / 2 (balanced) / 4 (aggressive) | Higher concurrency = faster but more API usage and harder to debug |
| **TUI refresh rate** | 500ms / 1s / 2s | Faster = smoother animation but more terminal overhead |
| **Dynamic task generation** | INDEX.md only (static) / AI can discover sub-tasks (dynamic) | Static is simpler and more predictable; dynamic adds complexity |
| **Session persistence** | No (restart from scratch) / Yes (resume from last state) | Resume requires checkpointing task state to disk |

---

## Proposed CLI Interface

```bash
afk [OPTIONS]

Options:
  --ai claude|gemini|opencode     AI agent (default: auto-detect)
  --max-retries N                 Max retries per task (default: 3)
  --idle-timeout SECONDS          Kill if no stdout for N seconds (default: 300)
  --max-concurrent N              Max parallel tasks (default: 2)
  --max-iterations N              Stop after N iterations (default: unlimited)
  --dry-run                       Print task plan without executing
  --log FILE                      Log file path (default: .afk-session.log)
  --prompt-file FILE              Custom prompt template
```

---

## Implementation Phases (Proposed Priority)

### Phase 1: Core Reliability
1. Double Ctrl+C handler
2. Idle timeout with `select.poll()`
3. Retry on failure with log file
4. `argparse` CLI interface

### Phase 2: Task Graph
5. Parse `issues/INDEX.md` → dependency graph
6. BFS scheduling (sequential, skip HITL tasks)
7. Update INDEX.md status after each task
8. Failed task pruning

### Phase 3: Parallel Execution
9. Concurrent `subprocess.Popen` per task (up to N)
10. Thread-safe state management
11. Per-task stdout routing (prefix with issue ID)

### Phase 4: Visualization
12. Tree layout algorithm (topological sort → ASCII tree)
13. ANSI render loop (dedicated thread, 1s refresh)
14. Circle legend with colors

### Phase 5: Polish
15. Session persistence (checkpoint to disk, `--resume`)
16. Dynamic box width for banner/footer
17. Symlink-safe CWD display
18. Session log rotation
