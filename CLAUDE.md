# Claude Code Instructions

## Commit Messages

Do not add `Co-Authored-By` or `Claude-Session` trailers to commit messages.

## Backlog Awareness

A full codebase audit lives at [`docs/BACKLOG.md`](docs/BACKLOG.md). At the start of every session:

1. Read `docs/BACKLOG.md` to understand the current state of known issues.
2. Unless the user directs otherwise, prefer working on higher-severity items first (Critical → High → Medium → Low).
3. When an item is resolved, mark its checkbox `[x]` and add a one-line note describing the fix.
4. When a new bug or improvement is discovered, add it to the appropriate tier in `docs/BACKLOG.md` before or alongside any fix.
