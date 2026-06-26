"""Multi-language tree-sitter parser: extracts named code constructs from source files."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

from tree_sitter_language_pack import get_parser as _ts_get_parser

MAX_TOKENS = 512
OVERLAP_TOKENS = 64


@dataclass
class CodeChunk:
    symbol_name: str
    file_path: str
    line_start: int
    line_end: int
    code_text: str
    chunk_type: str   # function | class | struct | interface | enum | macro | type_alias | module | constant
    language: str     # canonical language name, e.g. "c", "rust", "cmake"
    parent_name: str = ""   # enclosing function/class/namespace name, empty if top-level
    call_depth: int = 0     # 0 = top-level, 1+ = nested inside a recursible block
    chunk_index: int = 0    # 0 for unsplit chunks; 0,1,2,… for sub-chunks of large symbols


@dataclass
class _Rule:
    """Maps one or more AST node types to a chunk_type with a name extractor."""
    node_types: frozenset[str]
    chunk_type: str
    extract_name: Callable          # (node) -> str | None; None = skip but still recurse
    recurse: bool = True            # recurse into children after successfully extracting?


@dataclass
class _LangConfig:
    name: str       # canonical name stored in DB ("c", "rust", "cmake", …)
    ts_name: str    # name passed to tree-sitter-language-pack
    rules: list[_Rule]


# ---------------------------------------------------------------------------
# Name extractors
# ---------------------------------------------------------------------------

def _name_field(node) -> str | None:
    """Generic: 'name' field → first identifier child → first 64 chars of text."""
    n = node.child_by_field_name("name")
    if n:
        return n.text.decode(errors="replace")
    for c in node.children:
        if c.type == "identifier":
            return c.text.decode(errors="replace")
    txt = node.text.decode(errors="replace")[:64].strip()
    return txt or None


def _c_func_name(node) -> str | None:
    """Walk C/C++ declarator chain to find the function name."""
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
        return name_node.text.decode(errors="replace") if name_node else None
    if decl.type == "identifier":
        return decl.text.decode(errors="replace")
    return None


def _c_struct_name(node) -> str | None:
    """Only extract struct/union if it has a body (skip forward declarations)."""
    if node.child_by_field_name("body") is None:
        return None  # forward declaration — skip but still recurse
    name_node = node.child_by_field_name("name")
    return name_node.text.decode(errors="replace") if name_node else "(anonymous)"


def _c_typedef_name(node) -> str | None:
    """Only extract typedef if it wraps a struct/union with a body."""
    struct_node = None
    typedef_name = None
    for child in node.children:
        if child.type in ("struct_specifier", "union_specifier"):
            struct_node = child
        elif child.type == "type_identifier":
            typedef_name = child.text.decode(errors="replace")
    if struct_node is None or struct_node.child_by_field_name("body") is None:
        return None
    return typedef_name or "(anonymous)"


_CMAKE_BUILD_CMDS: frozenset[str] = frozenset({
    "add_executable", "add_library", "add_test", "add_subdirectory",
    "option", "find_package", "target_sources", "target_link_libraries",
    "target_include_directories", "target_compile_definitions",
    "target_compile_options", "install", "project", "cmake_minimum_required",
    "include", "set_property", "add_custom_target", "add_custom_command",
    "enable_testing", "add_definitions", "set",
})


def _cmake_cmd_name(node) -> str | None:
    """Return '<command>(<first_arg>)' for build-relevant cmake commands, else None."""
    id_node = None
    for c in node.children:
        if c.type == "identifier":
            id_node = c
            break
    if id_node is None:
        return None
    cmd = id_node.text.decode(errors="replace").lower()
    if cmd not in _CMAKE_BUILD_CMDS:
        return None
    args = [
        c for c in node.children
        if c.type in ("argument", "unquoted_argument", "quoted_argument", "bracket_argument")
    ]
    first = args[0].text.decode(errors="replace").strip('"') if args else ""
    return f"{cmd}({first})" if first else cmd


def _make_target_name(node) -> str | None:
    """Extract make rule target name."""
    targets = node.child_by_field_name("targets")
    if targets:
        return targets.text.decode(errors="replace").strip()
    for c in node.children:
        if c.type not in (":", "\n", "recipe", "prerequisites"):
            txt = c.text.decode(errors="replace").strip()
            if txt and not txt.startswith("#"):
                return txt
    return None


def _toml_table_name(node) -> str | None:
    """Extract TOML section header as name."""
    for c in node.children:
        if c.type in ("dotted_key", "key", "quoted_key", "bare_key"):
            return c.text.decode(errors="replace").strip("[]")
    return _name_field(node)


def _json_key_name(node) -> str | None:
    """Extract JSON object key string."""
    key = node.child_by_field_name("key")
    if key:
        return key.text.decode(errors="replace").strip('"\'')
    return None


def _xml_elem_name(node) -> str | None:
    """Extract XML element tag name for recognized build-relevant elements."""
    _BUILD_TAGS = frozenset({
        "artifactId", "groupId", "version", "dependency", "plugin",
        "module", "profile", "execution", "goal", "dependencies",
        "plugins", "modules", "profiles", "properties", "build",
    })
    start_tag = node.child_by_field_name("start_tag")
    if start_tag is None:
        for c in node.children:
            if c.type == "start_tag":
                start_tag = c
                break
    if start_tag is None:
        return None
    for c in start_tag.children:
        if c.type == "tag_name":
            tag = c.text.decode(errors="replace")
            return tag if tag in _BUILD_TAGS else None
    return None


def _go_type_name(node) -> str | None:
    """Extract Go type name from type_declaration → type_spec."""
    for c in node.children:
        if c.type == "type_spec":
            name_node = c.child_by_field_name("name")
            if name_node:
                return name_node.text.decode(errors="replace")
    return _name_field(node)


_N = _name_field

# ---------------------------------------------------------------------------
# Language rule sets
# ---------------------------------------------------------------------------

_C_RULES: list[_Rule] = [
    _Rule(frozenset({"function_definition"}),                         "function",   _c_func_name,    recurse=False),
    _Rule(frozenset({"struct_specifier", "union_specifier"}),         "struct",     _c_struct_name,  recurse=False),
    _Rule(frozenset({"enum_specifier"}),                              "enum",       _N,              recurse=False),
    _Rule(frozenset({"type_definition"}),                             "struct",     _c_typedef_name, recurse=False),
    _Rule(frozenset({"preproc_def", "preproc_function_def"}),         "macro",      _N,              recurse=False),
]

_CPP_RULES: list[_Rule] = _C_RULES + [
    _Rule(frozenset({"class_specifier"}),                             "class",      _N,              recurse=False),
    _Rule(frozenset({"namespace_definition"}),                        "module",     _N,              recurse=True),
]

_RUST_RULES: list[_Rule] = [
    _Rule(frozenset({"function_item"}),                               "function",   _N, recurse=False),
    _Rule(frozenset({"struct_item"}),                                 "struct",     _N, recurse=False),
    _Rule(frozenset({"enum_item"}),                                   "enum",       _N, recurse=False),
    _Rule(frozenset({"impl_item"}),                                   "class",      _N, recurse=True),
    _Rule(frozenset({"trait_item"}),                                  "interface",  _N, recurse=False),
    _Rule(frozenset({"type_item"}),                                   "type_alias", _N, recurse=False),
    _Rule(frozenset({"macro_definition", "macro_rules"}),             "macro",      _N, recurse=False),
    _Rule(frozenset({"mod_item"}),                                    "module",     _N, recurse=True),
    _Rule(frozenset({"const_item", "static_item"}),                   "constant",   _N, recurse=False),
]

_PYTHON_RULES: list[_Rule] = [
    _Rule(frozenset({"function_definition", "async_function_definition"}), "function", _N, recurse=False),
    _Rule(frozenset({"class_definition"}),                                 "class",    _N, recurse=True),
]

_GO_RULES: list[_Rule] = [
    _Rule(frozenset({"function_declaration", "method_declaration"}),  "function",   _N,              recurse=False),
    _Rule(frozenset({"type_declaration"}),                            "struct",     _go_type_name,   recurse=False),
    _Rule(frozenset({"const_declaration", "var_declaration"}),        "constant",   _N,              recurse=False),
]

_JS_RULES: list[_Rule] = [
    _Rule(frozenset({"function_declaration", "generator_function_declaration"}), "function", _N, recurse=False),
    _Rule(frozenset({"method_definition"}),                           "function",   _N, recurse=False),
    _Rule(frozenset({"class_declaration"}),                           "class",      _N, recurse=True),
    _Rule(frozenset({"lexical_declaration", "variable_declaration"}), "constant",   _N, recurse=False),
]

_TS_RULES: list[_Rule] = _JS_RULES + [
    _Rule(frozenset({"interface_declaration"}),                       "interface",  _N, recurse=False),
    _Rule(frozenset({"type_alias_declaration"}),                      "type_alias", _N, recurse=False),
    _Rule(frozenset({"enum_declaration"}),                            "enum",       _N, recurse=False),
]

_JAVA_RULES: list[_Rule] = [
    _Rule(frozenset({"method_declaration", "constructor_declaration"}),           "function",  _N, recurse=False),
    _Rule(frozenset({"class_declaration", "record_declaration"}),                 "class",     _N, recurse=True),
    _Rule(frozenset({"interface_declaration", "annotation_type_declaration"}),    "interface", _N, recurse=False),
    _Rule(frozenset({"enum_declaration"}),                                        "enum",      _N, recurse=False),
]

_CSHARP_RULES: list[_Rule] = [
    _Rule(frozenset({"method_declaration", "constructor_declaration", "local_function_statement"}), "function",  _N, recurse=False),
    _Rule(frozenset({"class_declaration", "record_declaration"}),                                    "class",     _N, recurse=True),
    _Rule(frozenset({"interface_declaration"}),                                                      "interface", _N, recurse=False),
    _Rule(frozenset({"enum_declaration"}),                                                           "enum",      _N, recurse=False),
    _Rule(frozenset({"struct_declaration"}),                                                         "struct",    _N, recurse=False),
    _Rule(frozenset({"namespace_declaration"}),                                                      "module",    _N, recurse=True),
]

_RUBY_RULES: list[_Rule] = [
    _Rule(frozenset({"method", "singleton_method"}),                  "function",  _N, recurse=False),
    _Rule(frozenset({"class"}),                                       "class",     _N, recurse=True),
    _Rule(frozenset({"module"}),                                      "module",    _N, recurse=True),
]

_SWIFT_RULES: list[_Rule] = [
    _Rule(frozenset({"function_declaration"}),                        "function",  _N, recurse=False),
    _Rule(frozenset({"class_declaration"}),                           "class",     _N, recurse=True),
    _Rule(frozenset({"struct_declaration"}),                          "struct",    _N, recurse=False),
    _Rule(frozenset({"enum_declaration"}),                            "enum",      _N, recurse=False),
    _Rule(frozenset({"protocol_declaration"}),                        "interface", _N, recurse=False),
    _Rule(frozenset({"extension_declaration"}),                       "module",    _N, recurse=True),
]

_KOTLIN_RULES: list[_Rule] = [
    _Rule(frozenset({"function_declaration"}),                        "function",  _N, recurse=False),
    _Rule(frozenset({"class_declaration", "object_declaration"}),     "class",     _N, recurse=True),
    _Rule(frozenset({"interface_declaration", "enum_class_declaration"}), "interface", _N, recurse=False),
]

_SCALA_RULES: list[_Rule] = [
    _Rule(frozenset({"function_definition", "function_declaration"}), "function",  _N, recurse=False),
    _Rule(frozenset({"class_definition", "object_definition", "case_class_definition"}), "class", _N, recurse=True),
    _Rule(frozenset({"trait_definition"}),                            "interface", _N, recurse=False),
]

_LUA_RULES: list[_Rule] = [
    _Rule(frozenset({"function_declaration", "local_function"}),      "function",  _N, recurse=False),
]

_PHP_RULES: list[_Rule] = [
    _Rule(frozenset({"function_definition"}),                         "function",  _N, recurse=False),
    _Rule(frozenset({"method_declaration", "constructor_declaration"}), "function", _N, recurse=False),
    _Rule(frozenset({"class_declaration"}),                           "class",     _N, recurse=True),
    _Rule(frozenset({"interface_declaration"}),                       "interface", _N, recurse=False),
    _Rule(frozenset({"enum_declaration"}),                            "enum",      _N, recurse=False),
]

_BASH_RULES: list[_Rule] = [
    _Rule(frozenset({"function_definition"}),                         "function",  _N, recurse=False),
]

_ZIG_RULES: list[_Rule] = [
    _Rule(frozenset({"fn_decl", "fn_proto"}),                         "function",  _N, recurse=False),
    _Rule(frozenset({"container_decl", "container_declaration"}),     "struct",    _N, recurse=False),
]

_ELIXIR_RULES: list[_Rule] = [
    _Rule(frozenset({"call"}),                                        "function",  _N, recurse=True),
]

_HASKELL_RULES: list[_Rule] = [
    _Rule(frozenset({"function", "bind"}),                            "function",  _N, recurse=False),
    _Rule(frozenset({"data_declaration"}),                            "struct",    _N, recurse=False),
    _Rule(frozenset({"class_declaration"}),                           "interface", _N, recurse=False),
    _Rule(frozenset({"newtype_declaration"}),                         "type_alias", _N, recurse=False),
]

_OCAML_RULES: list[_Rule] = [
    _Rule(frozenset({"let_binding"}),                                 "function",  _N, recurse=False),
    _Rule(frozenset({"type_binding"}),                                "struct",    _N, recurse=False),
    _Rule(frozenset({"module_binding"}),                              "module",    _N, recurse=True),
]

_ERLANG_RULES: list[_Rule] = [
    _Rule(frozenset({"function"}),                                    "function",  _N, recurse=False),
    _Rule(frozenset({"record_definition"}),                           "struct",    _N, recurse=False),
    _Rule(frozenset({"module_attribute"}),                            "module",    _N, recurse=False),
]

_DART_RULES: list[_Rule] = [
    _Rule(frozenset({"function_signature", "method_signature"}),      "function",  _N, recurse=False),
    _Rule(frozenset({"class_definition"}),                            "class",     _N, recurse=True),
    _Rule(frozenset({"mixin_declaration"}),                           "interface", _N, recurse=False),
    _Rule(frozenset({"enum_declaration"}),                            "enum",      _N, recurse=False),
]

_R_RULES: list[_Rule] = [
    _Rule(frozenset({"function_definition"}),                         "function",  _N, recurse=False),
]

_FORTRAN_RULES: list[_Rule] = [
    _Rule(frozenset({"subroutine_subprogram", "function_subprogram"}), "function", _N, recurse=False),
    _Rule(frozenset({"module"}),                                       "module",   _N, recurse=True),
    _Rule(frozenset({"derived_type_definition"}),                      "struct",   _N, recurse=False),
]

_VERILOG_RULES: list[_Rule] = [
    _Rule(frozenset({"module_declaration"}),                          "module",    _N, recurse=True),
    _Rule(frozenset({"function_declaration", "task_declaration"}),    "function",  _N, recurse=False),
]

_VHDL_RULES: list[_Rule] = [
    _Rule(frozenset({"entity_declaration"}),                          "module",    _N, recurse=False),
    _Rule(frozenset({"architecture_body"}),                           "class",     _N, recurse=True),
    _Rule(frozenset({"package_declaration"}),                         "module",    _N, recurse=False),
    _Rule(frozenset({"subprogram_body"}),                             "function",  _N, recurse=False),
]

# Build systems
_CMAKE_RULES: list[_Rule] = [
    _Rule(frozenset({"function_def", "function_definition"}),         "function",  _N,              recurse=False),
    _Rule(frozenset({"macro_def", "macro_definition"}),               "macro",     _N,              recurse=False),
    _Rule(frozenset({"normal_command"}),                              "constant",  _cmake_cmd_name, recurse=False),
]

_MAKE_RULES: list[_Rule] = [
    _Rule(frozenset({"rule"}),                                        "function",  _make_target_name, recurse=False),
]

_TOML_RULES: list[_Rule] = [
    _Rule(frozenset({"table", "table_array_element"}),                "struct",    _toml_table_name, recurse=False),
]

_JSON_RULES: list[_Rule] = [
    _Rule(frozenset({"pair"}),                                        "constant",  _json_key_name,   recurse=False),
]

_GOMOD_RULES: list[_Rule] = [
    _Rule(frozenset({"module_directive"}),                            "module",    _N, recurse=False),
    _Rule(frozenset({"require_directive", "require_spec"}),           "constant",  _N, recurse=False),
    _Rule(frozenset({"replace_directive"}),                           "constant",  _N, recurse=False),
]

_GRADLE_RULES: list[_Rule] = [
    _Rule(frozenset({"method_declaration", "function_declaration"}),  "function",  _N, recurse=False),
    _Rule(frozenset({"class_declaration"}),                           "class",     _N, recurse=True),
]

_XML_RULES: list[_Rule] = [
    _Rule(frozenset({"element"}),                                     "struct",    _xml_elem_name, recurse=True),
]

# ---------------------------------------------------------------------------
# Language registry
# ---------------------------------------------------------------------------

def _lc(name: str, ts: str, rules: list[_Rule]) -> _LangConfig:
    return _LangConfig(name, ts, rules)


_cmake_lc  = _lc("cmake",  "cmake",      _CMAKE_RULES)
_make_lc   = _lc("make",   "make",       _MAKE_RULES)
_toml_lc   = _lc("toml",   "toml",       _TOML_RULES)
_json_lc   = _lc("json",   "json",       _JSON_RULES)
_gomod_lc  = _lc("gomod",  "gomod",      _GOMOD_RULES)
_gradle_lc = _lc("gradle", "groovy",     _GRADLE_RULES)
_xml_lc    = _lc("xml",    "xml",        _XML_RULES)

# Extension → LanguageConfig (all files of this extension are indexed)
_EXT_REGISTRY: dict[str, _LangConfig] = {
    # C / C++
    ".c":    _lc("c",             "c",             _C_RULES),
    ".h":    _lc("c",             "c",             _C_RULES),
    ".cpp":  _lc("cpp",           "cpp",           _CPP_RULES),
    ".cc":   _lc("cpp",           "cpp",           _CPP_RULES),
    ".cxx":  _lc("cpp",           "cpp",           _CPP_RULES),
    ".hpp":  _lc("cpp",           "cpp",           _CPP_RULES),
    ".hh":   _lc("cpp",           "cpp",           _CPP_RULES),
    ".hxx":  _lc("cpp",           "cpp",           _CPP_RULES),
    # Rust
    ".rs":   _lc("rust",          "rust",          _RUST_RULES),
    # Python
    ".py":   _lc("python",        "python",        _PYTHON_RULES),
    # Go
    ".go":   _lc("go",            "go",            _GO_RULES),
    # JavaScript
    ".js":   _lc("javascript",    "javascript",    _JS_RULES),
    ".mjs":  _lc("javascript",    "javascript",    _JS_RULES),
    ".cjs":  _lc("javascript",    "javascript",    _JS_RULES),
    # TypeScript
    ".ts":   _lc("typescript",    "typescript",    _TS_RULES),
    ".tsx":  _lc("typescript",    "tsx",           _TS_RULES),
    ".mts":  _lc("typescript",    "typescript",    _TS_RULES),
    ".cts":  _lc("typescript",    "typescript",    _TS_RULES),
    # Java
    ".java": _lc("java",          "java",          _JAVA_RULES),
    # C#
    ".cs":   _lc("csharp",        "c_sharp",       _CSHARP_RULES),
    # Ruby
    ".rb":   _lc("ruby",          "ruby",          _RUBY_RULES),
    # Swift
    ".swift":_lc("swift",         "swift",         _SWIFT_RULES),
    # Kotlin
    ".kt":   _lc("kotlin",        "kotlin",        _KOTLIN_RULES),
    ".kts":  _lc("kotlin",        "kotlin",        _KOTLIN_RULES),
    # Scala
    ".scala":_lc("scala",         "scala",         _SCALA_RULES),
    # Lua
    ".lua":  _lc("lua",           "lua",           _LUA_RULES),
    # PHP
    ".php":  _lc("php",           "php",           _PHP_RULES),
    # Shell
    ".sh":   _lc("bash",          "bash",          _BASH_RULES),
    ".bash": _lc("bash",          "bash",          _BASH_RULES),
    # Zig
    ".zig":  _lc("zig",           "zig",           _ZIG_RULES),
    # Elixir
    ".ex":   _lc("elixir",        "elixir",        _ELIXIR_RULES),
    ".exs":  _lc("elixir",        "elixir",        _ELIXIR_RULES),
    # Haskell
    ".hs":   _lc("haskell",       "haskell",       _HASKELL_RULES),
    ".lhs":  _lc("haskell",       "haskell",       _HASKELL_RULES),
    # OCaml
    ".ml":   _lc("ocaml",         "ocaml",         _OCAML_RULES),
    ".mli":  _lc("ocaml",         "ocaml",         _OCAML_RULES),
    # Erlang
    ".erl":  _lc("erlang",        "erlang",        _ERLANG_RULES),
    ".hrl":  _lc("erlang",        "erlang",        _ERLANG_RULES),
    # Dart
    ".dart": _lc("dart",          "dart",          _DART_RULES),
    # R
    ".r":    _lc("r",             "r",             _R_RULES),
    ".R":    _lc("r",             "r",             _R_RULES),
    # Fortran
    ".f90":  _lc("fortran",       "fortran",       _FORTRAN_RULES),
    ".f95":  _lc("fortran",       "fortran",       _FORTRAN_RULES),
    ".f03":  _lc("fortran",       "fortran",       _FORTRAN_RULES),
    ".f08":  _lc("fortran",       "fortran",       _FORTRAN_RULES),
    ".for":  _lc("fortran",       "fortran",       _FORTRAN_RULES),
    ".f":    _lc("fortran",       "fortran",       _FORTRAN_RULES),
    # Verilog / SystemVerilog
    ".v":    _lc("verilog",       "verilog",       _VERILOG_RULES),
    ".sv":   _lc("systemverilog", "verilog",       _VERILOG_RULES),
    ".svh":  _lc("systemverilog", "verilog",       _VERILOG_RULES),
    # VHDL
    ".vhd":  _lc("vhdl",         "vhdl",          _VHDL_RULES),
    ".vhdl": _lc("vhdl",         "vhdl",          _VHDL_RULES),
    # Build files by extension
    ".cmake":  _cmake_lc,
    ".mk":     _make_lc,
    ".mak":    _make_lc,
    ".toml":   _toml_lc,
    ".gradle": _gradle_lc,
}

# Exact filename → LanguageConfig (build system files without distinctive extensions)
_FILENAME_REGISTRY: dict[str, _LangConfig] = {
    "CMakeLists.txt":   _cmake_lc,
    "Makefile":         _make_lc,
    "makefile":         _make_lc,
    "GNUmakefile":      _make_lc,
    "Cargo.toml":       _toml_lc,
    "pyproject.toml":   _toml_lc,
    "package.json":     _json_lc,
    "go.mod":           _gomod_lc,
    "build.gradle":     _gradle_lc,
    "build.gradle.kts": _lc("kotlin", "kotlin", _KOTLIN_RULES),
    "pom.xml":          _xml_lc,
    "conanfile.py":     _lc("conan",  "python", _PYTHON_RULES),
    "conanfile.txt":    _lc("conan",  "ini",    []),
}

# Public sets used by cli.py to discover files
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(_EXT_REGISTRY.keys())
BUILD_FILENAMES: frozenset[str]      = frozenset(_FILENAME_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Parser cache
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _get_cached_parser(ts_name: str):
    try:
        return _ts_get_parser(ts_name)
    except Exception as e:
        raise RuntimeError(
            f"Grammar '{ts_name}' not available in tree-sitter-language-pack: {e}. "
            "Try: pip install tree-sitter-language-pack --upgrade"
        ) from e


# ---------------------------------------------------------------------------
# Chunking logic
# ---------------------------------------------------------------------------

def _token_count(text: str) -> int:
    return len(text.split())


def _split_large_chunk(chunk: CodeChunk) -> list[CodeChunk]:
    """Split an oversized chunk into overlapping sub-chunks by lines."""
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
            language=chunk.language,
            parent_name=chunk.parent_name,
            call_depth=chunk.call_depth,
            chunk_index=idx,
        ))
        idx += 1
        if j >= len(lines):
            break
        overlap_tokens = 0
        step = j - 1
        while step > i and overlap_tokens < OVERLAP_TOKENS:
            overlap_tokens += len(lines[step].split())
            step -= 1
        new_i = step + 1
        if new_i <= i:
            new_i = i + 1
        i = new_i
    return sub_chunks


def _extract_chunks(source: bytes, file_path: str, lang: _LangConfig) -> list[CodeChunk]:
    parser = _get_cached_parser(lang.ts_name)
    tree = parser.parse(source)
    lines = source.decode(errors="replace").splitlines()
    chunks: list[CodeChunk] = []

    # Build fast lookup: node_type → rule
    type_to_rule: dict[str, _Rule] = {}
    for rule in lang.rules:
        for nt in rule.node_types:
            type_to_rule[nt] = rule

    def visit(node, depth: int = 0, parent_name: str = "") -> None:
        rule = type_to_rule.get(node.type)
        if rule is not None:
            name = rule.extract_name(node)
            if name is not None:
                r0, r1 = node.start_point[0], node.end_point[0]
                text = "\n".join(lines[r0: r1 + 1])
                chunk = CodeChunk(
                    symbol_name=name,
                    file_path=file_path,
                    line_start=r0 + 1,
                    line_end=r1 + 1,
                    code_text=text,
                    chunk_type=rule.chunk_type,
                    language=lang.name,
                    parent_name=parent_name,
                    call_depth=depth,
                    chunk_index=0,
                )
                if _token_count(text) > MAX_TOKENS:
                    chunks.extend(_split_large_chunk(chunk))
                else:
                    chunks.append(chunk)
                if not rule.recurse:
                    return
                for child in node.children:
                    visit(child, depth + 1, name)
                return
        for child in node.children:
            visit(child, depth, parent_name)

    visit(tree.root_node)
    return chunks


def chunk_code_file(path: Path) -> list[CodeChunk]:
    """Parse a source or build file and return all named code chunks."""
    source = path.read_bytes()
    lang = _FILENAME_REGISTRY.get(path.name) or _EXT_REGISTRY.get(path.suffix.lower())
    if lang is None:
        raise ValueError(f"Unsupported file type: {path.name!r}")
    return _extract_chunks(source, str(path), lang)
