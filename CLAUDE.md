# Claude Code Instructions

## Commit Messages

Do not add `Co-Authored-By` or `Claude-Session` trailers to commit messages.

## Session Start

At the start of every session:

1. Read `MEMORY.md` — the primary entry point for understanding the project, product, architecture, and accumulated decisions.
2. Read `docs/BACKLOG.md` — authoritative list of known bugs and improvements.
3. Unless the user directs otherwise, prefer working on higher-severity backlog items first (Critical → High → Medium → Low).

## Backlog Awareness

4. When an item is resolved, mark its checkbox `[x]` in `docs/BACKLOG.md` and add a one-line note describing the fix.
5. When a new bug or improvement is discovered, add it to the appropriate tier in `docs/BACKLOG.md` before or alongside any fix.
6. Before ending a session where significant design decisions or context accumulated, update `MEMORY.md` so future sessions start informed.
