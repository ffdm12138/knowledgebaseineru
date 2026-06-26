"""校验 catalog citation 与 references.bib 一致性

检查：每篇有 citation；bib_key 唯一；bibtex 含 title/author/year；DOI 已写入；
catalog bib_key 在 references.bib 中能找到。
退出码 0 通过，1 有错误。
用法: python scripts/validate_bib.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from loguru import logger
from src.catalog import Catalog
from src import bib as bibmod


def main():
    cat = Catalog().load()
    errors = bibmod.validate(cat)
    if not errors:
        logger.info(f"✅ BibTeX 校验通过（{len(cat['papers'])} 篇）")
        return 0
    logger.error(f"❌ 发现 {len(errors)} 个错误：")
    for e in errors:
        logger.error(f"  - {e}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
