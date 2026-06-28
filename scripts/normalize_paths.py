"""Normalize persisted JSON path fields to repo-relative POSIX paths."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import (
    CATALOG_PATH,
    DOMAIN_CATALOG_DIR,
    LIBRARY_INDEX_PATH,
    MANIFEST_PATH,
    PROJECT_ROOT,
)
from src.path_utils import normalize_record_paths


PATH_FIELDS = ("raw_pdf", "markdown", "markdown_path", "images_dir", "pending_pdf")


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {"papers": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    os.replace(tmp, path)


def _backup(path: Path, timestamp: str) -> Path:
    backup = path.with_name(f"{path.name}.bak_{timestamp}")
    shutil.copy2(path, backup)
    return backup


def normalize_json_data(data: dict, project_root: Path = PROJECT_ROOT) -> tuple[dict, list[dict]]:
    """Normalize path fields in a JSON object containing ``papers``."""
    updated = deepcopy(data)
    changes = []
    papers = updated.get("papers", [])
    if not isinstance(papers, list):
        return updated, changes
    for paper in papers:
        before = dict(paper)
        normalized = normalize_record_paths(before, fields=PATH_FIELDS, project_root=project_root)
        for field in PATH_FIELDS:
            old = before.get(field)
            new = normalized.get(field)
            if old and new and old != new:
                changes.append({
                    "paper_id": before.get("paper_id", ""),
                    "field": field,
                    "old": old,
                    "new": new,
                })
                paper[field] = new
    return updated, changes


def normalize_path_files(
    files: list[Path],
    project_root: Path = PROJECT_ROOT,
    apply: bool = False,
) -> dict:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {"apply": apply, "files": []}
    for path in files:
        if not path.exists():
            continue
        data = _load_json(path)
        normalized, changes = normalize_json_data(data, project_root=project_root)
        item = {
            "path": str(path),
            "changed": bool(changes),
            "changes": changes,
            "backup": "",
        }
        if apply and changes:
            item["backup"] = str(_backup(path, timestamp))
            _atomic_write_json(path, normalized)
        report["files"].append(item)
    return report


def collect_default_files(
    manifest_path: Path = MANIFEST_PATH,
    catalog_path: Path = CATALOG_PATH,
    index_path: Path = LIBRARY_INDEX_PATH,
    domain_dir: Path = DOMAIN_CATALOG_DIR,
) -> list[Path]:
    files = [manifest_path, catalog_path, index_path]
    if domain_dir.exists():
        files.extend(sorted(domain_dir.glob("*/literature_catalog.json")))
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize stored JSON path fields.")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    parser.add_argument("--index", type=Path, default=LIBRARY_INDEX_PATH)
    parser.add_argument("--domain-dir", type=Path, default=DOMAIN_CATALOG_DIR)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--apply", action="store_true", help="write changes; default is dry-run")
    parser.add_argument("--json", action="store_true", help="print JSON report")
    args = parser.parse_args()

    files = collect_default_files(args.manifest, args.catalog, args.index, args.domain_dir)
    report = normalize_path_files(files, project_root=args.project_root, apply=args.apply)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        changed = sum(1 for item in report["files"] if item["changed"])
        logger.info("{} files scanned; {} files need path normalization", len(report["files"]), changed)
        for item in report["files"]:
            if item["changed"]:
                logger.info("{}: {} changes", item["path"], len(item["changes"]))
                if item["backup"]:
                    logger.info("backup: {}", item["backup"])
        if not args.apply:
            logger.info("dry-run only; pass --apply to write backups and normalized JSON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
