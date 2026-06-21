"""Tree-sitter C/C++ parser: extracts functions, structs, and macros."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter_c as tsc
import tree_sitter_cpp as tscpp
from tree_sitter import Language, Parser

C_LANGUAGE = Language(tsc.language())
CPP_LANGUAGE = Language(tscpp.language())
_c_parser = Parser(C_LANGUAGE)
_cpp_parser = Parser(CPP_LANGUAGE)

MAX_TOKENS = 512
OVERLAP_TOKENS = 64


@dataclass
class CodeChunk:
    symbol_name: str
    file_path: str
    line_start: int
    line_end: int
    code_text: str
    chunk_type: str  # "function", "struct", "macro"


def _token_count(text: str) -> int:
    return len(text.split())


def _split_large_chunk(chunk: CodeChunk) -> list[CodeChunk]:
    """Split oversized function into overlapping sub-chunks by lines."""
    lines = chunk.code_text.splitlines()
    sub_chunks: list[CodeChunk] = []
    i = 0
    idx = 0
    while i < len(lines):
        window: list[str] = []
        token_count = 0
        j = i
        while j < len(lines) and token_count < MAX_TOKENS:
            window.append(lines[j])
            token_count += len(lines[j].split())
            j += 1
        text = "\n".join(window)
        sub_chunks.append(CodeChunk(
            symbol_name=f"{chunk.symbol_name}#{idx}",
            file_path=chunk.file_path,
            line_start=chunk.line_start + i,
            line_end=chunk.line_start + j - 1,
            code_text=text,
            chunk_type=chunk.chunk_type,
        ))
        idx += 1
        # If we consumed to end-of-function without hitting the token cap, stop.
        if j >= len(lines):
            break
        # Advance by (window size - overlap): step back from j to leave OVERLAP_TOKENS behind.
        overlap_tokens = 0
        step = j - 1
        while step > i and overlap_tokens < OVERLAP_TOKENS:
            overlap_tokens += len(lines[step].split())
            step -= 1
        new_i = step + 1
        if new_i <= i:
            new_i = i + 1  # always advance at least one line
        i = new_i
    return sub_chunks


def _get_func_name(node) -> str | None:
    """Extract function name from a function_definition node."""
    decl = node.child_by_field_name("declarator")
    while decl is not None and decl.type not in ("function_declarator", "identifier"):
        inner = decl.child_by_field_name("declarator")
        if inner is None:
            break
        decl = inner
    if decl is None:
        return None
    if decl.type == "function_declarator":
        name_node = decl.child_by_field_name("declarator")
        if name_node is not None:
            return name_node.text.decode(errors="replace")
    elif decl.type == "identifier":
        return decl.text.decode(errors="replace")
    return None


def _extract_chunks(source: bytes, file_path: str, parser: Parser) -> list[CodeChunk]:
    tree = parser.parse(source)
    lines = source.decode(errors="replace").splitlines()
    chunks: list[CodeChunk] = []

    def visit(node):
        if node.type == "function_definition":
            name = _get_func_name(node)
            if name:
                r0, r1 = node.start_point[0], node.end_point[0]
                text = "\n".join(lines[r0 : r1 + 1])
                chunk = CodeChunk(
                    symbol_name=name,
                    file_path=file_path,
                    line_start=r0 + 1,
                    line_end=r1 + 1,
                    code_text=text,
                    chunk_type="function",
                )
                if _token_count(text) > MAX_TOKENS:
                    chunks.extend(_split_large_chunk(chunk))
                else:
                    chunks.append(chunk)
            return  # don't recurse into nested functions

        if node.type in ("struct_specifier", "union_specifier"):
            body = node.child_by_field_name("body")
            if body is None:
                for child in node.children:
                    visit(child)
                return
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode(errors="replace") if name_node else "(anonymous)"
            r0, r1 = node.start_point[0], node.end_point[0]
            text = "\n".join(lines[r0 : r1 + 1])
            chunks.append(CodeChunk(
                symbol_name=name,
                file_path=file_path,
                line_start=r0 + 1,
                line_end=r1 + 1,
                code_text=text,
                chunk_type="struct",
            ))
            return

        if node.type == "type_definition":
            # typedef struct { ... } Name_t;
            struct_node = None
            typedef_name = None
            for child in node.children:
                if child.type in ("struct_specifier", "union_specifier"):
                    struct_node = child
                elif child.type == "type_identifier":
                    typedef_name = child.text.decode(errors="replace")
            if struct_node is not None and struct_node.child_by_field_name("body") is not None:
                name = typedef_name or "(anonymous)"
                r0, r1 = node.start_point[0], node.end_point[0]
                text = "\n".join(lines[r0 : r1 + 1])
                chunks.append(CodeChunk(
                    symbol_name=name,
                    file_path=file_path,
                    line_start=r0 + 1,
                    line_end=r1 + 1,
                    code_text=text,
                    chunk_type="struct",
                ))
                return

        if node.type in ("preproc_def", "preproc_function_def"):
            name_node = node.child_by_field_name("name")
            if name_node is None:
                for child in node.children:
                    if child.type == "identifier":
                        name_node = child
                        break
            name = name_node.text.decode(errors="replace") if name_node else "(macro)"
            r0, r1 = node.start_point[0], node.end_point[0]
            text = "\n".join(lines[r0 : r1 + 1])
            chunks.append(CodeChunk(
                symbol_name=name,
                file_path=file_path,
                line_start=r0 + 1,
                line_end=r1 + 1,
                code_text=text,
                chunk_type="macro",
            ))
            return

        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return chunks


def chunk_code_file(path: Path) -> list[CodeChunk]:
    source = path.read_bytes()
    parser = _cpp_parser if path.suffix.lower() == ".cpp" else _c_parser
    return _extract_chunks(source, str(path), parser)
