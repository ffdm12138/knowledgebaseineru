"""Paper ID migration service — plan, validate, apply paper_id renames.

Key principles:
- Default dry-run, never mutate without --apply
- Backup all indexes before mutation
- Atomic directory renames
- Transaction markers for recovery
- Full index synchronization (manifest, catalog, library_index, domain catalogs, bib)
"""
from __future__ import annotations

import json
import os
import shutil
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from config.settings import (
    CATALOG_PATH,
    DOMAIN_CATALOG_DIR,
    LIBRARY_INDEX_PATH,
    MANIFEST_PATH,
    PAPERS_DIR,
    RAW_DIR,
)
from src.catalog import Catalog
from src.library_index import VALID_DOMAINS, LibraryIndex
from src.manifest import PaperManifest
from src.naming import safe_child, validate_paper_id
from src.services.metadata_enrichment_service import (
    EnrichmentResult,
    looks_like_bad_paper_id,
    enrich_from_doi,
    normalize_bibliographic_metadata,
    extract_doi_from_sidecar,
    extract_doi_from_paper_md,
)
from src.services.paper_id import generate_paper_id
from src.utils.atomic_io import atomic_write_json

BACKUP_ROOT = Path("data/backups/paper_id_repair")
TRANSACTIONS_DIR = Path("data/transactions/paper_id_repair")


