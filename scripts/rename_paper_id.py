"""将已导入论文的 paper_id 改为中文命名（日志型，不回滚）。

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


def rename_paper(old_id: str, new_id: str, apply: bool = False):
    root = Path(__file__).parent.parent

    # --- 文件路径 ---
    papers_dir = root / "data" / "papers" / old_id
    papers_dir_new = root / "data" / "papers" / new_id
    raw_pdf = root / "data" / "raw" / f"{old_id}.pdf"
    raw_pdf_new = root / "data" / "raw" / f"{new_id}.pdf"

    manifest_path = root / "data" / "manifests" / "papers_manifest.json"
    libindex_path = root / "data" / "catalog" / "library_index.json"
    global_cat_path = root / "data" / "catalog" / "literature_catalog.json"
    domain_dir = root / "data" / "catalog" / "domains"

    # 预检查
    missing = []
    if not papers_dir.exists():
        missing.append(str(papers_dir))
    if not raw_pdf.exists():
        missing.append(str(raw_pdf))
    if missing:
        logger.warning(f"以下路径不存在，跳过: {missing}")

    logger.info(f"重命名: {old_id} → {new_id}")
    logger.info(f"  paper 目录: {papers_dir} → {papers_dir_new}")
    logger.info(f"  raw PDF:   {raw_pdf} → {raw_pdf_new}")

    if not apply:
        logger.info("[dry-run] 以上为拟执行变更")
        return

    # 1. 重命名 paper 目录
    if papers_dir.exists() and not papers_dir_new.exists():
        shutil.move(str(papers_dir), str(papers_dir_new))
        logger.info(f"  目录已重命名")
    elif papers_dir_new.exists():
        logger.info(f"  目录已存在，跳过")

    # 2. 重命名 raw PDF
    if raw_pdf.exists() and not raw_pdf_new.exists():
        shutil.move(str(raw_pdf), str(raw_pdf_new))
        logger.info(f"  raw PDF 已重命名")
    elif raw_pdf_new.exists():
        logger.info(f"  raw PDF 已存在，跳过")

    # 3. 更新 manifest
    mfst = _load(manifest_path)
    papers = mfst.get("papers", {})
    if old_id in papers:
        papers[new_id] = papers.pop(old_id)
        # 更新内部路径
        entry = papers[new_id]
        for field in ("raw_pdf_path", "pdf_path", "input_path"):
            if entry.get(field) and old_id in str(entry[field]):
                entry[field] = str(entry[field]).replace(old_id, new_id)
        _save(mfst, manifest_path)
        logger.info(f"  manifest 已更新")
    else:
        logger.warning(f"  manifest 中未找到 {old_id}")

    # 4. 更新 library_index
    lib = _load(libindex_path)
    lib_papers = lib.get("papers", [])
    changed = False
    for p in lib_papers:
        if p.get("paper_id") == old_id:
            p["paper_id"] = new_id
            changed = True
            break
    if changed:
        _save(lib, libindex_path)
        logger.info(f"  library_index 已更新")
    else:
        logger.warning(f"  library_index 中未找到 {old_id}")

    # 5. 更新全局 catalog
    cat = _load(global_cat_path)
    changed = False
    for p in cat.get("papers", []):
        if p.get("paper_id") == old_id:
            p["paper_id"] = new_id
            # 更新路径
            for field in ("raw_pdf", "markdown", "images_dir"):
                if p.get(field) and old_id in str(p[field]):
                    p[field] = str(p[field]).replace(old_id, new_id)
            changed = True
            break
    if changed:
        _save(cat, global_cat_path)
        logger.info(f"  全局 catalog 已更新")
    else:
        logger.warning(f"  全局 catalog 中未找到 {old_id}")

    # 6. 更新各 domain catalog
    for dc_dir in sorted(domain_dir.iterdir()):
        if not dc_dir.is_dir():
            continue
        dc_path = dc_dir / "literature_catalog.json"
        if not dc_path.exists():
            continue
        dc = _load(dc_path)
        changed = False
        for p in dc.get("papers", []):
            if p.get("paper_id") == old_id:
                p["paper_id"] = new_id
                if "domain_view" in p and p["domain_view"].get("canonical_paper_id") == old_id:
                    p["domain_view"]["canonical_paper_id"] = new_id
                # 更新路径
                for field in ("raw_pdf", "markdown", "images_dir"):
                    if p.get(field) and old_id in str(p[field]):
                        p[field] = str(p[field]).replace(old_id, new_id)
                changed = True
                break
        if changed:
            _save(dc, dc_path)
            logger.info(f"  domain catalog {dc_dir.name} 已更新")

    logger.info(f"完成: {old_id} → {new_id}")


def main():
    parser = argparse.ArgumentParser(description="重命名论文 paper_id")
    parser.add_argument("old_id", help="当前 paper_id")
    parser.add_argument("new_id", help="新 paper_id（支持中文）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="仅预览，不修改")
    group.add_argument("--apply", action="store_true", help="执行修改")
    args = parser.parse_args()

    rename_paper(args.old_id, args.new_id, apply=args.apply)


if __name__ == "__main__":
    main()
