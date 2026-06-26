"""校验 data/catalog/literature_catalog.json 结构是否正确

退出码：0 通过，1 有错误。
用法: python scripts/validate_catalog.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from src.catalog import Catalog


def main():
    cat = Catalog()
    papers = cat.list_papers()
    logger.info(f"catalog 共 {len(papers)} 条")
    errors = cat.validate()
    if not errors:
        logger.info("✅ 校验通过")
        return 0
    logger.error(f"❌ 发现 {len(errors)} 个错误：")
    for e in errors:
        logger.error(f"  - {e}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
