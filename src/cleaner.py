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

    def locate_markdown(self, source_dir: Path,
                        method: str | None = None,
                        stem: str | None = None) -> Path | None:
        """在 MinerU 输出目录中定位正文 Markdown。

        支持两种 source_dir 传入方式：
          A. tmp_out/<stem>/   — converter 返回 output_dir/stem（最常见）
          B. tmp_out/          — 直接传 MinerU 输出根目录

        选择规则（确定性，不依赖 rglob 顺序）：
          a. exact path（若提供 method + stem）：
             source_dir / method / stem.md     (模式 A)
             source_dir / stem / method / stem.md  (模式 B)
          b. method 是指定硬约束，找不到不 fallback
          c. source_dir 下唯一 .md → 取它
          d. 唯一 method 候选 → 取它
          e. 多候选 → 返回 None 并列出
        """
        source_dir = Path(source_dir)
        if not source_dir.exists():
            return None

        # a. exact path（若提供了 method 和 stem）
        if method and stem:
            # 模式 A: source_dir 已是 <stem>/ 目录
            exact_a = source_dir / method / f"{stem}.md"
            if exact_a.is_file():
                return exact_a
            # 模式 B: source_dir 是 tmp_out 根目录
            exact_b = source_dir / stem / method / f"{stem}.md"
            if exact_b.is_file():
                return exact_b
            # 模式 C: source_dir 是旧输出或扁平结构
            exact_c = source_dir / f"{stem}.md"
            if exact_c.is_file():
                return exact_c
            # method 是硬约束，找不到不 fallback
            logger.error(
                f"未找到指定 method={method} stem={stem} 的正文 md，"
                f"已检查: {exact_a}, {exact_b}, {exact_c}")
            return None

        candidates = list(source_dir.rglob("*.md"))
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        # b. 多个候选：查找标准 method 目录下的 md
        known_methods = {"auto", "txt", "ocr", "hybrid_auto", "hybrid_txt",
                         "hybrid_ocr", "vlm_auto", "vlm_txt", "vlm_ocr"}
        method_cands = [c for c in candidates if c.parent.name in known_methods]

        if len(method_cands) == 1:
            return method_cands[0]

        if len(method_cands) > 1:
            names = ", ".join(str(c.relative_to(source_dir)) for c in method_cands)
            logger.error(
                f"多个 method 目录候选 md 文件，无法确定正文: {names}。"
                f"请指定 method 参数或清理残留输出。")
            return None

        # c. 无 method 目录候选：报错列全部候选
        names = ", ".join(str(c.relative_to(source_dir)) for c in candidates)
        logger.error(f"多个候选 md 文件且不在标准 method 目录，无法确定正文: {names}")
        return None

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
                overwrite: bool = False,
                method: str | None = None,
                stem: str | None = None) -> dict:
        """从 MinerU 原始输出目录提取 paper.md + images 到 data/papers/<paper_id>/

        覆盖保护：默认 overwrite=False，目标已存在则报错；overwrite=True 先备份再重建。

        Args:
            method: MinerU 解析方法 (auto/ocr/txt)，用于确定性定位正文 md
            stem: 输入文件名 stem，用于 exact path 匹配

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
        # 防御性校验 paper_id，防路径穿越（调用方已校验，此处二次确认）
        from src.naming import validate_paper_id, safe_child
        try:
            validate_paper_id(paper_id)
        except ValueError as e:
            return {"success": False, "paper_id": paper_id,
                    "error": f"Invalid paper_id: {e}"}

        md_path = self.locate_markdown(source_dir, method=method, stem=stem)
        if md_path is None:
            msg = f"未在 {source_dir} 找到正文 Markdown"
            logger.error(msg)
            return {"success": False, "paper_id": paper_id, "error": msg}

        dest_dir = safe_child(PAPERS_DIR, paper_id)
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
