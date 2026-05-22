# 009 — Incremental database update (folder diff)

**Type:** AFK  
**Status:** Open  
**Blocked by:** None — can start immediately

---

## What to build

Make `rhub prepare -i <dir> -o <name>` **idempotent and diff-aware**: on re-run with the same `-o`, raghub compares the current input folder contents against a stored file manifest and applies only the delta (add new files, re-embed modified files, delete removed files). Input folder and database must always be an identical match.

## Design decisions

- **Manifest storage:** a `file_manifest` table inside each DB (`code.db` and `docs.db`). Keeps everything self-contained in one file per database.
- **Path representation:** paths stored **relative to each `-i` root** (not absolute). The `-i` roots themselves are stored in the manifest for change-detection, but relative paths are the stable identity key.
- **Root change handling:** if the `-i` roots on re-run differ from those stored in the manifest, raghub prints a hard error and exits. The user must pass `--force` to proceed, which triggers a full rebuild (wipe manifest + DB, start fresh).

## Manifest schema

```sql
CREATE TABLE file_manifest (
    rel_path   TEXT NOT NULL,
    input_root TEXT NOT NULL,
    mtime      REAL NOT NULL,
    sha256     TEXT NOT NULL,
    PRIMARY KEY (rel_path, input_root)
);
```

## Delta logic

1. Walk all current `-i` directories → build `{(root, rel_path): (mtime, sha256)}` map
2. Load existing manifest from DB
3. **Deleted** (in manifest, not in walk) → `DELETE` chunks/sections + manifest row
4. **Modified** (in both, mtime or sha256 changed) → re-chunk, re-embed, upsert chunks + update manifest row
5. **Added** (in walk, not in manifest) → chunk, embed, insert + add manifest row
6. **Unchanged** → skip entirely

mtime is checked first (fast); sha256 computed only when mtime differs.

## Acceptance criteria

- [ ] `file_manifest` table created in `code.db` and `docs.db` on first `prepare` run
- [ ] Re-run with no changes → zero DB writes, prints `[prepare] nothing changed`
- [ ] Re-run after adding a file → only new file embedded and inserted
- [ ] Re-run after modifying a file → only that file re-embedded (old chunks deleted, new inserted)
- [ ] Re-run after deleting a file → its chunks removed from DB and manifest
- [ ] Re-run after deleting a whole subfolder → all affected chunks removed correctly
- [ ] Re-run with different `-i` roots (no `--force`) → hard error with clear message, zero DB writes
- [ ] Re-run with `--force` → full rebuild: manifest wiped, DB rebuilt from scratch
- [ ] `--force` is documented in `--help` output

## Updates

<!-- Append timestamped notes here as work progresses -->
