"""Commit curated v2 paper_raw folders into data/papers and rebuild all.catalog."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import PAPER_RAW_DIR
from src.services.v2_library import V2PaperCommitService


def _ready_dirs(root: Path) -> list[Path]:
    out = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        name = folder.name
        if name.isdigit() and len(name) == 6:
            continue
        if all((folder / f"{name}.{suffix}").exists() for suffix in ("metadata.json", "catalog.json", "md", "pdf")) and (folder / "images").is_dir():
            out.append(folder)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Commit curated v2 paper_raw folders into data/papers.")
    parser.add_argument("--paper-dir", type=Path, default=None)
    parser.add_argument("--all-ready", action="store_true")
    parser.add_argument("--paper-raw-dir", type=Path, default=PAPER_RAW_DIR)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    write = args.apply and not args.dry_run
    folders = [args.paper_dir] if args.paper_dir else _ready_dirs(args.paper_raw_dir) if args.all_ready else []
    if not folders:
        raise SystemExit("--paper-dir or --all-ready is required")
    service = V2PaperCommitService()
    report = []
    for folder in folders:
        item = {"folder": str(folder), "status": "planned"}
        if write:
            try:
                result = service.commit_paper_raw(folder)
                item.update(result)
                item["status"] = result.get("status", "failed")
            except Exception as exc:
                item.update({"status": "failed", "error": str(exc)})
        report.append(item)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"applied": write, "items": report}, ensure_ascii=False, indent=2))
    return 1 if any(i["status"] not in {"planned", "imported"} for i in report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
