"""Rich TUI components for qrag build.

All Rich widget construction, layout math, path formatting, and refresh logic
lives here. cli.py calls BuildLayout and its event methods; it never imports
Rich directly for the build command.
"""
from __future__ import annotations

import os
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, ProgressColumn, SpinnerColumn, Task, TextColumn
from rich.rule import Rule
from rich.table import Column
from rich.text import Text

# ── Layout constants ──────────────────────────────────────────────────────────

MIN_HEIGHT: int = 12
MIN_WIDTH: int = 60
REFRESH_PER_SECOND: int = 2  # 500 ms

_COL_BAR: int = 35
_COL_COUNT: int = 15
_COL_RATE: int = 16
_COL_ETA: int = 8


# ── ETA / path utilities ──────────────────────────────────────────────────────

def fmt_eta(seconds: float) -> str:
    """Convert seconds to a short ETA string: Xs / Xm Ys / Xh Ym."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        m, rem = divmod(s, 60)
        return f"{m}m {rem}s"
    h, rem = divmod(s, 3600)
    return f"{h}h {rem // 60}m"


def fmt_path(abs_path: str, root: str, max_width: int) -> str:
    """Smart path truncation: start/…/parent/filename, shrinking toward filename."""
    try:
        parts = list(Path(abs_path).relative_to(root).parts)
    except ValueError:
        parts = list(Path(abs_path).parts)

    if not parts:
        return abs_path[:max_width]

    filename = parts[-1]

    # Full path fits
    full = "/".join(parts)
    if len(full) <= max_width:
        return full

    # start/…/parent/filename — grow head from the left until it no longer fits
    if len(parts) >= 3:
        tail = f"{parts[-2]}/{filename}"
        base = f"{parts[0]}/…/{tail}"
        if len(base) <= max_width:
            best = base
            for i in range(1, len(parts) - 2):
                candidate = "/".join(parts[: i + 1]) + f"/…/{tail}"
                if len(candidate) <= max_width:
                    best = candidate
                else:
                    break
            return best

    # …/parent/filename
    if len(parts) >= 2:
        candidate = f"…/{parts[-2]}/{filename}"
        if len(candidate) <= max_width:
            return candidate

    # …/filename
    candidate = f"…/{filename}"
    if len(candidate) <= max_width:
        return candidate

    # Last resort: truncate the filename itself
    return filename[:max_width]


# ── Custom progress columns ───────────────────────────────────────────────────

class _EtaColumn(ProgressColumn):
    """ETA column using fmt_eta() instead of Rich's default HH:MM:SS format."""

    def __init__(self) -> None:
        super().__init__(table_column=Column(min_width=_COL_ETA, justify="right", no_wrap=True))

    def render(self, task: Task) -> Text:
        remaining = task.time_remaining
        if remaining is None or task.total is None:
            return Text("—", style="dim", justify="right")
        return Text(fmt_eta(remaining), justify="right")


class _FieldColumn(ProgressColumn):
    """Renders a named field from task.fields with a fixed minimum column width."""

    def __init__(self, field: str, min_width: int = 0) -> None:
        super().__init__(
            table_column=Column(min_width=min_width or None, justify="right", no_wrap=True)
        )
        self._field = field

    def render(self, task: Task) -> Text:
        value = str(task.fields.get(self._field, ""))
        return Text(value, justify="right", no_wrap=True)


# ── Spinner helper ────────────────────────────────────────────────────────────

@contextmanager
def status_spinner(msg: str) -> Iterator[None]:
    """Show a Rich spinner for a blocking one-shot operation."""
    from rich.status import Status
    with Status(msg, console=Console(stderr=True), spinner="dots"):
        yield


# ── BuildLayout ───────────────────────────────────────────────────────────────

