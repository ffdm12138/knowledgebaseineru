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

    @staticmethod
    def _empty_data() -> dict:
        return {
            "version": "0.1",
            "description": "System-maintained file ledger of converted papers.",
            "papers": [],
        }

    def _load(self, strict: bool = False) -> dict:
        """读取 manifest JSON。

        strict=False：只读场景，损坏时 warning + 返回空结构。
        strict=True：写操作场景，损坏时抛 RuntimeError，防止静默覆盖。
        """
        if not self.path.exists():
            return self._empty_data()
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"manifest JSON 解析失败: {e}")
            if strict:
                raise RuntimeError(
                    f"manifest JSON 损坏 ({self.path})，"
                    f"拒绝写操作以防静默覆盖。请手动修复或从备份恢复。") from e
            logger.warning(f"manifest 读取失败，返回空结构（只读）: {e}")
            return self._empty_data()

    def _save_raw(self, data: dict) -> None:
        """无锁原子写入：调用方已持有锁时使用"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        json.loads(tmp.read_text(encoding="utf-8"))
        os.replace(tmp, self.path)

    def _save(self, data: dict) -> None:
        """原子写入：加锁 → 写 tmp → os.replace → 解锁"""
        lock = FileLock(str(self._lock_path))
        with lock:
            self._save_raw(data)

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

    def _locked_update(self, fn) -> None:
        """事务级锁：锁住完整的读-改-写周期，避免并发覆盖。
        JSON 损坏时抛 RuntimeError，防止静默覆盖成空库。"""
        lock = FileLock(str(self._lock_path))
        with lock:
            data = self._load(strict=True)
            fn(data)
            self._save_raw(data)

    def upsert(self, paper_id: str, raw_pdf: str, markdown: str, images_dir: str,
               status: str = "converted", images_count: int = 0, md_chars: int = 0,
               converted_at: str | None = None,
               raw_filename: str = "", raw_stem: str = "",
               sha256: str = "", file_size: int = 0, mtime: str = "",
               backend: str = "", method: str = "") -> dict:
        """新增或更新一条记录（事务级原子写入）"""
        entry_out = {}

        def _upsert(data):
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
            for i, p in enumerate(papers):
                if p.get("paper_id") == paper_id:
                    if converted_at is None and p.get("converted_at"):
                        entry["converted_at"] = p["converted_at"]
                    papers[i] = entry
                    break
            else:
                papers.append(entry)
            data["papers"] = papers
            nonlocal entry_out
            entry_out = entry
        self._locked_update(_upsert)
        logger.info(f"manifest 更新: {paper_id} ({status})")
        return entry_out

    def delete(self, paper_id: str) -> bool:
        result = [False]
        def _del(data):
            papers = data.get("papers", [])
            new = [p for p in papers if p.get("paper_id") != paper_id]
            if len(new) != len(papers):
                data["papers"] = new
                result[0] = True
        self._locked_update(_del)
        return result[0]

    def stats(self) -> dict:
        papers = self.list_all()
        return {
            "total_papers": len(papers),
            "total_images": sum(p.get("images_count", 0) for p in papers),
            "total_md_chars": sum(p.get("md_chars", 0) for p in papers),
        }
