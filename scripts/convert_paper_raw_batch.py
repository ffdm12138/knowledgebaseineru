"""Batch convert v2 data/paper_raw sources with guarded MinerU input paths."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import PAPER_RAW_DIR
from src.services.v2_library import PaperRawConverter


def _source_ids(root: Path, args) -> list[str]:
    if args.source_id:
        return [args.source_id]
    if args.source_ids:
        return args.source_ids
    if args.all:
        return sorted(p.name for p in root.iterdir() if p.is_dir() and p.name.isdigit() and len(p.name) == 6)
    raise ValueError("--source-id, --source-ids, or --all is required")


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert v2 paper_raw PDFs into md/images.")
    parser.add_argument("--source-id", default=None)
    parser.add_argument("--source-ids", nargs="+", default=None)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--paper-raw-dir", type=Path, default=PAPER_RAW_DIR)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    write = args.apply and not args.dry_run
    converter = PaperRawConverter(args.paper_raw_dir)
    report = []
    for source_id in _source_ids(args.paper_raw_dir, args):
        item = {"source_id": source_id, "status": "planned"}
        logger.info("{} convert paper_raw/{}", "CONVERT" if write else "DRY-RUN", source_id)
        if write:
            try:
                result = converter.convert(source_id)
                item.update(result)
                item["status"] = "converted" if result.get("success") else "failed"
            except Exception as exc:
                item.update({"status": "failed", "error": str(exc)})
                logger.error("convert failed for {}: {}", source_id, exc)
        report.append(item)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"applied": write, "items": report}, ensure_ascii=False, indent=2))
    return 1 if any(i["status"] == "failed" for i in report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
