"""将已导入论文的 paper_id 改为中文命名 — thin CLI wrapper，核心逻辑委托 PaperRegistryService。

用法：
  python scripts/rename_paper_id.py <old_id> <new_id> [--dry-run]

示例：
  python scripts/rename_paper_id.py \\
    2015_convective_boundary_layer_heights_over_mountainous_terrain_a_review_of_concepts \\
    2015_山地地形对流边界层高度综述 \\
    --dry-run
  python scripts/rename_paper_id.py ... --apply
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.services.paper_registry import PaperRegistryService


def main():
    parser = argparse.ArgumentParser(description="重命名论文 paper_id")
    parser.add_argument("old_id", help="当前 paper_id")
    parser.add_argument("new_id", help="新 paper_id（支持中文）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="仅预览，不修改")
    group.add_argument("--apply", action="store_true", help="执行修改")
    args = parser.parse_args()

    if args.dry_run:
        logger.info(f"[dry-run] 重命名: {args.old_id} → {args.new_id}")
        logger.info("  将移动 paper 目录和 raw PDF")
        logger.info("  将更新 manifest / catalog / library_index / domain views")
        return

    svc = PaperRegistryService()
    result = svc.rename_paper_id(args.old_id, args.new_id)
    if result.get("success"):
        logger.info(f"完成: {args.old_id} → {args.new_id}")
        for k, v in result.items():
            if k not in ("success", "old_id", "new_id"):
                if v:
                    logger.info(f"  {k}=True")
    else:
        logger.warning(f"重命名失败: {result.get('error', 'unknown')}")


if __name__ == "__main__":
    main()
