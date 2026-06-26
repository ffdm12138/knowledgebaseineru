"""文件账本：系统维护的 papers_manifest.json

记录每篇已转换文献的路径、状态、时间。区别于 AI 维护的 literature_catalog.json：
  - manifest 管文件状态（在哪、转没转、何时转）
  - catalog  管文献理解（讲了什么、怎么用）
两者分离，paper_id 是共同主键。
"""
import json
from pathlib import Path
from datetime import datetime
from loguru import logger

from config.settings import MANIFEST_PATH


class PaperManifest:
    """papers_manifest.json 读写"""

    def __init__(self, path: Path = MANIFEST_PATH):
        self.path = Path(path)

    def _load(self) -> dict:
        if not self.path.exists():
            return {"version": "0.1", "description": "System-maintained file ledger of converted papers.",
                    "papers": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"manifest 读取失败，重建: {e}")
            return {"version": "0.1", "description": "System-maintained file ledger of converted papers.",
                    "papers": []}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_all(self) -> list[dict]:
        return self._load().get("papers", [])

    def get(self, paper_id: str) -> dict | None:
        for p in self.list_all():
            if p.get("paper_id") == paper_id:
                return p
        return None

    def has(self, paper_id: str) -> bool:
        return self.get(paper_id) is not None

    def upsert(self, paper_id: str, raw_pdf: str, markdown: str, images_dir: str,
               status: str = "converted", images_count: int = 0, md_chars: int = 0,
               converted_at: str | None = None) -> dict:
        """新增或更新一条记录"""
        data = self._load()
        papers = data.get("papers", [])
        entry = {
            "paper_id": paper_id,
            "raw_pdf": raw_pdf,
            "markdown": markdown,
            "images_dir": images_dir,
            "status": status,
            "images_count": images_count,
            "md_chars": md_chars,
            "converted_at": converted_at or datetime.now().isoformat(timespec="seconds"),
        }
        # 替换已有
        for i, p in enumerate(papers):
            if p.get("paper_id") == paper_id:
                # 保留旧的 converted_at（若未提供）
                if converted_at is None and p.get("converted_at"):
                    entry["converted_at"] = p["converted_at"]
                papers[i] = entry
                break
        else:
            papers.append(entry)
        data["papers"] = papers
        self._save(data)
        logger.info(f"manifest 更新: {paper_id} ({status})")
        return entry

    def delete(self, paper_id: str) -> bool:
        data = self._load()
        papers = data.get("papers", [])
        new = [p for p in papers if p.get("paper_id") != paper_id]
        if len(new) == len(papers):
            return False
        data["papers"] = new
        self._save(data)
        return True

    def stats(self) -> dict:
        papers = self.list_all()
        return {
            "total_papers": len(papers),
            "total_images": sum(p.get("images_count", 0) for p in papers),
            "total_md_chars": sum(p.get("md_chars", 0) for p in papers),
        }
