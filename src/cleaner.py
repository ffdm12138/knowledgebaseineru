"""MinerU 输出清理器

把 MinerU 杂乱的原始输出（md + images + 一堆 json/layout/中间文件）清理为
长期 AI 可读资产：

    data/papers/<paper_id>/
    ├── paper.md
    └── images/

不复制 PDF，不保留 json sidecars。
"""
import shutil
from pathlib import Path
from loguru import logger

from config.settings import PAPERS_DIR

# MinerU 中间产物后缀（均为 .json，非正文 .md）：_model/_middle/_content_list/_origin
# 正文 md 文件名等于 stem，可能含 model 等词，故不按 token 排除 .md。


class MinerUOutputCleaner:
    """清理 MinerU 输出，只保留 paper.md + images/"""

    def locate_markdown(self, source_dir: Path) -> Path | None:
        """在 MinerU 输出目录中定位正文 Markdown。

        MinerU 3.4 输出结构多变：
          - <stem>/<method>/<stem>.md
          - <stem>.md 直接在目录下
        正文 md 文件名通常等于 stem，且不含 _model/_middle/_content_list 等。
        """
        source_dir = Path(source_dir)
        if not source_dir.exists():
            return None

        # 递归找所有 .md（MinerU 中间产物是 .json，正文 md 不含 _model/_middle 后缀，
        # 但正文文件名本身可能含 model 字样，如 "drag_model"，故不按 token 排除 .md）
        candidates = list(source_dir.rglob("*.md"))

        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        # 多个候选：取体积最大的（正文通常最大）
        candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
        return candidates[0]

    def locate_images_dir(self, source_dir: Path, md_path: Path) -> Path | None:
        """定位 md 引用的 images 目录"""
        # 优先 md 同级 images/
        img_dir = md_path.parent / "images"
        if img_dir.is_dir():
            return img_dir
        # 退而递归找
        for d in source_dir.rglob("images"):
            if d.is_dir():
                return d
        return None

    def extract(self, source_dir: str | Path, paper_id: str,
                overwrite: bool = False) -> dict:
        """从 MinerU 原始输出目录提取 paper.md + images 到 data/papers/<paper_id>/

        覆盖保护：默认 overwrite=False，目标已存在则报错；overwrite=True 先备份再重建。

        Returns:
            {
                "success": bool,
                "paper_id": str,
                "markdown_path": str,
                "images_dir": str,
                "images_count": int,
                "char_count": int,
                "error": str (失败时),
            }
        """
        source_dir = Path(source_dir)
        md_path = self.locate_markdown(source_dir)
        if md_path is None:
            msg = f"未在 {source_dir} 找到正文 Markdown"
            logger.error(msg)
            return {"success": False, "paper_id": paper_id, "error": msg}

        dest_dir = PAPERS_DIR / paper_id
        # 覆盖保护：已存在则备份或报错，不无条件 rmtree
        if dest_dir.exists():
            if not overwrite:
                msg = (f"目标目录已存在，拒绝覆盖: {dest_dir} "
                       f"(传 overwrite=True 以备份后重建)")
                logger.error(msg)
                return {"success": False, "paper_id": paper_id, "error": msg}
            # 备份旧目录为 .bak_<timestamp>
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = dest_dir.with_name(f"{dest_dir.name}__old_{ts}")
            dest_dir.rename(bak)
            logger.info(f"已备份旧目录: {dest_dir.name} -> {bak.name}")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_images = dest_dir / "images"
        dest_md = dest_dir / "paper.md"

        # 1. 写入 paper.md，统一图片相对路径为 images/...
        md_content = md_path.read_text(encoding="utf-8")
        # MinerU 已用 ![](images/xxx) 形式，无需改写；若出现 ./images/ 也归一化
        md_content = md_content.replace("](./images/", "](images/")
        dest_md.write_text(md_content, encoding="utf-8")

        # 2. 复制 images/
        images_count = 0
        src_images = self.locate_images_dir(source_dir, md_path)
        if src_images and src_images.is_dir():
            dest_images.mkdir(parents=True, exist_ok=True)
            for img in src_images.iterdir():
                if img.is_file():
                    shutil.copy2(img, dest_images / img.name)
                    images_count += 1

        logger.info(f"清理完成: {paper_id} -> {dest_md} ({len(md_content)} 字符, {images_count} 图)")
        return {
            "success": True,
            "paper_id": paper_id,
            "markdown_path": str(dest_md),
            "images_dir": str(dest_images) if images_count else "",
            "images_count": images_count,
            "char_count": len(md_content),
        }
