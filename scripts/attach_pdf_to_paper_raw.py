"""Attach a local PDF to an existing data/paper_raw/<source_id>/ folder."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import PAPER_RAW_DIR
from src.services.v2_library import PaperRawAllocator


def main() -> int:
    parser = argparse.ArgumentParser(description="Attach PDF to v2 paper_raw source folder.")
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--paper-raw-dir", type=Path, default=PAPER_RAW_DIR)
    parser.add_argument("--copy", action="store_true")
    parser.add_argument("--move", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    write = args.apply and not args.dry_run
    move = args.move and not args.copy
    folder = args.paper_raw_dir / args.source_id
    dest = folder / f"{args.source_id}.pdf"
    result = {
        "applied": write,
        "source_id": args.source_id,
        "source_pdf": str(args.pdf_path),
        "target_pdf": str(dest),
        "status": "planned",
    }
    if write:
        out = PaperRawAllocator(args.paper_raw_dir).attach_pdf(args.source_id, args.pdf_path, move=move)
        result.update(out)
        result["status"] = "attached"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
