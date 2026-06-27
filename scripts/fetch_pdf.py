"""通用 PDF 获取 CLI（支持 access policy）。

默认走 ``oa_only``。通过 ``--access-mode`` 切换策略。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import RAW_DIR
from src.fetch.access_policy import AccessMode, AccessPolicy
from src.fetch.fetch_pipeline import fetch_pdf
from src.library_index import VALID_DOMAINS


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch PDF using access policy.")
    parser.add_argument("doi", help="DOI to fetch")
    parser.add_argument("--domain", choices=sorted(VALID_DOMAINS), default=None)
    parser.add_argument("--access-mode", choices=[m.value for m in AccessMode], default="oa_only")
    parser.add_argument("--dry-run", action="store_true", help="resolve candidate without downloading")
    parser.add_argument("--pdf-path", type=Path, default=None, help="local PDF path (for local_manual)")
    parser.add_argument("--title", default="", help="paper title")
    parser.add_argument("--year", type=int, default=None, help="publication year")
    args = parser.parse_args()

    policy = AccessPolicy(mode=AccessMode(args.access_mode))
    metadata = {}
    if args.pdf_path:
        metadata["pdf_path"] = str(args.pdf_path)

    result = fetch_pdf(
        args.doi, domain_id=args.domain, dry_run=args.dry_run,
        access_policy=policy, title=args.title, year=args.year,
        metadata=metadata,
    )

    if result.success:
        if result.requires_user_action:
            logger.info(f"[{result.resolver}] requires user action — {result.action_hint}")
            if result.landing_url:
                logger.info(f"  landing: {result.landing_url}")
        else:
            logger.info(f"[OK] source: {result.source}")
            logger.info(f"[OK] pdf_url: {result.pdf_url}")
            if result.output_path:
                logger.info(f"[OK] output_path: {result.output_path}")
            if result.sha256:
                logger.info(f"[OK] sha256: {result.sha256}")
        return 0

    logger.error(f"[ERROR] {result.error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