class BuildLayout:
    """Manages the full Rich Live layout for ``qrag build``.

    Owns all Rich widget state. cli.py calls on_file_parsed(), on_error(), and
    on_embed_batch() as events arrive; BuildLayout handles all rendering.

    Usage::

        with BuildLayout(total_files, out_dir, code_workers, doc_workers) as layout:
            layout.on_file_parsed(...)
            layout.on_embed_batch(...)
    """

    _LOG_MAXLEN: int = 200

    def __init__(
        self,
        total_files: int,
        out_dir: Path,
        code_workers: int,
        doc_workers: int,
    ) -> None:
        self._total_files = total_files
        self._out_dir = out_dir
        self._code_workers = code_workers
        self._doc_workers = doc_workers
        self._console = Console(stderr=True)

        # Mutable state updated by event callbacks
        self._log: deque[str] = deque(maxlen=self._LOG_MAXLEN)
        self._files_parsed: int = 0
        self._chunks_embedded: int = 0
        self._error_count: int = 0
        self._warning_count: int = 0
        self._parse_rate: str = "—"
        self._embed_rate: str = "—"
        self._parse_batches: deque[tuple[int, float]] = deque(maxlen=20)
        self._embed_batches: deque[tuple[int, float]] = deque(maxlen=20)

        self._progress = self._make_progress()
        self._overall_task = self._progress.add_task(
            "Overall", total=total_files * 2, count="", rate="—",
        )
        self._parse_task = self._progress.add_task(
            "  Parse ", total=total_files,
            count=f"0/{total_files} files", rate="—",
        )
        self._embed_task = self._progress.add_task(
            "  Embed ", total=None, count="", rate="waiting…",
        )
        self._live: Live | None = None

    @staticmethod
    def _make_progress() -> Progress:
        return Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description:<8}"),
            BarColumn(bar_width=_COL_BAR),
            _FieldColumn("count", min_width=_COL_COUNT),
            _FieldColumn("rate", min_width=_COL_RATE),
            _EtaColumn(),
            expand=False,
        )

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "BuildLayout":
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=REFRESH_PER_SECOND,
            transient=True,
        )
        self._live.start()
        return self

    def __exit__(self, *_) -> None:
        if self._live:
            self._live.stop()
            self._live = None

    # ── Public event callbacks ────────────────────────────────────────────────

    def on_file_parsed(
        self,
        abs_path: str,
        root: str,
        chunks: int,
        elapsed: float,
        skipped: bool = False,
        skip_reason: str = "",
    ) -> None:
        """Called when a file has been parsed (successfully or with zero chunks)."""
        self._files_parsed += 1
        if skipped and skip_reason == "zero_chunks":
            self._warning_count += 1

        # Rolling parse rate (deque of (file_count, elapsed) pairs)
        self._parse_batches.append((1, elapsed))
        if len(self._parse_batches) >= 2:
            total_t = sum(b[1] for b in self._parse_batches)
            if total_t > 0:
                rate = sum(b[0] for b in self._parse_batches) / total_t
                self._parse_rate = f"{rate:.0f} files/s"

        # Log panel entry
        width = max(30, self._console.size.width - 22)
        short = fmt_path(abs_path, root, width)
        if skipped and skip_reason == "zero_chunks":
            entry = f"[yellow]⚠[/yellow] {short}  [dim]{chunks} chunks {elapsed:.1f}s[/dim]"
        else:
            entry = f"[green]✓[/green] {short}  [dim]{chunks} chunks {elapsed:.1f}s[/dim]"
        self._log.append(entry)

        count_str = f"{self._files_parsed}/{self._total_files} files"
        self._progress.update(
            self._parse_task, advance=1, count=count_str, rate=self._parse_rate,
        )
        self._update_overall()
        self._push()

    def on_error(self, abs_path: str, root: str, msg: str) -> None:
        """Called when a file failed to parse."""
        self._error_count += 1
        self._files_parsed += 1
        width = max(30, self._console.size.width - 22)
        short = fmt_path(abs_path, root, width)
        truncated = (msg[:60] + "…") if len(msg) > 60 else msg
        self._log.append(
            f"[red]✗[/red] [red]{short}[/red]  [dim red]{truncated}[/dim red]"
        )
        self._progress.update(self._parse_task, advance=1)
        self._update_overall()
        self._push()

    def on_embed_batch(
        self,
        batch_len: int,
        elapsed_batch: float,
        chunks_embedded: int,
        avg_chunks_per_file: float,
    ) -> None:
        """Called after each embedding batch is written to the DB."""
        self._chunks_embedded = chunks_embedded
        self._embed_batches.append((batch_len, elapsed_batch))
        total_ch = sum(b[0] for b in self._embed_batches)
        total_t = sum(b[1] for b in self._embed_batches)
        if total_t > 0:
            self._embed_rate = f"{total_ch / total_t:,.0f} chunks/s"

        est_total = (
            max(chunks_embedded, int(avg_chunks_per_file * self._total_files))
            if self._total_files > 0 and avg_chunks_per_file > 0
            else None
        )
        # Progress.update() calls task._reset() whenever `total` actually changes,
        # which wipes the rolling speed samples Rich needs for time_remaining.
        # est_total is a rolling estimate that jitters on nearly every batch, so
        # only push a new total when it drifts enough to matter — otherwise the
        # ETA column would show "—" forever.
        current_total = self._progress.tasks[self._embed_task].total
        if (
            est_total is not None
            and current_total is not None
            and abs(est_total - current_total) < 0.1 * current_total
        ):
            est_total = current_total
        self._progress.update(
            self._embed_task,
            completed=chunks_embedded,
            total=est_total,
            count=f"{chunks_embedded:,} chunks",
            rate=self._embed_rate,
        )
        self._update_overall()
        self._push()

    # ── Internal rendering ────────────────────────────────────────────────────

    def _update_overall(self) -> None:
        avg_ch = self._chunks_embedded / max(1, self._files_parsed) if self._files_parsed else 0
        est_embedded = self._chunks_embedded / max(1.0, avg_ch) if avg_ch > 0 else 0
        completed = int(self._files_parsed + min(est_embedded, self._total_files))
        self._progress.update(self._overall_task, completed=completed)

    def _panel_lines(self) -> int:
        return max(5, min(20, self._console.size.height - 9))

    def _is_too_small(self) -> bool:
        size = self._console.size
        return size.height < MIN_HEIGHT or size.width < MIN_WIDTH

    def _render(self) -> Group:
        if self._is_too_small():
            return Group(
                Text(
                    "Terminal too small — showing minimal output",
                    style="bold yellow",
                    justify="center",
                ),
                self._progress,
            )

        # Worker header
        total_cores = os.cpu_count() or 1
        if self._code_workers > 0 and self._doc_workers > 0:
            hdr = (
                f"⚙️  {self._code_workers} code workers · "
                f"{self._doc_workers} doc workers  ({total_cores} cores total)"
            )
        elif self._code_workers > 0:
            hdr = f"⚙️  {self._code_workers} code workers  ({total_cores} cores)"
        else:
            hdr = f"⚙️  {self._doc_workers} doc workers  ({total_cores} cores)"

        # Log panel
        n = self._panel_lines()
        visible = list(self._log)[-n:]
        panel_markup = (
            "\n".join(visible) if visible else "[dim]Waiting for files…[/dim]"
        )
        log_panel = Panel(
            Text.from_markup(panel_markup),
            title="Processing",
            expand=True,
        )

        # Build report footer (between log panel and status line)
        report_path = self._out_dir / "build-report.txt"
        footer = Text(f"  Build report → {report_path}", style="dim")

        # Status line
        parts: list[str] = []
        if self._error_count:
            parts.append(f"[red]{self._error_count} error{'s' if self._error_count != 1 else ''}[/red]")
        if self._warning_count:
            parts.append(f"[yellow]{self._warning_count} warning{'s' if self._warning_count != 1 else ''}[/yellow]")
        if self._embed_rate != "—":
            parts.append(f"[cyan]{self._embed_rate}[/cyan]")
        if self._code_workers > 0 and self._doc_workers > 0:
            parts.append(f"{self._code_workers}+{self._doc_workers} workers")
        status = Text.from_markup("  •  ".join(parts)) if parts else Text("")

        return Group(
            Text(hdr, style="bold cyan"),
            Rule(style="dim"),
            self._progress,
            Rule(style="dim"),
            log_panel,
            footer,
            Rule(style="dim"),
            status,
        )

    def _push(self) -> None:
        if self._live is not None:
            self._live.update(self._render())


