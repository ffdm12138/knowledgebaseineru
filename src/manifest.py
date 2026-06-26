"""文件账本：系统维护的 papers_manifest.json

记录每篇已转换文献的路径、状态、指纹、时间。区别于 AI 维护的 literature_catalog.json：
  - manifest 管文件状态（在哪、转没转、何时转、原始文件 hash）
  - catalog  管文献理解（讲了什么、怎么用）
两者分离，paper_id 是共同主键。

写入采用 filelock + 临时文件 + os.replace 原子替换，避免并发/中断损坏 JSON。
"""
import json
import os
from pathlib import Path
from datetime import datetime
from loguru import logger
from filelock import FileLock

from config.settings import MANIFEST_PATH


class PaperManifest:
    """papers_manifest.json 读写（原子 + 锁）"""

    def __init__(self, path: Path = MANIFEST_PATH):
        self.path = Path(path)

    @property
    def _lock_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".lock")

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
        """原子写入：加锁 → 写 tmp → os.replace → 解锁"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(self._lock_path))
        with lock:
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            # 校验 tmp 可解析
            json.loads(tmp.read_text(encoding="utf-8"))
            os.replace(tmp, self.path)

    def list_all(self) -> list[dict]:
        return self._load().get("papers", [])

    def get(self, paper_id: str) -> dict | None:
        for p in self.list_all():
            if p.get("paper_id") == paper_id:
                return p
        return None

    def has(self, paper_id: str) -> bool:
        return self.get(paper_id) is not None

    def find_by_sha256(self, sha256: str) -> dict | None:
        """按原始文件 sha256 查找记录（用于去重）"""
        for p in self.list_all():
            if p.get("sha256") == sha256:
                return p
        return None

    def upsert(self, paper_id: str, raw_pdf: str, markdown: str, images_dir: str,
               status: str = "converted", images_count: int = 0, md_chars: int = 0,
               converted_at: str | None = None,
               raw_filename: str = "", raw_stem: str = "",
               sha256: str = "", file_size: int = 0, mtime: str = "",
               backend: str = "", method: str = "") -> dict:
        """新增或更新一条记录（原子写入）"""
        data = self._load()
        papers = data.get("papers", [])
        entry = {
            "paper_id": paper_id,
            "raw_pdf": raw_pdf,
            "raw_filename": raw_filename or Path(raw_pdf).name,
            "raw_stem": raw_stem or Path(raw_pdf).stem,
            "sha256": sha256,
            "file_size": file_size,
            "mtime": mtime,
            "markdown": markdown,
            "images_dir": images_dir,
            "status": status,
            "backend": backend,
            "method": method,
            "images_count": images_count,
            "md_chars": md_chars,
            "converted_at": converted_at or datetime.now().isoformat(timespec="seconds"),
        }
        # 替换已有
        for i, p in enumerate(papers):
            if p.get("paper_id") == paper_id:
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
