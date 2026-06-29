"""Validate v2 paper library structure."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import ALL_CATALOG_PATH, PAPERS_DIR
from src.path_utils import resolve_stored_path
from src.services.v2_library import (
    PaperNumberLedger,
    validate_catalog_schema,
    validate_metadata_schema,
)


def validate_v2_library(
    *,
    papers_dir: Path = PAPERS_DIR,
    all_catalog_path: Path = ALL_CATALOG_PATH,
    check_paths: bool = True,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    ledger_errors, ledger_warnings = PaperNumberLedger().validate(papers_dir)
    errors.extend(ledger_errors)
    warnings.extend(ledger_warnings)

    if papers_dir.exists():
        for folder in sorted(p for p in papers_dir.iterdir() if p.is_dir()):
            pid = folder.name
            required = {
                "metadata": folder / f"{pid}.metadata.json",
                "catalog": folder / f"{pid}.catalog.json",
                "md": folder / f"{pid}.md",
                "pdf": folder / f"{pid}.pdf",
                "images": folder / "images",
            }
            has_any_v2_asset = any(path.exists() for path in required.values())
            if (folder / "paper.md").exists():
                errors.append(f"{pid}: formal v2 library must not contain paper.md")
            if (folder / "output").exists():
                errors.append(f"{pid}: MinerU raw output must be removed before commit (delete output/)")
            for vestige in folder.glob("*.metadata.patch.json"):
                errors.append(f"{pid}: paper_raw transient file must not enter formal library: {vestige.name}")
            for vestige in folder.glob("*.tmp"):
                errors.append(f"{pid}: temporary file must not enter formal library: {vestige.name}")
            if (folder / "curation_prompt.md").exists():
                errors.append(f"{pid}: curation prompt must not enter formal library")
            if (folder / ".import_status.json").exists():
                errors.append(f"{pid}: import_status marker must not enter formal library")
            if not has_any_v2_asset:
                continue
            for name, path in required.items():
                if not path.exists():
                    errors.append(f"{pid} missing {name}: {path}")
            if required["metadata"].exists():
                metadata = json.loads(required["metadata"].read_text(encoding="utf-8"))
                errors.extend([f"{pid} {err}" for err in validate_metadata_schema(metadata)])
            if required["catalog"].exists():
                catalog = json.loads(required["catalog"].read_text(encoding="utf-8"))
                errors.extend([f"{pid} {err}" for err in validate_catalog_schema(catalog)])
            markers = list(folder.glob("*.paper.number"))
            if len(markers) > 1:
                errors.append(f"{pid} has multiple .paper.number files")

    if not all_catalog_path.exists():
        errors.append(f"missing all.catalog.json: {all_catalog_path}")
        return errors, warnings

    data = json.loads(all_catalog_path.read_text(encoding="utf-8"))
    seen_numbers: set[str] = set()
    seen_ids: set[str] = set()
    for i, entry in enumerate(data.get("papers", [])):
        ctx = f"papers[{i}]"
        number = entry.get("paper_number") or ""
        pid = entry.get("paper_id") or entry.get("folder_name") or ""
        if not number:
            errors.append(f"{ctx} missing paper_number")
        elif number in seen_numbers:
            errors.append(f"{ctx} duplicate paper_number: {number}")
        seen_numbers.add(number)
        if not pid:
            errors.append(f"{ctx} missing paper_id")
        elif pid in seen_ids:
            errors.append(f"{ctx} duplicate paper_id: {pid}")
        seen_ids.add(pid)
        metadata = entry.get("metadata") or {}
        catalog = entry.get("catalog") or {}
        errors.extend([f"{ctx} {err}" for err in validate_metadata_schema(metadata)])
        errors.extend([f"{ctx} {err}" for err in validate_catalog_schema(catalog)])
        if check_paths:
            for field in ("folder_path", "main_md", "pdf", "images_dir", "catalog_file", "metadata_file"):
                value = entry.get(field) or ""
                if not value:
                    errors.append(f"{ctx} missing {field}")
                    continue
                if not resolve_stored_path(value).exists():
                    errors.append(f"{ctx} {field} does not exist: {value}")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate v2 library structure.")
    parser.add_argument("--no-check-paths", action="store_true", help="do not require local paper assets to exist")
    args = parser.parse_args()
    errors, warnings = validate_v2_library(check_paths=not args.no_check_paths)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    print(f"valid={not errors} errors={len(errors)} warnings={len(warnings)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
