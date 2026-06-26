"""校验 catalog citation 与 references.bib 一致性

检查：有 citation；bib_key 唯一；bibtex entry key == bib_key；含 title/author/year；
catalog bib_key 在 references.bib 中能找到。
退出码 0 通过，1 有错误。
用法: python scripts/validate_bib.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from loguru import logger
from src.catalog import Catalog
from src.writer.bib_manager import validate_catalog_citations
from src import bib as bibmod


def main():
    cat = Catalog().load()
    errors = validate_catalog_citations(cat)
    # 额外：catalog bib_key 在 references.bib 中能找到
    bib_keys_in_file = set()
    if bibmod.GLOBAL_BIB_PATH.exists():
        bib_keys_in_file = set(bibmod.parse_blocks(
            bibmod.GLOBAL_BIB_PATH.read_text(encoding="utf-8")).keys())
    for p in cat.get("papers", []):
        bk = (p.get("citation") or {}).get("bib_key")
        if bk and bib_keys_in_file and bk not in bib_keys_in_file:
            errors.append(f"paper_id={p.get('paper_id')} bib_key={bk} 在 references.bib 中找不到")

    if not errors:
        logger.info(f"✅ BibTeX 校验通过（{len(cat['papers'])} 篇）")
        return 0
    logger.error(f"❌ 发现 {len(errors)} 个错误：")
    for e in errors:
        logger.error(f"  - {e}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
