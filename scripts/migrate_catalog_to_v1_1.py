"""Migrate per-paper catalog JSON files to the v1.1 schema.

Scans ``data/papers/*/<pid>.catalog.json`` and fills any missing v1.1
groups/fields (preserving existing values) via ``migrate_catalog_to_v1_1``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.v2_library import migrate_catalog_to_v1_1
from src.utils.atomic_io import atomic_write_json
from config.settings import PAPERS_DIR


def _catalog_files(papers_dir: Path) -> list[Path]:
    if not papers_dir.exists():
        return []
    out: list[Path] = []
    for folder in sorted(p for p in papers_dir.iterdir() if p.is_dir()):
        out.extend(folder.glob("*.catalog.json"))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate catalog JSON to v1.1 schema.")
    parser.add_argument("--papers-dir", default=str(PAPERS_DIR))
    parser.add_argument("--apply", action="store_true", help="write migrated catalogs; default is dry-run")
    parser.add_argument("--dry-run", action="store_true", help="print summary without writing")
    args = parser.parse_args()
    write = args.apply and not args.dry_run
    papers_dir = Path(args.papers_dir)
    files = _catalog_files(papers_dir)
    migrated = 0
    for path in files:
        import json
        data = json.loads(path.read_text(encoding="utf-8"))
        before_version = data.get("schema_version")
        new_data, notes = migrate_catalog_to_v1_1(data)
        if new_data.get("schema_version") != before_version or notes:
            migrated += 1
            if write:
                atomic_write_json(path, new_data, indent=2)
            print(f"{path.name}: {before_version} -> {new_data.get('schema_version')} added={len(notes)}")
    print(f"files={len(files)} migrated={migrated} written={write}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