# ===========================================================================
# TreeView — reusable expandable/fuzzy tree widget (explore browser + diff)
# ===========================================================================

def fuzzy_match(query: str, text: str) -> bool:
    """Case-insensitive subsequence match (the fuzzy filter used in the TUI)."""
    if not query:
        return True
    it = iter(text.lower())
    return all(ch in it for ch in query.lower())


@dataclass
class TreeNode:
    label: str
    key: str
    data: Any = None
    children: list["TreeNode"] = field(default_factory=list)
    expanded: bool = False

    @property
    def is_branch(self) -> bool:
        return bool(self.children)


class TreeView:
    """Pure navigation/selection model over a forest of TreeNodes.

    All state transitions (move, toggle, filter) are side-effect-free on the
    outside world, so they are unit-tested without any terminal. The
    interactive loop (run_explore_browser / the diff viewer) renders .visible()
    and feeds keypresses into these methods.
    """

    def __init__(self, roots: list[TreeNode]) -> None:
        self.roots = roots
        self.filter = ""
        self.index = 0

    def _matches(self, node: TreeNode) -> bool:
        if not self.filter:
            return True
        if fuzzy_match(self.filter, node.label):
            return True
        return any(self._matches(c) for c in node.children)

    def _flatten(self, nodes: list[TreeNode], depth: int, out: list) -> None:
        for node in nodes:
            if not self._matches(node):
                continue
            out.append((node, depth))
            # A filter auto-expands branches that contain a match.
            auto = bool(self.filter) and any(self._matches(c) for c in node.children)
            if node.children and (node.expanded or auto):
                self._flatten(node.children, depth + 1, out)

    def visible(self) -> list[tuple[TreeNode, int]]:
        out: list[tuple[TreeNode, int]] = []
        self._flatten(self.roots, 0, out)
        return out

    def move(self, delta: int) -> None:
        count = len(self.visible())
        if count == 0:
            self.index = 0
            return
        self.index = max(0, min(count - 1, self.index + delta))

    @property
    def current(self) -> TreeNode | None:
        vis = self.visible()
        if not vis:
            return None
        self.index = max(0, min(len(vis) - 1, self.index))
        return vis[self.index][0]

    def toggle(self) -> None:
        node = self.current
        if node is not None and node.children:
            node.expanded = not node.expanded

    def expand_current(self) -> None:
        node = self.current
        if node is not None and node.children:
            node.expanded = True

    def set_filter(self, text: str) -> None:
        self.filter = text
        self.index = 0

    def render(self, empty_hint: str = "(nothing to show)") -> Group:
        """Build a Rich renderable of the currently visible rows."""
        vis = self.visible()
        if not vis:
            return Group(Text(empty_hint, style="dim"))
        lines: list[Text] = []
        for i, (node, depth) in enumerate(vis):
            indent = "  " * depth
            if node.children:
                marker = "▾ " if (node.expanded or self.filter) else "▸ "
            else:
                marker = "  "
            line = Text(f"{indent}{marker}{node.label}")
            if i == self.index:
                line.stylize("reverse")
            lines.append(line)
        return Group(*lines)


