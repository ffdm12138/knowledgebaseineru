"""PaperLibrary — load metadata/catalog/assets by paper_number.

After the catalog/metadata separation, all.catalog is a content index (no
bibliographic fields) and paper_index.json maps paper_number → asset paths.
Consumers that need bibliographic facts (DOI/title/authors/year/journal) MUST
go through this accessor (or read data/papers/<pid>/...metadata.json directly)
— never through all.catalog entries.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.settings import ALL_CATALOG_PATH, PAPERS_DIR


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


class PaperLibrary:
    """Access metadata/catalog/assets by paper_number, backed by paper_index.json."""

    def __init__(
        self,
        *,
        all_catalog_path: str | Path = ALL_CATALOG_PATH,
        papers_dir: str | Path = PAPERS_DIR,
    ):
        self.all_catalog_path = Path(all_catalog_path)
        self.papers_dir = Path(papers_dir)
        self._index_path = self.all_catalog_path.parent / "paper_index.json"
        self._index_cache: dict | None = None

    # ── index ──
    def _index(self) -> list[dict]:
        if self._index_cache is None:
            data = _read_json(self._index_path, {"papers": []})
            self._index_cache = data.get("papers") or []
        return self._index_cache

    def _index_entry(self, paper_number: str) -> dict | None:
        for item in self._index():
            if item.get("paper_number") == paper_number:
                return item
        return None

    def _entry_by_id(self, paper_id: str) -> dict | None:
        for item in self._index():
            if item.get("paper_id") == paper_id:
                return item
        return None

    # ── lookups ──
    def resolve(self, paper_number_or_id: str) -> dict | None:
        """Return the paper_index entry for a paper_number or paper_id."""
        for item in self._index():
            if item.get("paper_number") == paper_number_or_id or item.get("paper_id") == paper_number_or_id:
                return item
        return None

    def load_metadata(self, paper_number: str) -> dict | None:
        entry = self._index_entry(paper_number)
        if not entry:
            return None
        path = Path(entry.get("metadata_path") or "")
        if not path.exists() and entry.get("paper_id"):
            path = self.papers_dir / entry["paper_id"] / f"{entry['paper_id']}.metadata.json"
        meta = _read_json(path, None)
        return meta if meta else None

    def load_catalog(self, paper_number: str) -> dict | None:
        entry = self._index_entry(paper_number)
        if not entry:
            return None
        path = Path(entry.get("catalog_path") or "")
        if not path.exists() and entry.get("paper_id"):
            path = self.papers_dir / entry["paper_id"] / f"{entry['paper_id']}.catalog.json"
        cat = _read_json(path, None)
        return cat if cat else None

    def all_paper_numbers(self) -> list[str]:
        return [str(item.get("paper_number")) for item in self._index() if item.get("paper_number")]

    def all_entries(self) -> list[dict]:
        """Return all paper_index entries."""
        return list(self._index())

    def metadata_for_all(self) -> dict[str, dict]:
        """paper_number -> metadata dict, for every formal paper. (Reads disk.)"""
        out: dict[str, dict] = {}
        for item in self._index():
            num = item.get("paper_number")
            if not num:
                continue
            meta = self.load_metadata(num)
            if meta:
                out[num] = meta
        return out

    def catalog_entry(self, paper_number: str) -> dict | None:
        """Return the all.catalog content entry for a paper_number."""
        for entry in _read_json(self.all_catalog_path, {"papers": []}).get("papers", []):
            if entry.get("paper_number") == paper_number:
                return entry
        return None
