"""Audit manifest/catalog/library_index consistency without modifying data."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import (
    CATALOG_PATH,
    DOMAIN_CATALOG_DIR,
    LIBRARY_INDEX_PATH,
    MANIFEST_PATH,
)
from src.path_utils import is_windows_abs_path, resolve_stored_path


PATH_FIELDS = ("raw_pdf", "markdown", "markdown_path", "images_dir", "pending_pdf")
READABLE_MANIFEST_STATUSES = {"converted"}
UNREGISTERED_STATUSES = {"unregistered", "unregistered_converted"}
CATALOG_NONREADABLE_STATUSES = {"asset_missing", "conversion_failed_with_catalog"}


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _papers_by_id(data: dict) -> dict[str, dict]:
    return {p.get("paper_id", ""): p for p in data.get("papers", []) if p.get("paper_id")}


def _norm_doi(value: str) -> str:
    return (value or "").strip().lower()


def _norm_title(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _path_items(source: str, paper: dict) -> list[dict]:
    out = []
    pid = paper.get("paper_id", "")
    for field in PATH_FIELDS:
        value = paper.get(field)
        if isinstance(value, str) and value:
            out.append({"source": source, "paper_id": pid, "field": field, "path": value})
    return out


def _duplicate_map(rows: list[tuple[str, str]], *, min_len: int = 2) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for key, pid in rows:
        if key:
            grouped[key].append(pid)
    return {
        key: sorted(set(pids))
        for key, pids in sorted(grouped.items())
        if len(set(pids)) >= min_len
    }


def audit_library(
    manifest_path: Path = MANIFEST_PATH,
    catalog_path: Path = CATALOG_PATH,
    index_path: Path = LIBRARY_INDEX_PATH,
    domain_dir: Path = DOMAIN_CATALOG_DIR,
    check_paths: bool = False,
    strict: bool = False,
) -> dict:
    manifest = _load_json(manifest_path, {"papers": []})
    catalog = _load_json(catalog_path, {"papers": []})
    library_index = _load_json(index_path, {"papers": []})

    manifest_by_id = _papers_by_id(manifest)
    catalog_by_id = _papers_by_id(catalog)
    index_by_id = _papers_by_id(library_index)

    manifest_ids = set(manifest_by_id)
    catalog_ids = set(catalog_by_id)
    index_ids = set(index_by_id)

    converted_manifest_ids = {
        pid for pid, p in manifest_by_id.items() if p.get("status") == "converted"
    }
    unregistered_manifest_ids = {
        pid
        for pid, p in manifest_by_id.items()
        if p.get("status") in UNREGISTERED_STATUSES or p.get("unregistered") is True
    }
    catalog_entries_with_nonreadable_manifest = sorted(
        pid
        for pid in catalog_ids & manifest_ids
        if manifest_by_id[pid].get("status") in CATALOG_NONREADABLE_STATUSES
    )

    catalog_entries_without_manifest = sorted(catalog_ids - manifest_ids)
    catalog_entries_with_manifest_status_not_converted = sorted(
        pid
        for pid in catalog_ids & manifest_ids
        if manifest_by_id[pid].get("status") not in READABLE_MANIFEST_STATUSES
        and manifest_by_id[pid].get("status") not in CATALOG_NONREADABLE_STATUSES
    )
    manifest_converted_without_catalog = sorted(converted_manifest_ids - catalog_ids)
    manifest_failed_with_existing_catalog = sorted(
        pid
        for pid in catalog_ids & manifest_ids
        if manifest_by_id[pid].get("status") == "failed"
    )

    duplicate_sha256 = _duplicate_map(
        [
            ((p.get("sha256") or "").strip().lower(), pid)
            for pid, p in manifest_by_id.items()
            if p.get("status") in READABLE_MANIFEST_STATUSES | {"unregistered_converted"}
        ]
    )
    duplicate_doi = _duplicate_map(
        [(_norm_doi(p.get("doi", "")), pid) for pid, p in catalog_by_id.items()]
    )
    duplicate_title_year = _duplicate_map(
        [
            (f"{p.get('year')}::{_norm_title(p.get('title', ''))}", pid)
            for pid, p in catalog_by_id.items()
            if p.get("year") and _norm_title(p.get("title", ""))
        ]
    )

    path_records = []
    for pid, paper in manifest_by_id.items():
        path_records.extend(_path_items("manifest", paper))
    for pid, paper in catalog_by_id.items():
        path_records.extend(_path_items("catalog", paper))
    for pid, paper in index_by_id.items():
        path_records.extend(_path_items("library_index", paper))

    domain_catalogs = {}
    if domain_dir.exists():
        for path in sorted(domain_dir.glob("*/literature_catalog.json")):
            domain_id = path.parent.name
            data = _load_json(path, {"papers": []})
            domain_catalogs[domain_id] = len(data.get("papers", []))
            for paper in data.get("papers", []):
                path_records.extend(_path_items(f"domain:{domain_id}", paper))

    windows_absolute_paths = [
        item for item in path_records if is_windows_abs_path(item["path"])
    ]
    backslash_paths = [
        item
        for item in path_records
        if "\\" in item["path"] and not is_windows_abs_path(item["path"])
    ]

    missing_raw_pdf = []
    missing_markdown = []
    missing_images_dir = []
    if check_paths:
        for item in path_records:
            field = item["field"]
            if field not in {"raw_pdf", "markdown", "markdown_path", "images_dir"}:
                continue
            if not resolve_stored_path(item["path"]).exists():
                if field == "raw_pdf":
                    missing_raw_pdf.append(item)
                elif field in {"markdown", "markdown_path"}:
                    missing_markdown.append(item)
                elif field == "images_dir":
                    missing_images_dir.append(item)

    strict_errors = []
    if catalog_ids != index_ids:
        strict_errors.append("catalog/index paper_ids differ")
    if catalog_entries_without_manifest:
        strict_errors.append("catalog entries without manifest")
    if catalog_entries_with_manifest_status_not_converted:
        strict_errors.append("catalog entries with manifest status not converted")
    converted_registered_gap = sorted(set(manifest_converted_without_catalog) - unregistered_manifest_ids)
    if converted_registered_gap:
        strict_errors.append("manifest converted without catalog")
    if duplicate_sha256:
        strict_errors.append("duplicate sha256 among converted manifest papers")
    if duplicate_doi:
        strict_errors.append("duplicate DOI in catalog")

    return {
        "manifest_count": len(manifest_by_id),
        "catalog_count": len(catalog_by_id),
        "library_index_count": len(index_by_id),
        "domain_catalog_counts": domain_catalogs,
        "manifest_only_paper_ids": sorted(manifest_ids - catalog_ids - index_ids),
        "catalog_only_paper_ids": sorted(catalog_ids - manifest_ids - index_ids),
        "index_only_paper_ids": sorted(index_ids - manifest_ids - catalog_ids),
        "catalog_entries_without_manifest": catalog_entries_without_manifest,
        "catalog_entries_with_manifest_status_not_converted": (
            catalog_entries_with_manifest_status_not_converted
        ),
        "catalog_entries_with_nonreadable_manifest": catalog_entries_with_nonreadable_manifest,
        "manifest_converted_without_catalog": manifest_converted_without_catalog,
        "unregistered_manifest_ids": sorted(unregistered_manifest_ids),
        "unregistered_papers_count": len(unregistered_manifest_ids),
        "manifest_failed_with_existing_catalog": manifest_failed_with_existing_catalog,
        "duplicate_sha256": duplicate_sha256,
        "duplicate_doi": duplicate_doi,
        "duplicate_title_year": duplicate_title_year,
        "windows_absolute_paths": windows_absolute_paths,
        "backslash_paths": backslash_paths,
        "missing_raw_pdf": missing_raw_pdf,
        "missing_markdown": missing_markdown,
        "missing_images_dir": missing_images_dir,
        "check_paths": check_paths,
        "strict": strict,
        "strict_errors": strict_errors if strict else [],
        "ok": not strict_errors if strict else True,
    }


def _print_text(report: dict) -> None:
    logger.info(
        "counts: manifest={} catalog={} library_index={}",
        report["manifest_count"],
        report["catalog_count"],
        report["library_index_count"],
    )
    for key in (
        "manifest_only_paper_ids",
        "catalog_only_paper_ids",
        "index_only_paper_ids",
        "catalog_entries_without_manifest",
        "catalog_entries_with_manifest_status_not_converted",
        "manifest_converted_without_catalog",
        "catalog_entries_with_nonreadable_manifest",
        "unregistered_manifest_ids",
        "manifest_failed_with_existing_catalog",
    ):
        values = report[key]
        if values:
            logger.warning("{}: {}", key, values)
    for key in ("duplicate_sha256", "duplicate_doi", "duplicate_title_year"):
        values = report[key]
        if values:
            logger.warning("{}: {}", key, values)
    for key in ("windows_absolute_paths", "backslash_paths"):
        if report[key]:
            logger.warning("{}: {} entries", key, len(report[key]))
    for key in ("missing_raw_pdf", "missing_markdown", "missing_images_dir"):
        if report[key]:
            logger.warning("{}: {} entries", key, len(report[key]))
    if report["strict_errors"]:
        logger.error("strict errors: {}", report["strict_errors"])
    elif report["strict"]:
        logger.info("strict audit passed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit library fact-source consistency.")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    parser.add_argument("--index", type=Path, default=LIBRARY_INDEX_PATH)
    parser.add_argument("--domain-dir", type=Path, default=DOMAIN_CATALOG_DIR)
    parser.add_argument("--json", action="store_true", help="print structured JSON")
    parser.add_argument("--check-paths", action="store_true", help="check path existence")
    parser.add_argument("--strict", action="store_true", help="fail on core consistency issues")
    args = parser.parse_args()

    report = audit_library(
        manifest_path=args.manifest,
        catalog_path=args.catalog,
        index_path=args.index,
        domain_dir=args.domain_dir,
        check_paths=args.check_paths,
        strict=args.strict,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
