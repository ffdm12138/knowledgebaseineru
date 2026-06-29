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
from src.naming import safe_child, validate_image_name
from src.path_utils import resolve_stored_path


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
        self._catalog_cache: dict | None = None

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

    def _catalog_entries(self) -> list[dict]:
        if self._catalog_cache is None:
            self._catalog_cache = _read_json(self.all_catalog_path, {"papers": []})
        return list((self._catalog_cache or {}).get("papers") or [])

    def _catalog_entry(self, paper_number_or_id: str) -> dict | None:
        for item in self._catalog_entries():
            if item.get("paper_number") == paper_number_or_id or item.get("paper_id") == paper_number_or_id:
                return item
        return None

    def _inferred_entry(self, paper_id: str, paper_number: str = "") -> dict:
        folder = self.papers_dir / paper_id
        return {
            "paper_number": paper_number,
            "paper_id": paper_id,
            "metadata_path": str(folder / f"{paper_id}.metadata.json"),
            "catalog_path": str(folder / f"{paper_id}.catalog.json"),
            "markdown_path": str(folder / f"{paper_id}.md"),
            "pdf_path": str(folder / f"{paper_id}.pdf"),
            "images_dir": str(folder / "images"),
        }

    def _path_from_entry(self, entry: dict, field: str, suffix: str | None = None) -> Path:
        value = str(entry.get(field) or "").strip()
        if value:
            path = resolve_stored_path(value)
            if path.exists() or not entry.get("paper_id"):
                return path
        paper_id = str(entry.get("paper_id") or "").strip()
        if not paper_id:
            raise FileNotFoundError(f"paper_index entry missing paper_id for {field}")
        folder = self.papers_dir / paper_id
        if field == "images_dir":
            return folder / "images"
        if suffix is None:
            raise FileNotFoundError(f"cannot infer {field} for {paper_id}")
        return folder / f"{paper_id}.{suffix}"

    # ── lookups ──
    def resolve(self, paper_number_or_id: str) -> dict | None:
        """Return a paper_index-style entry for a paper_number or paper_id.

        paper_index.json is preferred. If it is missing, fall back to the
        content-only all.catalog entry and infer formal data/papers paths.
        """
        for item in self._index():
            if item.get("paper_number") == paper_number_or_id or item.get("paper_id") == paper_number_or_id:
                return item
        catalog_entry = self._catalog_entry(paper_number_or_id)
        if catalog_entry and catalog_entry.get("paper_id"):
            return self._inferred_entry(
                str(catalog_entry["paper_id"]),
                str(catalog_entry.get("paper_number") or ""),
            )
        return None

    def metadata_path(self, paper_number_or_id: str) -> Path:
        entry = self.resolve(paper_number_or_id)
        if not entry:
            raise FileNotFoundError(f"paper not found: {paper_number_or_id}")
        return self._path_from_entry(entry, "metadata_path", "metadata.json")

    def catalog_path(self, paper_number_or_id: str) -> Path:
        entry = self.resolve(paper_number_or_id)
        if not entry:
            raise FileNotFoundError(f"paper not found: {paper_number_or_id}")
        return self._path_from_entry(entry, "catalog_path", "catalog.json")

    def markdown_path(self, paper_number_or_id: str) -> Path:
        entry = self.resolve(paper_number_or_id)
        if not entry:
            raise FileNotFoundError(f"paper not found: {paper_number_or_id}")
        return self._path_from_entry(entry, "markdown_path", "md")

    def pdf_path(self, paper_number_or_id: str) -> Path:
        entry = self.resolve(paper_number_or_id)
        if not entry:
            raise FileNotFoundError(f"paper not found: {paper_number_or_id}")
        return self._path_from_entry(entry, "pdf_path", "pdf")

    def images_dir(self, paper_number_or_id: str) -> Path:
        entry = self.resolve(paper_number_or_id)
        if not entry:
            raise FileNotFoundError(f"paper not found: {paper_number_or_id}")
        return self._path_from_entry(entry, "images_dir")

    def paper_dir(self, paper_number_or_id: str) -> Path:
        entry = self.resolve(paper_number_or_id)
        if not entry:
            raise FileNotFoundError(f"paper not found: {paper_number_or_id}")
        metadata = self.metadata_path(paper_number_or_id)
        if metadata.name.endswith(".metadata.json"):
            return metadata.parent
        paper_id = str(entry.get("paper_id") or "").strip()
        if paper_id:
            return self.papers_dir / paper_id
        raise FileNotFoundError(f"cannot infer paper folder for {paper_number_or_id}")

    def load_metadata(self, paper_number_or_id: str) -> dict | None:
        try:
            path = self.metadata_path(paper_number_or_id)
        except FileNotFoundError:
            return None
        meta = _read_json(path, None)
        return meta if meta else None

    def load_catalog(self, paper_number_or_id: str) -> dict | None:
        try:
            path = self.catalog_path(paper_number_or_id)
        except FileNotFoundError:
            return None
        cat = _read_json(path, None)
        return cat if cat else None

    def read_markdown(self, paper_number_or_id: str, max_chars: int | None = None) -> str | None:
        try:
            path = self.markdown_path(paper_number_or_id)
        except FileNotFoundError:
            return None
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8", errors="ignore")
        return text[:max_chars] if max_chars else text

    def list_images(self, paper_number_or_id: str) -> list[str]:
        try:
            folder = self.images_dir(paper_number_or_id)
        except FileNotFoundError:
            return []
        if not folder.exists():
            return []
        return sorted(p.name for p in folder.iterdir() if p.is_file())

    def image_path(self, paper_number_or_id: str, image_name: str) -> Path:
        validate_image_name(image_name)
        return safe_child(self.images_dir(paper_number_or_id), image_name)

    def read_multiple(self, paper_numbers_or_ids: list[str], max_chars_each: int | None = None) -> dict[str, str]:
        out: dict[str, str] = {}
        for key in paper_numbers_or_ids:
            text = self.read_markdown(key, max_chars=max_chars_each)
            if text is not None:
                out[key] = text
        return out

    def all_paper_numbers(self) -> list[str]:
        numbers = [str(item.get("paper_number")) for item in self._index() if item.get("paper_number")]
        if numbers:
            return numbers
        return [str(item.get("paper_number")) for item in self._catalog_entries() if item.get("paper_number")]

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

    def catalog_entry(self, paper_number_or_id: str) -> dict | None:
        """Return the all.catalog content entry for a paper_number or paper_id."""
        return self._catalog_entry(paper_number_or_id)
