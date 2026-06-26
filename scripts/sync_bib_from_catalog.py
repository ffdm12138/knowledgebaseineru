"""从 literature_catalog.json 同步生成 data/catalog/references.bib

用法: python scripts/sync_bib_from_catalog.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from loguru import logger
from src.catalog import Catalog
from src import bib as bibmod


def main():
    cat = Catalog().load()
    n = bibmod.sync_from_catalog(cat)
    logger.info(f"已同步 {n} 条 BibTeX 到 {bibmod.GLOBAL_BIB_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
