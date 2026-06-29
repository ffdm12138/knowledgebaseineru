"""Read formal v2 paper assets via all.catalog.json."""
from __future__ import annotations

from pathlib import Path

from config.settings import ALL_CATALOG_PATH
from src.catalog import Catalog
from src.naming import safe_child, validate_image_name, validate_paper_id
from src.path_utils import resolve_stored_path


class PaperLibrary:
    def __init__(self, catalog: Catalog | None = None, all_catalog_path: Path = ALL_CATALOG_PATH):
        self.catalog = catalog or Catalog(all_catalog_path)

    def _entry(self, paper_or_number: str) -> dict | None:
        return self.catalog.get(paper_or_number)

    def exists(self, paper_or_number: str) -> bool:
        return self._entry(paper_or_number) is not None

    def markdown_path(self, paper_or_number: str) -> Path:
        entry = self._entry(paper_or_number)
        if not entry:
            validate_paper_id(paper_or_number)
            raise FileNotFoundError(f"paper not found: {paper_or_number}")
        return resolve_stored_path(entry["main_md"])

    def images_dir(self, paper_or_number: str) -> Path:
        entry = self._entry(paper_or_number)
        if not entry:
            validate_paper_id(paper_or_number)
            raise FileNotFoundError(f"paper not found: {paper_or_number}")
        return resolve_stored_path(entry["images_dir"])

    def read_markdown(self, paper_or_number: str, max_chars: int | None = None) -> str | None:
        path = self.markdown_path(paper_or_number)
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8", errors="ignore")
        return text[:max_chars] if max_chars else text

    def list_images(self, paper_or_number: str) -> list[str]:
        folder = self.images_dir(paper_or_number)
        if not folder.exists():
            return []
        return sorted(p.name for p in folder.iterdir() if p.is_file())

    def image_path(self, paper_or_number: str, image_name: str) -> Path:
        validate_image_name(image_name)
        return safe_child(self.images_dir(paper_or_number), image_name)

    def list_all(self) -> list[dict]:
        return self.catalog.list_papers()

    def read_multiple(self, paper_ids: list[str], max_chars_each: int | None = None) -> dict[str, str]:
        out: dict[str, str] = {}
        for pid in paper_ids:
            text = self.read_markdown(pid, max_chars=max_chars_each)
            if text is not None:
                out[pid] = text
        return out
