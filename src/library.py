"""文献资产库读取：按 paper_id 读取全文 paper.md 与 images

不做检索、不做分块，只是按 id 取全文，供 prompt_builder 组装。
"""
from pathlib import Path
from loguru import logger

from config.settings import PAPERS_DIR
from src.manifest import PaperManifest


class PaperLibrary:
    """按 paper_id 读取清理后的 paper.md / images"""

    def __init__(self, manifest: PaperManifest | None = None):
        self.manifest = manifest or PaperManifest()

    def paper_dir(self, paper_id: str) -> Path:
        from src.naming import validate_paper_id, safe_child
        validate_paper_id(paper_id)  # 防路径穿越
        return safe_child(PAPERS_DIR, paper_id)

    def exists(self, paper_id: str) -> bool:
        return (self.paper_dir(paper_id) / "paper.md").exists()

    def list_papers(self) -> list[dict]:
        """返回 manifest 中所有文献条目"""
        return self.manifest.list_all()

    def read_markdown(self, paper_id: str, max_chars: int | None = None) -> str | None:
        """读取某篇 paper.md 全文，可截断"""
        md_path = self.paper_dir(paper_id) / "paper.md"
        if not md_path.exists():
            logger.warning(f"paper.md 不存在: {paper_id}")
            return None
        content = md_path.read_text(encoding="utf-8")
        if max_chars and len(content) > max_chars:
            content = content[:max_chars] + "\n\n...(已截断)"
        return content

    def list_images(self, paper_id: str) -> list[str]:
        """返回该文献 images/ 下的文件名列表"""
        img_dir = self.paper_dir(paper_id) / "images"
        if not img_dir.is_dir():
            return []
        return sorted([f.name for f in img_dir.iterdir() if f.is_file()])

    def read_multiple(self, paper_ids: list[str], max_chars_each: int | None = None) -> dict[str, str]:
        """批量读取多篇全文"""
        out = {}
        for pid in paper_ids:
            md = self.read_markdown(pid, max_chars=max_chars_each)
            if md is not None:
                out[pid] = md
        return out