# ===========================================================================
# Interactive explore browser (qrag explore, no args) — #46
# ===========================================================================

def _version_nodes() -> list[TreeNode]:
    """Build the version forest from the local cache (each version → detail children)."""
    from . import explore as _explore

    nodes: list[TreeNode] = []
    for v in _explore.gather_local_versions():
        marker = "●" if v.active else "○"
        content = "+".join(k for k, present in (("code", v.has_code), ("docs", v.has_docs)) if present)
        node = TreeNode(label=f"{marker} {v.name}  [{content}]", key=v.name, data=v)
        langs = "  ".join(f"{lang} {pct:.0f}%" for lang, pct in _explore.lang_percentages(v.languages)) or "—"
        origin = _explore.get_origin_remote(v.name) or "—"
        node.children = [
            TreeNode(f"size {_explore.human_size(v.size_bytes)} · built {_explore.human_age(v.built_at)}", key=v.name + ":size"),
            TreeNode(f"symbols {v.symbols} · sections {v.sections} · docs {v.docs}", key=v.name + ":counts"),
            TreeNode(f"languages: {langs}", key=v.name + ":langs"),
            TreeNode(f"active: {'yes' if v.active else 'no'} · origin: {origin}", key=v.name + ":meta"),
        ]
        nodes.append(node)
    return nodes


