"""从 literature_catalog.json 同步生成 data/catalog/references.bib（原子写入 + 校验）

流程：校验 catalog citation → 备份旧 references.bib → 写 tmp → 校验 → 原子替换。
用法: python scripts/sync_bib_from_catalog.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from loguru import logger
from src.writer.bib_manager import sync_from_catalog, validate_catalog_citations
from src.catalog import Catalog
from src import bib as bibmod


def main():
    # 先校验
    errors = validate_catalog_citations()
    if errors:
        logger.error(f"catalog citation 校验未通过，拒绝同步：")
        for e in errors:
            logger.error(f"  - {e}")
        return 1
    try:
        dest = sync_from_catalog(backup=True)
        n = len(bibmod.parse_blocks(dest.read_text(encoding="utf-8")))
        logger.info(f"已同步 {n} 条 BibTeX 到 {dest}（含备份）")
        return 0
    except RuntimeError as e:
        logger.error(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
