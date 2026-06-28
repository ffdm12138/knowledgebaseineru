"""pending PDF 正式入库 CLI wrapper.

Core import logic lives in ``src.services.pending_import_service``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.library_index import VALID_DOMAINS
from src.services.pending_import_service import import_pending_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a pending OA PDF into the library.")
    parser.add_argument("pdf_path", type=Path, help="pending PDF 路径")
    parser.add_argument("--domain", required=True, choices=sorted(VALID_DOMAINS),
                        help="主领域 (primary domain)")
    parser.add_argument("--domains", nargs="+", default=None, help="全部领域 membership（含主领域）")
    parser.add_argument("--title", default="", help="标题（缺省从 sidecar 读）")
    parser.add_argument("--doi", default="", help="DOI（缺省从 sidecar 读）")
    parser.add_argument("--year", type=int, default=None, help="年份")
    parser.add_argument("--paper-id", default=None, help="显式 canonical paper_id（缺省自动生成）")
    parser.add_argument("--apply", action="store_true", help="实际写入（默认 dry-run）")
    args = parser.parse_args()

    try:
        result = import_pending_pdf(
            args.pdf_path,
            domain=args.domain,
            domains=args.domains,
            title=args.title,
            doi=args.doi,
            year=args.year,
            paper_id=args.paper_id,
            apply=args.apply,
        )
    except Exception as e:
        logger.error(f"import failed: {e}")
        return 1
    logger.info(
        "status={} applied={} is_duplicate={}",
        result["status"],
        result["applied"],
        result["is_duplicate"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
