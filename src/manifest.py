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

# 合法 status 词表（状态机）：
#   queued      已入账待转换（预留，当前上传直接进 converting）
#   converting  转换中：阻止同 sha256 重复转换
#   converted   转换完成：命中即 duplicate
#   failed      转换失败：允许显式重试
#   duplicate   重复（与 converted 等价的去重态，供查询语义使用）
#   unregistered_converted  转换完成但缺少正式 catalog metadata，不进入 catalog/index
#   conversion_failed_with_catalog / asset_missing  catalog 保留但全文资产不可读，需人工处理
# SSOT：upload_service / watcher / batch_convert 写入的 status 必须在此集合内。
VALID_STATUSES = {
    "queued", "converting", "converted", "unregistered_converted",
    "failed", "duplicate", "conversion_failed_with_catalog", "asset_missing",
}

# find_by_sha256 命中多条记录时的优先级（高 → 低）。
# 含义：converted/duplicate 优先于 converting，converting 优先于 failed。
_SHA_PRIORITY = {
    "converted": 0,
    "unregistered_converted": 0,
    "duplicate": 0,
    "converting": 1,
    "failed": 2,
    "conversion_failed_with_catalog": 3,
    "asset_missing": 3,
}


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

    def migrate(self) -> int:
        """一次性迁移旧记录到 SSOT 字段结构。

        旧记录可能用 backend 字段表示调用通道（cli/api），语义与新结构冲突。
        迁移规则（幂等）：
          - 删除旧 backend 字段
          - mineru_backend 缺失 → "hybrid-engine"（产品固定）
          - effort 缺失 → "medium"
          - runner 缺失 → 旧 backend 值或 "cli"
          - status 不在词表 → "converted"
        返回迁移的记录数。
        """
        migrated = 0

        def _migrate(data):
            nonlocal migrated
            now = datetime.now().isoformat(timespec="seconds")
            for p in data.get("papers", []):
                old_backend = p.pop("backend", None)
                changed = False
                if "mineru_backend" not in p or not p["mineru_backend"]:
                    p["mineru_backend"] = "hybrid-engine"
                    changed = True
                if "effort" not in p or not p["effort"]:
                    p["effort"] = "medium"
                    changed = True
                if "runner" not in p or not p["runner"]:
                    p["runner"] = old_backend or "cli"
                    changed = True
                if "error" not in p:
                    p["error"] = ""
                    changed = True
                if "updated_at" not in p or not p["updated_at"]:
                    p["updated_at"] = p.get("converted_at") or now
                    changed = True
                # converted_at 语义：非 converted 状态不应有新建的 converted_at
                if p.get("status") not in {"converted", "unregistered_converted"} and not p.get("converted_at"):
                    p["converted_at"] = p.get("converted_at") or ""
                if p.get("status") not in VALID_STATUSES:
                    p["status"] = "converted"
                    changed = True
                if old_backend is not None:
                    changed = True
                if changed:
                    migrated += 1

        self._locked_update(_migrate)
        if migrated:
            logger.info(f"manifest 迁移完成: {migrated} 条记录更新为 SSOT 字段")
        return migrated

    def get(self, paper_id: str) -> dict | None:
        for p in self.list_all():
            if p.get("paper_id") == paper_id:
                return p
        return None

    def has(self, paper_id: str) -> bool:
        return self.get(paper_id) is not None

    def find_by_sha256(self, sha256: str) -> dict | None:
        """按原始文件 sha256 查找记录（用于去重）。

        命中多条时按状态优先级返回：converted/duplicate > converting > failed。
        即同一文件的旧 failed 记录不会遮蔽已成功的 converted 记录。
        """
        matches = [p for p in self.list_all() if p.get("sha256") == sha256]
        if not matches:
            return None
        matches.sort(key=lambda p: _SHA_PRIORITY.get(p.get("status", ""), 3))
        return matches[0]

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
               mineru_backend: str = "", method: str = "",
               effort: str = "", runner: str = "",
               error: str = "") -> dict:
        """新增或更新一条记录（事务级原子写入）。

        SSOT 字段语义：
          mineru_backend : MinerU 解析后端（hybrid-engine/pipeline/vlm-engine），
                           来自 config.MINERU_BACKEND，不是 cli/api。
          method         : 解析方法 auto/ocr/txt。
          effort         : hybrid-engine 解析强度 medium/high。
          runner         : 本次调用通道 cli/api（来自 converter 返回）。
          error          : 失败原因（status=failed 时填）。
          converted_at   : 仅 status=converted 时写入；converting/failed 保留旧值
                           或空串，不新建。
          updated_at     : 每次 upsert 都刷新（记录最近一次状态变更时间）。
        """
        if status not in VALID_STATUSES:
            raise ValueError(
                f"非法 status: {status}，允许: {sorted(VALID_STATUSES)}")
        now = datetime.now().isoformat(timespec="seconds")
        entry_out = {}

        def _upsert(data):
            papers = data.get("papers", [])
            # 旧记录的 converted_at（若存在）
            old_converted_at = ""
            old_index = None
            for i, p in enumerate(papers):
                if p.get("paper_id") == paper_id:
                    old_converted_at = p.get("converted_at", "") or ""
                    old_index = i
                    break

            # converted_at 语义：仅 converted 写新时间；其它状态保留旧值或空
            if status in {"converted", "unregistered_converted"}:
                final_converted_at = converted_at or now
            else:
                # converting/failed/queued/duplicate：保留旧 converted_at，无则空
                final_converted_at = converted_at if converted_at is not None else old_converted_at

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
                "mineru_backend": mineru_backend,
                "method": method,
                "effort": effort,
                "runner": runner,
                "error": error,
                "images_count": images_count,
                "md_chars": md_chars,
                "converted_at": final_converted_at,
                "updated_at": now,
            }
            if old_index is not None:
                papers[old_index] = entry
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
