"""从系统中完全删除一篇论文 — thin CLI wrapper，核心逻辑委托 PaperRegistryService。

用法：
  python scripts/remove_paper.py <paper_id> --dry-run
  python scripts/remove_paper.py <paper_id> --apply
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.services.paper_registry import PaperRegistryService


def main():
    parser = argparse.ArgumentParser(description="从系统中完全删除一篇论文")
    parser.add_argument("paper_id", help="要删除的 paper_id")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="仅预览，不修改")
    group.add_argument("--apply", action="store_true", help="执行删除")
    args = parser.parse_args()

    if args.dry_run:
        logger.info(f"[dry-run] 模拟删除: {args.paper_id}")
        for field in ("paper_dir", "raw_pdf"):
            logger.info(f"  将删除 {field}")
        logger.info("  将清理 manifest / catalog / library_index / domain views")
        return

    svc = PaperRegistryService()
    result = svc.delete_paper(args.paper_id, remove_raw=True, remove_assets=True)
    if result["success"]:
        logger.info(f"已删除: {args.paper_id}")
        for k, v in result.items():
            if k != "success":
                logger.info(f"  {k}={v}")
    else:
        logger.warning(f"未删除或未找到: {args.paper_id}")


if __name__ == "__main__":
    main()
