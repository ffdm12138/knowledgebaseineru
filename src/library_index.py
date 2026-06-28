"""Domain-aware global paper registry.

library_index.json is a path/domain registry. It complements the root
literature_catalog.json, which remains the AI-readable paper summary catalog.
"""
import json
import os
from pathlib import Path
from typing import Iterable

from filelock import FileLock

from config.settings import DATA_DIR, LIBRARY_INDEX_PATH
from src.domain_config import DOMAIN_LABELS, DOMAIN_REGISTRY, VALID_DOMAINS
from src.path_utils import normalize_repo_path, resolve_stored_path


PROJECT_ROOT = DATA_DIR.parent

def normalize_rel_path(path: str | Path) -> str:
    """Return a stable repo-relative POSIX path when possible."""
    return normalize_repo_path(path, project_root=PROJECT_ROOT)


def resolve_repo_path(path: str | Path) -> Path:
    """Resolve stored paths without rewriting Windows absolute paths."""
    return resolve_stored_path(path, project_root=PROJECT_ROOT)


def validate_domains(primary_domain: str, domains: Iterable[str] | None) -> list[str]:
    """Validate domain fields and return errors without raising."""
    errors = []
    if not primary_domain:
        errors.append("primary_domain is empty")
    elif primary_domain not in VALID_DOMAINS:
        errors.append(f"invalid primary_domain: {primary_domain}")

    if not isinstance(domains, list) or not domains:
        errors.append("domains must be a non-empty list")
        domain_list = []
    else:
        domain_list = domains

    for domain_id in domain_list:
        if domain_id not in VALID_DOMAINS:
            errors.append(f"invalid domain: {domain_id}")
    if primary_domain and domain_list and primary_domain not in domain_list:
        errors.append(f"primary_domain {primary_domain} not in domains")
    return errors


def _catalog_path_first(catalog_entry: dict, manifest_entry: dict, field: str) -> str:
    """Prefer root catalog paths; use manifest only as a supplement."""
    value = catalog_entry.get(field) or manifest_entry.get(field) or ""
    return normalize_rel_path(value)


class LibraryIndex:
    """Read/write/query data/catalog/library_index.json."""

    def __init__(self, path: Path = LIBRARY_INDEX_PATH):
        self.path = Path(path)

    @property
    def _lock_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".lock")

    @staticmethod
    def empty_data() -> dict:
        return {
            "version": "0.1",
            "description": "Global paper registry for domain-aware library layout.",
            "domains": DOMAIN_REGISTRY,
            "papers": [],
        }

    def load(self) -> dict:
        if not self.path.exists():
            return self.empty_data()
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(self._lock_path))
        with lock:
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            json.loads(tmp.read_text(encoding="utf-8"))
            os.replace(tmp, self.path)

    def list_all(self) -> list[dict]:
        return self.load().get("papers", [])

    def list_papers(self) -> list[dict]:
        return self.list_all()

    def get(self, paper_id: str) -> dict | None:
        for entry in self.list_all():
            if entry.get("paper_id") == paper_id:
                return entry
        return None

    def find_by_doi(self, doi: str) -> dict | None:
        """按 DOI 查找 canonical 记录（DOI 规范化后精确匹配）。"""
        target = (doi or "").strip().lower()
        if not target:
            return None
        for entry in self.list_all():
            if (entry.get("doi") or "").strip().lower() == target:
                return entry
        return None

    def upsert(self, entry: dict) -> None:
        data = self.load()
        papers = data.get("papers", [])
        for i, existing in enumerate(papers):
            if existing.get("paper_id") == entry.get("paper_id"):
                papers[i] = entry
                break
        else:
            papers.append(entry)
        data["papers"] = papers
        self.save(data)

    def delete(self, paper_id: str) -> bool:
        data = self.load()
        papers = data.get("papers", [])
        kept = [p for p in papers if p.get("paper_id") != paper_id]
        if len(kept) == len(papers):
            return False
        data["papers"] = kept
        self.save(data)
        return True

    @staticmethod
    def build_from_catalog_and_manifest(catalog: dict, manifest: dict) -> dict:
        manifest_by_id = {p.get("paper_id"): p for p in manifest.get("papers", [])}
        papers = []
        for catalog_entry in catalog.get("papers", []):
            paper_id = catalog_entry.get("paper_id", "")
            manifest_entry = manifest_by_id.get(paper_id, {})
            citation = catalog_entry.get("citation") or {}
            papers.append({
                "paper_id": paper_id,
                "title": catalog_entry.get("title", ""),
                "year": catalog_entry.get("year"),
                "doi": catalog_entry.get("doi", ""),
                "primary_domain": catalog_entry.get("primary_domain", ""),
                "domains": list(catalog_entry.get("domains") or []),
                "raw_pdf": _catalog_path_first(catalog_entry, manifest_entry, "raw_pdf"),
                "markdown_path": _catalog_path_first(catalog_entry, manifest_entry, "markdown"),
                "images_dir": _catalog_path_first(catalog_entry, manifest_entry, "images_dir"),
                "status": catalog_entry.get("status", ""),
                "bib_key": citation.get("bib_key", ""),
            })
        return {
            "version": "0.1",
            "description": "Global paper registry for domain-aware library layout.",
            "domains": DOMAIN_REGISTRY,
            "papers": papers,
        }

    def validate(self, check_paths: bool = False) -> list[str]:
        """Return fatal validation errors.

        Missing markdown files are intentionally not fatal by default because
        data/papers is ignored in snapshots.
        """
        data = self.load()
        errors = []
        if data.get("domains") != DOMAIN_REGISTRY:
            errors.append("domains registry does not match code registry")
        papers = data.get("papers", [])
        if not isinstance(papers, list):
            return ["papers must be a list"]

        seen_ids = set()
        seen_doi = set()
        seen_bib = set()
        for i, entry in enumerate(papers):
            ctx = f"papers[{i}] paper_id={entry.get('paper_id', '?')}"
            paper_id = entry.get("paper_id")
            if not paper_id:
                errors.append(f"{ctx} missing paper_id")
            elif paper_id in seen_ids:
                errors.append(f"{ctx} duplicate paper_id")
            else:
                seen_ids.add(paper_id)

            errors.extend([
                f"{ctx} {err}"
                for err in validate_domains(entry.get("primary_domain", ""), entry.get("domains"))
            ])

            doi = (entry.get("doi") or "").strip().lower()
            if doi:
                if doi in seen_doi:
                    errors.append(f"{ctx} duplicate doi: {doi}")
                seen_doi.add(doi)

            bib_key = (entry.get("bib_key") or "").strip()
            if not bib_key:
                errors.append(f"{ctx} missing bib_key")
            elif bib_key in seen_bib:
                errors.append(f"{ctx} duplicate bib_key: {bib_key}")
            else:
                seen_bib.add(bib_key)

            markdown_path = entry.get("markdown_path") or ""
            if not markdown_path:
                errors.append(f"{ctx} missing markdown_path")
            elif check_paths and not resolve_repo_path(markdown_path).exists():
                errors.append(f"{ctx} markdown_path does not exist: {markdown_path}")
        return errors

    def path_warnings(self) -> list[str]:
        warnings = []
        for entry in self.list_all():
            markdown_path = entry.get("markdown_path") or ""
            if markdown_path and not resolve_repo_path(markdown_path).exists():
                warnings.append(
                    f"paper_id={entry.get('paper_id', '?')} markdown_path not found: {markdown_path}"
                )
        return warnings


def domain_for_paper(paper: dict) -> tuple[str, list[str]]:
    return paper.get("primary_domain") or "", list(paper.get("domains") or [])
