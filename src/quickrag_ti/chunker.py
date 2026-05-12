"""Simple regex-based C function extractor (no tree-sitter dependency for slice 001)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CodeChunk:
    symbol_name: str
    file_path: str
    line_start: int
    line_end: int
    code_text: str
    chunk_type: str  # "function", "struct", "macro"


# Matches C function definitions: return_type name(...) { ... }
# Handles multi-line bodies by brace counting.
_FUNC_SIG = re.compile(
    r"^(?:(?:static|inline|extern|volatile|const)\s+)*"
    r"[\w\s\*]+\s+(\w+)\s*\([^)]*\)\s*$"
)


def _extract_functions_from_c(source: str, file_path: str) -> list[CodeChunk]:
    lines = source.splitlines()
    chunks: list[CodeChunk] = []
    i = 0
    while i < len(lines):
        # Look for a line that looks like a function signature (ends without semicolon/brace)
        line = lines[i].rstrip()
        m = _FUNC_SIG.match(line)
        if m:
            func_name = m.group(1)
            sig_start = i + 1  # 1-based
            # Find opening brace
            j = i
            while j < len(lines) and "{" not in lines[j]:
                j += 1
            if j >= len(lines):
                i += 1
                continue
            # Count braces to find closing
            depth = 0
            body_start = j
            k = j
            while k < len(lines):
                depth += lines[k].count("{") - lines[k].count("}")
                if depth == 0:
                    break
                k += 1
            if depth != 0:
                i += 1
                continue
            func_lines = lines[i : k + 1]
            # Pull docstring comment above if present
            comment_start = i
            while comment_start > 0 and (
                lines[comment_start - 1].strip().startswith("*")
                or lines[comment_start - 1].strip().startswith("/*")
                or lines[comment_start - 1].strip().startswith("//")
            ):
                comment_start -= 1
            full_text = "\n".join(lines[comment_start : k + 1])
            chunks.append(
                CodeChunk(
                    symbol_name=func_name,
                    file_path=file_path,
                    line_start=comment_start + 1,
                    line_end=k + 1,
                    code_text=full_text,
                    chunk_type="function",
                )
            )
            i = k + 1
        else:
            i += 1
    return chunks


def chunk_c_file(path: Path) -> list[CodeChunk]:
    source = path.read_text(encoding="utf-8", errors="replace")
    return _extract_functions_from_c(source, str(path))
