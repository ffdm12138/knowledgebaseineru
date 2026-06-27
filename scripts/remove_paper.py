"""从系统中完全删除一篇论文（逆向 import_pending_pdf）。

用法：
  python scripts/remove_paper.py <paper_id> --dry-run
  python scripts/remove_paper.py <paper_id> --apply
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(data, path: Path):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def remove_paper(paper_id: str, apply: bool = False):
    root = Path(__file__).parent.parent

    papers_dir = root / "data" / "papers" / paper_id
    raw_pdf = root / "data" / "raw" / f"{paper_id}.pdf"
    manifest_path = root / "data" / "manifests" / "papers_manifest.json"
    libindex_path = root / "data" / "catalog" / "library_index.json"
    global_cat_path = root / "data" / "catalog" / "literature_catalog.json"
    domain_dir = root / "data" / "catalog" / "domains"

    logger.info(f"删除论文: {paper_id}")
    logger.info(f"  paper 目录存在: {papers_dir.exists()}")
    logger.info(f"  raw PDF 存在:   {raw_pdf.exists()}")

    if not apply:
        logger.info("[dry-run] 以上为拟执行变更")
        return

    # 1. 删除 paper 目录
    if papers_dir.exists():
        shutil.rmtree(papers_dir)
        logger.info(f"  已删除 {papers_dir}")

    # 2. 删除 raw PDF
    if raw_pdf.exists():
        raw_pdf.unlink()
        logger.info(f"  已删除 {raw_pdf}")

    # 3. 从 manifest 删除
    mfst = _load(manifest_path)
    papers = mfst.get("papers", {})
    if paper_id in papers:
        del papers[paper_id]
        _save(mfst, manifest_path)
        logger.info(f"  已从 manifest 删除")
    else:
        logger.warning(f"  manifest 中未找到")

    # 4. 从 library_index 删除
    lib = _load(libindex_path)
    lib_papers = lib.get("papers", [])
    before = len(lib_papers)
    lib["papers"] = [p for p in lib_papers if p.get("paper_id") != paper_id]
    if len(lib["papers"]) < before:
        _save(lib, libindex_path)
        logger.info(f"  已从 library_index 删除")
    else:
        logger.warning(f"  library_index 中未找到")

    # 5. 从全局 catalog 删除
    cat = _load(global_cat_path)
    before = len(cat.get("papers", []))
    cat["papers"] = [p for p in cat.get("papers", []) if p.get("paper_id") != paper_id]
    if len(cat["papers"]) < before:
        _save(cat, global_cat_path)
        logger.info(f"  已从全局 catalog 删除")
    else:
        logger.warning(f"  全局 catalog 中未找到")

    # 6. 从各 domain catalog 删除
    for dc_dir in sorted(domain_dir.iterdir()):
        if not dc_dir.is_dir():
            continue
        dc_path = dc_dir / "literature_catalog.json"
        if not dc_path.exists():
            continue
        dc = _load(dc_path)
        before = len(dc.get("papers", []))
        dc["papers"] = [p for p in dc.get("papers", []) if p.get("paper_id") != paper_id]
        if len(dc["papers"]) < before:
            _save(dc, dc_path)
            logger.info(f"  已从 domain catalog {dc_dir.name} 删除")

    logger.info(f"完成: {paper_id} 已删除")


def main():
    parser = argparse.ArgumentParser(description="从系统中完全删除一篇论文")
    parser.add_argument("paper_id", help="要删除的 paper_id")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="仅预览")
    group.add_argument("--apply", action="store_true", help="执行删除")
    args = parser.parse_args()
    remove_paper(args.paper_id, apply=args.apply)


if __name__ == "__main__":
    main()
