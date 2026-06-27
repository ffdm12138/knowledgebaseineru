"""批量 DOI 下载 / pending 生成。

输入：
  data/discovery/doi_candidates/*.jsonl
支持断点续跑、去重、报告。
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import DISCOVERY_DIR, RAW_DIR
from src.fetch.access_policy import AccessMode, AccessPolicy
from src.fetch.fetch_pipeline import fetch_pdf, safe_doi_slug
from src.library_index import VALID_DOMAINS


def _already_pending(doi: str, raw_dir: Path) -> bool:
    """检查 pending 目录是否已有此 DOI 的 PDF。"""
    slug = safe_doi_slug(doi)
    for domain_path in raw_dir.iterdir():
        if not domain_path.is_dir():
            continue
        pending_dir = domain_path / "pending"
        if not pending_dir.exists():
            continue
        for pdf in pending_dir.glob(f"{slug}*"):
            if pdf.suffix == ".pdf":
                return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch DOI PDF fetch.")
    parser.add_argument("--input", type=Path, default=None, help="input jsonl path (default: all in doi_candidates)")
    parser.add_argument("--domain", choices=sorted(VALID_DOMAINS), default=None)
    parser.add_argument("--access-mode", choices=[m.value for m in AccessMode], default="oa_only")
    parser.add_argument("--limit", type=int, default=0, help="max DOIs to process")
    parser.add_argument("--resume", action="store_true", help="skip already pending DOIs")
    parser.add_argument("--dry-run", action="store_true", help="resolve without downloading")
    parser.add_argument("--report-dir", type=Path, default=DISCOVERY_DIR / "pdf_fetch_logs")
    args = parser.parse_args()

    policy = AccessPolicy(mode=AccessMode(args.access_mode))

    # collect DOIs
    dois: list[str] = []
    if args.input:
        files = [args.input]
    else:
        files = sorted((DISCOVERY_DIR / "doi_candidates").glob("*.jsonl"))
    for f in files:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                p = json.loads(line)
                doi = (p.get("doi") or "").strip()
                if doi and doi not in dois:
                    dois.append(doi)
            except Exception:
                pass

    if args.resume:
        before = len(dois)
        dois = [d for d in dois if not _already_pending(d, RAW_DIR)]
        logger.info(f"skipped {before - len(dois)} already-pending DOIs")

    if args.limit > 0:
        dois = dois[:args.limit]

    logger.info(f"processing {len(dois)} DOIs (mode={args.access_mode})")

    report = []
    ok = 0
    fail = 0
    for i, doi in enumerate(dois):
        result = fetch_pdf(doi, domain_id=args.domain, dry_run=args.dry_run, access_policy=policy)
        entry = {
            "doi": doi,
            "status": "downloaded" if result.success else "failed",
            "resolver": result.resolver,
            "access_mode": result.access_mode,
            "pdf_path": result.output_path,
            "landing_url": result.landing_url,
            "error": result.error,
            "requires_user_action": result.requires_user_action,
        }
        report.append(entry)

        if result.success:
            ok += 1
            logger.info(f"[{i + 1}/{len(dois)}] OK {doi} -> {result.resolver}")
        else:
            fail += 1
            if i < 5:
                logger.warning(f"[{i + 1}/{len(dois)}] FAIL {doi}: {result.error}")

    # write report
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.report_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.report_dir / f"{ts}_batch_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # markdown summary
    md = f"# Batch PDF Fetch Report ({ts})\n\n"
    md += f"- Access mode: {args.access_mode}\n"
    md += f"- DOIs attempted: {len(dois)}\n"
    md += f"- Success: {ok}\n"
    md += f"- Failed: {fail}\n\n"
    md += "## Detail\n\n"
    for e in report:
        md += f"- {e['doi']}: **{e['status']}** (resolver={e['resolver']})\n"
        if e['error']:
            md += f"  - error: {e['error']}\n"
    md_path = args.report_dir / f"{ts}_batch_report.md"
    md_path.write_text(md, encoding="utf-8")

    logger.info(f"report: {report_path}")
    logger.info(f"summary: {md_path}")
    logger.info(f"done: {ok} OK, {fail} failed")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
