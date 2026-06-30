"""Per-job BibTeX helpers.

Each paper's BibTeX is generated from per-paper ``metadata.json`` via
``src/services/v2_library.py::bibtex_from_metadata``. Writing jobs write the
selected entries into job-local ``tex/references.bib``.
"""
import re

from src.services.v2_library import bibtex_from_metadata, sanitize_paper_id


def _entry_type_and_key(block: str) -> tuple[str, str]:
    """从单个 bibtex 块提取 (type, key)，如 (@article{key, ...) → ('article','key')"""
    m = re.match(r"@(\w+)\s*\{\s*([^,\s]+)", block.strip())
    if not m:
        return ("", "")
    return m.group(1).lower(), m.group(2)


def parse_blocks(bib_text: str) -> dict[str, str]:
    """把 bib 文本拆成 {bib_key: block_text}。简单括号匹配，足以处理受控 bib。"""
    blocks = {}
    i = 0
    n = len(bib_text)
    while i < n:
        if bib_text[i] == "@":
            brace_start = bib_text.find("{", i)
            if brace_start == -1:
                break
            depth = 0
            j = brace_start
            while j < n:
                if bib_text[j] == "{":
                    depth += 1
                elif bib_text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            block = bib_text[i:j + 1]
            _, key = _entry_type_and_key(block)
            if key:
                blocks[key] = block.strip()
            i = j + 1
        else:
            i += 1
    return blocks


def _resolve_metadata(entry: dict) -> dict:
    """Get metadata for an entry. all.catalog entries no longer embed metadata,
    so fall back to PaperLibrary by paper_number (then paper_id)."""
    meta = entry.get("metadata")
    if isinstance(meta, dict) and meta:
        return meta
    number = entry.get("paper_number")
    pid = entry.get("paper_id")
    if number or pid:
        try:
            from src.services.paper_library import PaperLibrary
            lib = PaperLibrary()
            m = lib.load_metadata(number) if number else None
            if not m and pid:
                idx = lib.resolve(pid)
                if idx:
                    m = lib.load_metadata(idx.get("paper_number") or "")
            if m:
                return m
        except Exception:
            pass
    return {}


def bib_key_for_entry(entry: dict) -> str:
    """v2 bib_key：metadata.citation_key 或 paper_id（经 sanitize）。"""
    meta = _resolve_metadata(entry)
    key = meta.get("citation_key") or entry.get("paper_id") or ""
    return sanitize_paper_id(str(key))


def bibtex_for_entry(entry: dict) -> str:
    """根据 all.catalog 条目生成单篇 BibTeX（来自 metadata.json）。"""
    meta = _resolve_metadata(entry)
    return bibtex_from_metadata(meta, key=bib_key_for_entry(entry))
