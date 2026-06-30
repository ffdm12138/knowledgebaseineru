"""Compatibility wrapper for formal v2 paper assets.

New code should use src.services.paper_library.PaperLibrary directly. This
module preserves the older src.library.PaperLibrary import path while resolving
assets through paper_index.json / formal data/papers folders, without reading
old all.catalog path fields.
"""
from __future__ import annotations

from pathlib import Path

from config.settings import ALL_CATALOG_PATH, PAPERS_DIR
from src.catalog import Catalog
from src.naming import validate_paper_id
from src.services.paper_library import PaperLibrary as ServicePaperLibrary


class PaperLibrary:
    def __init__(self, catalog: Catalog | None = None, all_catalog_path: Path = ALL_CATALOG_PATH):
        self.catalog = catalog or Catalog(all_catalog_path)
        papers_dir = getattr(getattr(self.catalog, "library", None), "papers_dir", None)
        self._service = ServicePaperLibrary(
            all_catalog_path=getattr(self.catalog, "path", all_catalog_path),
            papers_dir=papers_dir if papers_dir is not None else PAPERS_DIR,
        )

    def _entry(self, paper_or_number: str) -> dict | None:
        return self._service.resolve(paper_or_number)

    def resolve(self, paper_or_number: str) -> dict | None:
        return self._entry(paper_or_number)

    def exists(self, paper_or_number: str) -> bool:
        return self._entry(paper_or_number) is not None

    def markdown_path(self, paper_or_number: str) -> Path:
        try:
            return self._service.markdown_path(paper_or_number)
        except FileNotFoundError:
            validate_paper_id(paper_or_number)
            raise FileNotFoundError(f"paper not found: {paper_or_number}")

    def images_dir(self, paper_or_number: str) -> Path:
        try:
            return self._service.images_dir(paper_or_number)
        except FileNotFoundError:
            validate_paper_id(paper_or_number)
            raise FileNotFoundError(f"paper not found: {paper_or_number}")

    def read_markdown(self, paper_or_number: str, max_chars: int | None = None) -> str | None:
        return self._service.read_markdown(paper_or_number, max_chars=max_chars)

    def list_images(self, paper_or_number: str) -> list[str]:
        return self._service.list_images(paper_or_number)

    def image_path(self, paper_or_number: str, image_name: str) -> Path:
        return self._service.image_path(paper_or_number, image_name)

    def paper_dir(self, paper_or_number: str) -> Path:
        return self._service.paper_dir(paper_or_number)

    def load_metadata(self, paper_or_number: str) -> dict | None:
        return self._service.load_metadata(paper_or_number)

    def load_catalog(self, paper_or_number: str) -> dict | None:
        return self._service.load_catalog(paper_or_number)

    def list_all(self) -> list[dict]:
        return self.catalog.list_papers()

    def read_multiple(self, paper_ids: list[str], max_chars_each: int | None = None) -> dict[str, str]:
        out: dict[str, str] = {}
        for pid in paper_ids:
            text = self.read_markdown(pid, max_chars=max_chars_each)
            if text is not None:
                out[pid] = text
        return out
