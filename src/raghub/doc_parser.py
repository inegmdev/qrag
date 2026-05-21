"""PDF and HTML document parsers that produce DocSection records."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

MAX_TOKENS = 512
OVERLAP_TOKENS = 64

# Patterns like "2", "2.1", "2.1.3" at the start of a heading
_SEC_NUM = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")
# ALL-CAPS abbreviations 2-8 chars used as feature tags
_ABBREV = re.compile(r"\b([A-Z][A-Z0-9]{1,7})\b")


@dataclass
class DocSection:
    source_path: str
    doc_type: str          # "TRM", "Datasheet", "AppNote", "HTML"
    chapter: int
    section: int
    subsection: str
    title: str
    content: str
    page_range: str        # e.g. "42" or "42-45"
    feature_tags: str      # comma-separated


def _token_count(text: str) -> int:
    return len(text.split())


def _extract_tags(title: str, content: str) -> str:
    tags: set[str] = set()
    for m in _ABBREV.finditer(title + " " + content[:500]):
        t = m.group(1)
        if len(t) >= 2:
            tags.add(t)
    # Remove common English words that happen to be all caps (short stop words)
    stop = {"A", "I", "AN", "AT", "BY", "IN", "IS", "IT", "OF", "ON",
            "OR", "TO", "UP", "BE", "DO", "IF", "NO", "SO", "AS"}
    return ",".join(sorted(tags - stop))


def _split_section(sec: DocSection) -> list[DocSection]:
    """Split a large section into overlapping sub-sections."""
    if _token_count(sec.content) <= MAX_TOKENS:
        return [sec]

    words = sec.content.split()
    subs: list[DocSection] = []
    i = 0
    idx = 0
    while i < len(words):
        chunk_words = words[i : i + MAX_TOKENS]
        text = " ".join(chunk_words)
        subs.append(DocSection(
            source_path=sec.source_path,
            doc_type=sec.doc_type,
            chapter=sec.chapter,
            section=sec.section,
            subsection=sec.subsection,
            title=f"{sec.title} [{idx}]" if idx > 0 else sec.title,
            content=text,
            page_range=sec.page_range,
            feature_tags=sec.feature_tags,
        ))
        idx += 1
        if i + MAX_TOKENS >= len(words):
            break
        i += MAX_TOKENS - OVERLAP_TOKENS
    return subs


# ── PDF parser ───────────────────────────────────────────────────────────────

def _parse_heading_number(text: str) -> tuple[int, int, str]:
    """Return (chapter, section, subsection) from a heading string."""
    m = _SEC_NUM.match(text.strip())
    if not m:
        return (0, 0, "")
    ch = int(m.group(1)) if m.group(1) else 0
    se = int(m.group(2)) if m.group(2) else 0
    sub = m.group(3) or ""
    return ch, se, sub


def parse_pdf(path: Path, doc_type: str = "TRM") -> list[DocSection]:
    import fitz  # PyMuPDF

    doc = fitz.open(str(path))
    source = str(path)

    # First pass: collect all spans to determine body font size (mode)
    sizes: list[float] = []
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    if span["text"].strip():
                        sizes.append(span["size"])

    if not sizes:
        doc.close()
        return []

    # Median as body size threshold
    sizes_sorted = sorted(sizes)
    median_size = sizes_sorted[len(sizes_sorted) // 2]
    h1_threshold = median_size * 1.4
    h2_threshold = median_size * 1.15

    # Second pass: build sections
    sections: list[DocSection] = []
    cur_ch, cur_se, cur_sub = 0, 0, ""
    cur_title = ""
    cur_lines: list[str] = []
    cur_page_start = 1
    cur_page_end = 1

    def flush():
        if not cur_title and not cur_lines:
            return
        content = " ".join(" ".join(cur_lines).split())
        if not content:
            return
        page_range = str(cur_page_start) if cur_page_start == cur_page_end \
            else f"{cur_page_start}-{cur_page_end}"
        sec = DocSection(
            source_path=source,
            doc_type=doc_type,
            chapter=cur_ch,
            section=cur_se,
            subsection=cur_sub,
            title=cur_title,
            content=content,
            page_range=page_range,
            feature_tags=_extract_tags(cur_title, content),
        )
        sections.extend(_split_section(sec))

    for page_idx, page in enumerate(doc, start=1):
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                line_text = " ".join(
                    span["text"] for span in line["spans"]
                ).strip()
                if not line_text:
                    continue
                # Use max span size in the line for heading detection
                max_size = max(span["size"] for span in line["spans"])

                if max_size >= h1_threshold:
                    flush()
                    cur_ch, cur_se, cur_sub = _parse_heading_number(line_text)
                    cur_se = 0
                    cur_title = line_text
                    cur_lines = []
                    cur_page_start = page_idx
                    cur_page_end = page_idx

                elif max_size >= h2_threshold:
                    flush()
                    ch2, se2, sub2 = _parse_heading_number(line_text)
                    if ch2:
                        cur_ch = ch2
                    cur_se = se2
                    cur_sub = sub2
                    cur_title = line_text
                    cur_lines = []
                    cur_page_start = page_idx
                    cur_page_end = page_idx

                else:
                    cur_lines.append(line_text)
                    cur_page_end = page_idx

    flush()
    doc.close()
    return sections


# ── HTML parser ──────────────────────────────────────────────────────────────

_BOILERPLATE_IDS = re.compile(r"(nav|toc|sidebar|header|footer|menu)", re.I)
_BOILERPLATE_CLASSES = re.compile(r"(nav|toc|sidebar|header|footer|menu|breadcrumb)", re.I)


def _is_boilerplate(tag) -> bool:
    if not hasattr(tag, "attrs") or tag.attrs is None:
        return False
    tag_id = (tag.attrs.get("id", "") or "")
    tag_cls = " ".join(tag.attrs.get("class", []) or [])
    return bool(
        _BOILERPLATE_IDS.search(tag_id)
        or _BOILERPLATE_CLASSES.search(tag_cls)
        or tag.name in ("nav", "header", "footer", "aside")
    )


def parse_html(path: Path, doc_type: str = "HTML") -> list[DocSection]:
    from bs4 import BeautifulSoup, NavigableString, Tag

    text = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(text, "html.parser")

    # Remove boilerplate tags
    for tag in soup.find_all(True):
        if _is_boilerplate(tag):
            tag.decompose()

    source = str(path)
    sections: list[DocSection] = []
    cur_ch, cur_se, cur_sub = 0, 0, ""
    cur_title = ""
    cur_lines: list[str] = []

    def flush():
        if not cur_title and not cur_lines:
            return
        content = " ".join(" ".join(cur_lines).split())
        if not content:
            return
        sec = DocSection(
            source_path=source,
            doc_type=doc_type,
            chapter=cur_ch,
            section=cur_se,
            subsection=cur_sub,
            title=cur_title,
            content=content,
            page_range="",
            feature_tags=_extract_tags(cur_title, content),
        )
        sections.extend(_split_section(sec))

    HEADING_TAGS = {"h1", "h2", "h3", "h4"}

    for element in soup.body.descendants if soup.body else []:
        if not isinstance(element, Tag):
            continue
        if element.name in HEADING_TAGS:
            heading_text = element.get_text(" ", strip=True)
            if not heading_text:
                continue
            flush()
            cur_lines = []
            if element.name in ("h1",):
                cur_ch, cur_se, cur_sub = _parse_heading_number(heading_text)
                cur_se = 0
            elif element.name in ("h2",):
                ch2, se2, sub2 = _parse_heading_number(heading_text)
                if ch2:
                    cur_ch = ch2
                cur_se = se2
                cur_sub = sub2
            elif element.name in ("h3", "h4"):
                _, _, sub3 = _parse_heading_number(heading_text)
                cur_sub = sub3 or heading_text[:40]
            cur_title = heading_text

        elif element.name == "p":
            para = element.get_text(" ", strip=True)
            if para:
                cur_lines.append(para)

    flush()
    return sections