@dataclass
class MigrationPlan:
    old_paper_id: str
    new_paper_id: str = ""
    doi: str = ""
    title: str = ""
    year: int | None = None
    authors: list[str] = field(default_factory=list)
    first_author: str = ""
    domains: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    warnings: list[str] = field(default_factory=list)
    apply: bool = True  # user can set to False in mapping file to skip

    def to_dict(self) -> dict:
        return {
            "old_paper_id": self.old_paper_id,
            "new_paper_id": self.new_paper_id,
            "doi": self.doi,
            "title": self.title,
            "year": self.year,
            "authors": self.authors,
            "first_author": self.first_author,
            "domains": self.domains,
            "confidence": self.confidence,
            "reason": self.reason,
            "warnings": self.warnings,
            "apply": self.apply,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MigrationPlan":
        return cls(
            old_paper_id=data.get("old_paper_id", ""),
            new_paper_id=data.get("new_paper_id", ""),
            doi=data.get("doi", ""),
            title=data.get("title", ""),
            year=data.get("year"),
            authors=list(data.get("authors") or []),
            first_author=data.get("first_author", ""),
            domains=list(data.get("domains") or []),
            confidence=float(data.get("confidence", 0)),
            reason=data.get("reason", ""),
            warnings=list(data.get("warnings") or []),
            apply=bool(data.get("apply", True)),
        )


class PaperIdMigrationService:
    """Plan, validate, and apply paper_id migrations."""

    def __init__(
        self,
        manifest_path: Path = MANIFEST_PATH,
        catalog_path: Path = CATALOG_PATH,
        index_path: Path = LIBRARY_INDEX_PATH,
        domain_dir: Path = DOMAIN_CATALOG_DIR,
        papers_dir: Path = PAPERS_DIR,
        raw_dir: Path = RAW_DIR,
        backup_root: Path = BACKUP_ROOT,
        transactions_dir: Path = TRANSACTIONS_DIR,
    ):
        self.manifest_path = manifest_path
        self.catalog_path = catalog_path
        self.index_path = index_path
        self.domain_dir = domain_dir
        self.papers_dir = papers_dir
        self.raw_dir = raw_dir
        self.backup_root = backup_root
        self.transactions_dir = transactions_dir
        self._manifest = PaperManifest(manifest_path)
        self._catalog = Catalog(catalog_path)
        self._index = LibraryIndex(index_path)

    # ── Scanning ───────────────────────────────────────────────────────

    def _collect_all_paper_ids(self) -> set[str]:
        """Collect all paper_ids from all fact sources."""
        ids: set[str] = set()
        for p in self._manifest.list_all():
            pid = p.get("paper_id", "")
            if pid:
                ids.add(pid)
        for p in self._catalog.list_papers():
            pid = p.get("paper_id", "")
            if pid:
                ids.add(pid)
        for p in self._index.list_all():
            pid = p.get("paper_id", "")
            if pid:
                ids.add(pid)
        # Also scan data/papers/ directories
        if self.papers_dir.exists():
            for d in self.papers_dir.iterdir():
                if d.is_dir() and not d.name.startswith("."):
                    ids.add(d.name)
        return ids

    def _get_catalog_entry(self, paper_id: str) -> dict | None:
        return self._catalog.get(paper_id)

    def _get_manifest_entry(self, paper_id: str) -> dict | None:
        return self._manifest.get(paper_id)

    def _get_index_entry(self, paper_id: str) -> dict | None:
        return self._index.get(paper_id)

    def _find_doi_for_paper(self, paper_id: str) -> str:
        """Find the best DOI for a paper from all fact sources."""
        # catalog
        cat = self._get_catalog_entry(paper_id)
        if cat and cat.get("doi"):
            return cat["doi"]
        # index
        idx = self._get_index_entry(paper_id)
        if idx and idx.get("doi"):
            return idx["doi"]
        # manifest may have doi in metadata
        mf = self._get_manifest_entry(paper_id)
        if mf and mf.get("doi"):
            return mf["doi"]
        # Try paper.md
        paper_md = self.papers_dir / paper_id / "paper.md"
        if paper_md.exists():
            try:
                text = paper_md.read_text(encoding="utf-8")
                doi = extract_doi_from_paper_md(text)
                if doi:
                    return doi
            except Exception:
                pass
        return ""

    def _get_title_for_paper(self, paper_id: str) -> str:
        cat = self._get_catalog_entry(paper_id)
        if cat:
            return cat.get("title", "")
        idx = self._get_index_entry(paper_id)
        if idx:
            return idx.get("title", "")
        return ""

    def _get_year_for_paper(self, paper_id: str) -> int | None:
        cat = self._get_catalog_entry(paper_id)
        if cat and cat.get("year") is not None:
            return cat["year"]
        idx = self._get_index_entry(paper_id)
        if idx and idx.get("year") is not None:
            return idx["year"]
        return None

    def _get_domains_for_paper(self, paper_id: str) -> list[str]:
        cat = self._get_catalog_entry(paper_id)
        if cat:
            return list(cat.get("domains") or [])
        idx = self._get_index_entry(paper_id)
        if idx:
            return list(idx.get("domains") or [])
        return []

    # ── Planning ───────────────────────────────────────────────────────

    def plan_migrations(
        self,
        domain: str = "",
        paper_ids: list[str] | None = None,
        query_crossref: bool = False,
    ) -> list[MigrationPlan]:
        """Scan all papers and produce a migration plan.

        Args:
            domain: If set, only scan papers in this domain.
            paper_ids: If set, only scan these specific paper_ids.
            query_crossref: If True, query Crossref API for DOI metadata.
        """
        all_ids = self._collect_all_paper_ids()
        if paper_ids:
            all_ids = all_ids & set(paper_ids)
        plans: list[MigrationPlan] = []

        for paper_id in sorted(all_ids):
            is_bad, reason = looks_like_bad_paper_id(paper_id)
            if not is_bad:
                continue

            plan = MigrationPlan(old_paper_id=paper_id, reason=reason)
            plan.domains = self._get_domains_for_paper(paper_id)
            plan.title = self._get_title_for_paper(paper_id)
            plan.year = self._get_year_for_paper(paper_id)
            plan.doi = self._find_doi_for_paper(paper_id)

            # Try enrichment
            if plan.doi and query_crossref:
                enriched = enrich_from_doi(plan.doi)
                plan.title = enriched.title or plan.title
                plan.year = enriched.year or plan.year
                plan.authors = enriched.authors or plan.authors
                plan.first_author = enriched.first_author or plan.first_author
                plan.confidence = enriched.confidence
                plan.warnings = enriched.warnings

            # Generate new paper_id
            plan.new_paper_id = generate_paper_id(
                year=plan.year,
                title=plan.title,
                authors=[plan.first_author] if plan.first_author else None,
            )

            # Check conflicts
            if plan.new_paper_id == plan.old_paper_id:
                plan.warnings.append("new_paper_id same as old; skipping")
                plan.apply = False
            elif plan.new_paper_id in all_ids:
                # Check if same DOI
                existing_doi = self._find_doi_for_paper(plan.new_paper_id)
                if plan.doi and existing_doi and plan.doi.lower() == existing_doi.lower():
                    plan.warnings.append(
                        f"new_paper_id {plan.new_paper_id} already exists with same DOI; "
                        f"merge candidate (not auto-merged)"
                    )
                    plan.apply = False
                else:
                    plan.warnings.append(
                        f"new_paper_id {plan.new_paper_id} already exists; conflict"
                    )
                    plan.apply = False

            if not plan.warnings or any("DO" not in w for w in plan.warnings):
                pass  # keep going

            plans.append(plan)

        return plans

    def validate_migrations(self, plans: list[MigrationPlan]) -> list[str]:
        """Validate a list of MigrationPlan objects. Returns errors."""
        errors: list[str] = []
        seen_new = set()
        seen_old = set()
        existing_ids = self._collect_all_paper_ids()

        for plan in plans:
            if not plan.apply:
                continue
            if plan.old_paper_id in seen_old:
                errors.append(f"duplicate old_paper_id in plan: {plan.old_paper_id}")
            seen_old.add(plan.old_paper_id)

            if plan.new_paper_id in seen_new:
                errors.append(f"duplicate new_paper_id in plan: {plan.new_paper_id}")
            seen_new.add(plan.new_paper_id)

            # Validate new_paper_id format
            try:
                validate_paper_id(plan.new_paper_id)
            except ValueError as e:
                errors.append(f"invalid new_paper_id {plan.new_paper_id}: {e}")

            # Check old exists
            if plan.old_paper_id not in existing_ids:
                errors.append(f"old_paper_id not found in any fact source: {plan.old_paper_id}")

            # Check new doesn't exist (unless same DOI merge, which we skip)
            if plan.new_paper_id in existing_ids and plan.new_paper_id != plan.old_paper_id:
                errors.append(
                    f"new_paper_id {plan.new_paper_id} already exists; "
                    f"cannot migrate {plan.old_paper_id}"
                )

        return errors

    def load_mapping(self, mapping_path: str | Path) -> list[MigrationPlan]:
        """Load migration plans from a mapping JSON file."""
        mapping_path = Path(mapping_path)
        data = json.loads(mapping_path.read_text(encoding="utf-8"))
        plans = []
        for item in data.get("migrations", []):
            plan = MigrationPlan.from_dict(item)
            plans.append(plan)
        return plans

    def export_mapping(self, plans: list[MigrationPlan], output_path: str | Path) -> None:
        """Export migration plans to a mapping JSON file for human review."""
        output_path = Path(output_path)
        data = {
            "description": "Paper ID repair mapping — review and set apply=true/false before running --apply",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "migrations": [p.to_dict() for p in plans],
        }
        atomic_write_json(output_path, data, indent=2)

    # ── Backup ─────────────────────────────────────────────────────────

    def _backup_timestamp(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def backup_indexes(self) -> Path:
        """Create a timestamped backup of all index files. Returns backup dir."""
        ts = self._backup_timestamp()
        backup_dir = self.backup_root / ts
        backup_dir.mkdir(parents=True, exist_ok=True)
        files_to_backup = [
            self.manifest_path,
            self.catalog_path,
            self.index_path,
        ]
        # Domain catalogs and bibs
        if self.domain_dir.exists():
            for domain_dir in self.domain_dir.iterdir():
                if domain_dir.is_dir():
                    for fname in ("literature_catalog.json", "references.bib"):
                        fp = domain_dir / fname
                        if fp.exists():
                            files_to_backup.append(fp)

        for fp in files_to_backup:
            if fp.exists():
                dest = backup_dir / fp.relative_to(fp.anchor) if fp.is_absolute() else backup_dir / fp.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fp, dest)

        # Copy domain structure
        if self.domain_dir.exists():
            domain_backup = backup_dir / "domains"
            domain_backup.mkdir(parents=True, exist_ok=True)
            for item in self.domain_dir.iterdir():
                if item.is_dir():
                    dest_dir = domain_backup / item.name
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    for fname in ("literature_catalog.json", "references.bib"):
                        fp = item / fname
                        if fp.exists():
                            shutil.copy2(fp, dest_dir / fname)

        logger.info(f"Indexes backed up to {backup_dir}")
        return backup_dir

    # ── Apply ──────────────────────────────────────────────────────────

    def apply_migration(self, plan: MigrationPlan) -> dict:
        """Apply a single paper_id migration. Returns result dict."""
        result = {
            "old_paper_id": plan.old_paper_id,
            "new_paper_id": plan.new_paper_id,
            "success": False,
            "moved_dir": False,
            "manifest_updated": False,
            "catalog_updated": False,
            "index_updated": False,
            "domain_views_updated": False,
            "errors": [],
        }

        old_id = plan.old_paper_id
        new_id = plan.new_paper_id

        try:
            # 1. Rename paper directory
            old_dir = safe_child(self.papers_dir, old_id)
            new_dir = safe_child(self.papers_dir, new_id)
            if old_dir.exists() and not new_dir.exists():
                # Use intermediate rename for safety
                temp_dir = safe_child(self.papers_dir, f".renaming_{old_id}_to_{new_id}")
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                shutil.move(str(old_dir), str(temp_dir))
                shutil.move(str(temp_dir), str(new_dir))
                result["moved_dir"] = True

            # 2. Update manifest
            manifest_updated = [False]

            def _update_manifest(data):
                for entry in data.get("papers", []):
                    if entry.get("paper_id") == old_id:
                        entry["paper_id"] = new_id
                        entry["markdown"] = _normalize_path(str(new_dir / "paper.md"))
                        entry["images_dir"] = _normalize_path(str(new_dir / "images"))
                        for field in ("raw_filename", "raw_stem"):
                            val = str(entry.get(field, ""))
                            if val and val.startswith(old_id):
                                entry[field] = val.replace(old_id, new_id, 1)
                        manifest_updated[0] = True
                        return

            self._manifest._locked_update(_update_manifest)
            result["manifest_updated"] = manifest_updated[0]

            # 3. Update catalog
            cat = self._catalog.load()
            for p in cat.get("papers", []):
                if p.get("paper_id") == old_id:
                    p["paper_id"] = new_id
                    p["markdown"] = _normalize_path(str(new_dir / "paper.md"))
                    p["images_dir"] = _normalize_path(str(new_dir / "images"))
                    result["catalog_updated"] = True
                    break
            self._catalog.save(cat)

            # 4. Update library_index
            idx = self._index.load()
            for entry in idx.get("papers", []):
                if entry.get("paper_id") == old_id:
                    entry["paper_id"] = new_id
                    entry["markdown_path"] = _normalize_path(str(new_dir / "paper.md"))
                    entry["images_dir"] = _normalize_path(str(new_dir / "images"))
                    result["index_updated"] = True
                    break
            self._index.save(idx)

            # 5. Update domain catalogs + bibs
            if result["catalog_updated"]:
                self._rebuild_domain_views()
                result["domain_views_updated"] = True

            result["success"] = any([
                result["moved_dir"],
                result["manifest_updated"],
                result["catalog_updated"],
                result["index_updated"],
            ])
        except Exception as exc:
            result["errors"].append(str(exc))
            logger.error(f"Migration failed for {old_id} -> {new_id}: {exc}")

        return result

    def apply_migrations(
        self,
        plans: list[MigrationPlan],
        *,
        backup: bool = True,
    ) -> dict:
        """Apply a list of migrations with backup and transaction tracking.

        Returns summary dict with per-migration results.
        """
        ts = self._backup_timestamp()
        transactions_dir = self.transactions_dir / ts
        transactions_dir.mkdir(parents=True, exist_ok=True)

        # Validate first
        errors = self.validate_migrations(plans)
        if errors:
            return {"success": False, "error": "validation failed", "validation_errors": errors}

        active_plans = [p for p in plans if p.apply]
        if not active_plans:
            return {"success": True, "message": "no migrations to apply (all apply=False)", "results": []}

        # Backup
        backup_dir = None
        if backup:
            backup_dir = self.backup_indexes()

        # Transaction marker
        tx_path = transactions_dir / "transaction.json"
        tx_data = {
            "status": "started",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "backup_dir": str(backup_dir) if backup_dir else "",
            "migrations": [p.to_dict() for p in active_plans],
            "errors": [],
        }
        atomic_write_json(tx_path, tx_data, indent=2)

        results = []
        all_ok = True
        for plan in active_plans:
            result = self.apply_migration(plan)
            results.append(result)
            if not result["success"]:
                all_ok = False
                tx_data["errors"].append(
                    f"{plan.old_paper_id}: {result['errors']}"
                )

        # Final transaction marker
        tx_data["status"] = "completed" if all_ok else "failed"
        tx_data["completed_at"] = datetime.now().isoformat(timespec="seconds")
        atomic_write_json(tx_path, tx_data, indent=2)

        if not all_ok:
            logger.error(
                f"Migration partially failed. Backups at {backup_dir}. "
                f"Transaction log at {tx_path}. Review errors and restore if needed."
            )

        # Save applied mapping
        mapping_path = transactions_dir / "repair_mapping_applied.json"
        self.export_mapping(active_plans, mapping_path)

        return {
            "success": all_ok,
            "results": results,
            "backup_dir": str(backup_dir) if backup_dir else "",
            "transaction_path": str(tx_path),
            "applied_count": sum(1 for r in results if r["success"]),
            "failed_count": sum(1 for r in results if not r["success"]),
        }

    def _rebuild_domain_views(self):
        """Rebuild domain catalogs and bibs from current catalog + manifest."""
        from src.services.domain_library_service import build_domain_library, apply_domain_library

        cat_data = self._catalog.load()
        mfst_data = self._manifest._load()
        updated_cat, lib_idx, domain_cats, domain_bibs, global_bib = build_domain_library(
            cat_data, mfst_data
        )
        apply_domain_library(
            updated_cat, lib_idx, domain_cats, domain_bibs, global_bib,
            catalog_path=self.catalog_path,
            index_path=self.index_path,
            domain_dir=self.domain_dir,
        )

    # ── Single rename ──────────────────────────────────────────────────

    def rename_single(self, old_id: str, new_id: str, *, backup: bool = True) -> dict:
        """Directly rename a single paper_id (with validation and backup)."""
        plan = MigrationPlan(
            old_paper_id=old_id,
            new_paper_id=new_id,
            reason="manual rename",
        )
        return self.apply_migrations([plan], backup=backup)


def _normalize_path(path: str) -> str:
    """Convert a path to normalized repo-relative form."""
    from src.path_utils import normalize_repo_path
    return normalize_repo_path(path)
