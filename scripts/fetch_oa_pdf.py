"""Fetch an open-access PDF for a DOI into data/raw/<domain>/pending."""
import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import RAW_DIR  # noqa: E402
from src.fetch.fetch_pipeline import fetch_oa_pdf  # noqa: E402
from src.library_index import VALID_DOMAINS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch OA-only PDF by DOI. No Sci-Hub or paywall bypass.")
    parser.add_argument("doi", help="DOI, with or without https://doi.org/ prefix.")
    parser.add_argument("--domain", choices=sorted(VALID_DOMAINS), default=None)
    parser.add_argument("--output-root", type=Path, default=RAW_DIR)
    parser.add_argument("--dry-run", action="store_true", help="Resolve candidate PDF URL without writing files.")
    args = parser.parse_args()

    result = fetch_oa_pdf(
        args.doi,
        domain_id=args.domain,
        output_root=args.output_root,
        dry_run=args.dry_run,
    )
    if result.success:
        print(f"[OK] source: {result.source}")
        print(f"[OK] pdf_url: {result.pdf_url}")
        if args.dry_run:
            print("[OK] dry-run: no file written")
        else:
            print(f"[OK] output_path: {result.output_path}")
            print(f"[OK] sidecar_path: {result.sidecar_path}")
            print(f"[OK] sha256: {result.sha256}")
        return 0

    print(f"[ERROR] {result.error or 'no OA PDF found'}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