_BROWSER_KEYS = (
    "j/k move · space expand · ⏎ details · / filter · "
    "a activate · d delete · p push · r refresh · q quit"
)


def run_explore_browser() -> bool:
    """Interactive database browser. Returns False if readchar is unavailable
    (so the caller can fall back to `explore list`)."""
    try:
        import readchar
    except ImportError:
        return False

    from . import explore as _explore

    console = Console()
    tree = TreeView(_version_nodes())
    message = ""

    def draw() -> None:
        console.clear()
        body = tree.render(empty_hint="(no databases — build one with: qrag build)")
        console.print(Panel(body, title="qrag explore", title_align="left", expand=True))
        if message:
            console.print(message)
        console.print(Text(_BROWSER_KEYS, style="dim"))

    def read_filter() -> str:
        # simple line editor for the fuzzy filter
        buf = tree.filter
        while True:
            tree.set_filter(buf)
            console.clear()
            console.print(Panel(tree.render(), title="qrag explore", title_align="left", expand=True))
            console.print(Text(f"/{buf}", style="yellow"))
            console.print(Text("type to filter · Enter apply · Esc clear", style="dim"))
            key = readchar.readkey()
            if key in (readchar.key.ENTER, "\r", "\n"):
                return buf
            if key == readchar.key.ESC:
                return ""
            if key in (readchar.key.BACKSPACE, "\x7f", "\b"):
                buf = buf[:-1]
            elif key.isprintable() and len(key) == 1:
                buf += key

    while True:
        draw()
        message = ""
        try:
            key = readchar.readkey()
        except KeyboardInterrupt:
            break

        if key in ("q", readchar.key.ESC):
            break
        elif key in ("j", readchar.key.DOWN):
            tree.move(1)
        elif key in ("k", readchar.key.UP):
            tree.move(-1)
        elif key == " ":
            tree.toggle()
        elif key in (readchar.key.ENTER, "\r", "\n"):
            tree.expand_current()
        elif key == "/":
            tree.set_filter(read_filter())
        elif key == "r":
            tree = TreeView(_version_nodes())
            message = "[green]refreshed[/green]"
        elif key in ("a", "d", "p"):
            node = tree.current
            if node is None or node.data is None:
                continue
            version = node.key.split(":")[0]
            message = _browser_action(key, version, console)
            tree = TreeView(_version_nodes())  # reflect the change

    console.clear()
    return True


def _browser_action(key: str, version: str, console: Console) -> str:
    """Run an a/d/p action on VERSION, returning a status message."""
    from . import explore as _explore
    from .config import add_active_version, remove_active_version

    try:
        if key == "a":
            info = _explore.gather_version(version)
            if info.active:
                remove_active_version(version)
                return f"[yellow]deactivated[/yellow] {version}"
            add_active_version(version)
            return f"[green]activated[/green] {version}"

        if key == "d":
            typed = console.input(f"Delete '{version}'? type the name to confirm: ")
            if typed != version:
                return "delete cancelled"
            _explore.delete_local(version)
            return f"[red]deleted[/red] {version}"

        if key == "p":
            backend = _explore.resolve_push_backend(version, None)
            backend.check_auth()
            backend.push(version, _explore.CACHE_DIR / version, force=False)
            return f"[green]pushed[/green] {version} → {backend.name}"
    except _explore.RemoteError as e:
        return f"[red]error[/red] {e}"
    except Exception as e:  # keep the browser alive on any action failure
        return f"[red]error[/red] {e}"
    return ""
