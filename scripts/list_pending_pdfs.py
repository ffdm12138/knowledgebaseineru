"""列出 data/raw/<domain>/pending/ 下的待入库 PDF 及其状态。"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import RAW_DIR
from src.library_index import VALID_DOMAINS


def list_pending_pdfs(raw_dir: Path = RAW_DIR) -> list[dict]:
    """扫描所有领域 pending 目录，返回 pending PDF 信息列表。"""
    out = []
    for domain in sorted(VALID_DOMAINS):
        pending_dir = raw_dir / domain / "pending"
        if not pending_dir.exists():
            continue
        for pdf_path in sorted(pending_dir.glob("*.pdf")):
            sidecar = pdf_path.with_suffix(".json")
            info = {
                "pdf_path": str(pdf_path),
                "domain": domain,
                "sidecar_path": str(sidecar) if sidecar.exists() else "",
                "doi": "",
                "title": "",
                "status": "pending",
                "possible_duplicate": False,
            }
            if sidecar.exists():
                try:
                    data = json.loads(sidecar.read_text(encoding="utf-8"))
                    info["doi"] = data.get("doi") or ""
                    info["title"] = data.get("title") or ""
                    info["status"] = data.get("status") or "pending"
                    info["possible_duplicate"] = bool(data.get("canonical_paper_id"))
                    info["canonical_paper_id"] = data.get("canonical_paper_id") or ""
                except Exception:
                    pass
            out.append(info)
    # 也扫描 unknown 域
    unknown_dir = raw_dir / "unknown" / "pending"
    if unknown_dir.exists():
        for pdf_path in sorted(unknown_dir.glob("*.pdf")):
            sidecar = pdf_path.with_suffix(".json")
            info = {
                "pdf_path": str(pdf_path),
                "domain": "unknown",
                "sidecar_path": str(sidecar) if sidecar.exists() else "",
                "doi": "", "title": "", "status": "pending", "possible_duplicate": False,
            }
            if sidecar.exists():
                try:
                    data = json.loads(sidecar.read_text(encoding="utf-8"))
                    info.update({
                        "doi": data.get("doi") or "",
                        "title": data.get("title") or "",
                        "status": data.get("status") or "pending",
                        "possible_duplicate": bool(data.get("canonical_paper_id")),
                    })
                except Exception:
                    pass
            out.append(info)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="List pending OA PDFs awaiting import.")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    args = parser.parse_args()
    pending = list_pending_pdfs(args.raw_dir)
    if not pending:
        logger.info("no pending PDFs found")
        return 0
    logger.info(f"{len(pending)} pending PDF(s):")
    for p in pending:
        print(f"- doi: {p['doi'] or '(none)'}")
        print(f"  title: {p['title'] or '(none)'}")
        print(f"  domain: {p['domain']}")
        print(f"  pdf: {p['pdf_path']}")
        print(f"  sidecar: {p['sidecar_path'] or '(none)'}")
        print(f"  status: {p['status']}")
        print(f"  possible_duplicate: {p['possible_duplicate']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
