"""Read paper Markdown and images by paper_id.

Path resolution is domain-index aware, while keeping the legacy
data/papers/<paper_id>/paper.md layout as the final fallback.
"""
from pathlib import Path

from loguru import logger

from config.settings import PAPERS_DIR
from src.catalog import Catalog
from src.library_index import LibraryIndex, resolve_repo_path
from src.manifest import PaperManifest


class PaperLibrary:
    """Read cleaned paper.md and images for a paper_id."""

    def __init__(
        self,
        manifest: PaperManifest | None = None,
        catalog: Catalog | None = None,
        library_index: LibraryIndex | None = None,
    ):
        self.manifest = manifest or PaperManifest()
        self.catalog = catalog or Catalog()
        self.library_index = library_index or LibraryIndex()

    def paper_dir(self, paper_id: str) -> Path:
        """Legacy paper directory path for existing callers."""
        from src.naming import safe_child, validate_paper_id

        validate_paper_id(paper_id)
        return safe_child(PAPERS_DIR, paper_id)

    def markdown_path(self, paper_id: str) -> Path:
        """Resolve paper.md path: library_index -> manifest -> catalog -> legacy."""
        from src.naming import validate_paper_id

        validate_paper_id(paper_id)
        idx = self.library_index.get(paper_id) or {}
        if idx.get("markdown_path"):
            return resolve_repo_path(idx["markdown_path"])

        manifest_entry = self.manifest.get(paper_id) or {}
        if manifest_entry.get("markdown"):
            return resolve_repo_path(manifest_entry["markdown"])

        catalog_entry = self.catalog.get(paper_id) or {}
        if catalog_entry.get("markdown"):
            return resolve_repo_path(catalog_entry["markdown"])

        return self.paper_dir(paper_id) / "paper.md"

    def images_dir(self, paper_id: str) -> Path:
        """Resolve images path: library_index -> manifest -> catalog -> legacy."""
        from src.naming import validate_paper_id

        validate_paper_id(paper_id)
        idx = self.library_index.get(paper_id) or {}
        if idx.get("images_dir"):
            return resolve_repo_path(idx["images_dir"])

        manifest_entry = self.manifest.get(paper_id) or {}
        if manifest_entry.get("images_dir"):
            return resolve_repo_path(manifest_entry["images_dir"])

        catalog_entry = self.catalog.get(paper_id) or {}
        if catalog_entry.get("images_dir"):
            return resolve_repo_path(catalog_entry["images_dir"])

        return self.paper_dir(paper_id) / "images"

    def exists(self, paper_id: str) -> bool:
        return self.markdown_path(paper_id).exists()

    def list_papers(self) -> list[dict]:
        """Return all papers from the manifest."""
        return self.manifest.list_all()

    def read_markdown(self, paper_id: str, max_chars: int | None = None) -> str | None:
        """Read a paper.md file, optionally truncated."""
        md_path = self.markdown_path(paper_id)
        if not md_path.exists():
            logger.warning(f"paper.md does not exist: {paper_id}")
            return None
        content = md_path.read_text(encoding="utf-8")
        if max_chars and len(content) > max_chars:
            content = content[:max_chars] + "\n\n...(truncated)"
        return content

    def list_images(self, paper_id: str) -> list[str]:
        """Return image file names for a paper."""
        img_dir = self.images_dir(paper_id)
        if not img_dir.is_dir():
            return []
        return sorted([f.name for f in img_dir.iterdir() if f.is_file()])

    def read_multiple(
        self, paper_ids: list[str], max_chars_each: int | None = None
    ) -> dict[str, str]:
        """Read multiple papers, skipping missing files."""
        out = {}
        for pid in paper_ids:
            md = self.read_markdown(pid, max_chars=max_chars_each)
            if md is not None:
                out[pid] = md
        return out
