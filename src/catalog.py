"""文献目录：literature_catalog.json 的加载/校验/查询

catalog 是 AI 维护的"文献理解目录"，不是搜索索引。

写入采用 filelock + 临时文件 + os.replace 原子替换，与 manifest 一致防止中断损坏 JSON。
"""
import json
import os
from pathlib import Path
from loguru import logger
from filelock import FileLock

from config.settings import CATALOG_PATH


# 每条 paper 条目必须包含的字段（嵌套结构用点号）
REQUIRED_FIELDS = {
    "paper_id", "title", "authors", "year", "venue", "doi",
    "raw_pdf", "markdown", "images_dir", "status",
    "ai_summary", "tags", "selection_hints", "notes", "citation",
}
AI_SUMMARY_FIELDS = {
    "one_sentence", "background_problem", "research_question", "method",
    "data_or_experiment", "main_findings", "key_equations_or_models",
    "important_figures", "limitations", "relevance_to_my_work", "possible_use_in_paper",
}
TAGS_FIELDS = {"topic", "method", "material_or_region", "variables", "model_names"}
HINTS_FIELDS = {"read_when_question_contains", "do_not_use_for", "priority"}
CITATION_FIELDS = {"bib_key", "bibtex", "citation_style_name", "source", "verified"}
VALID_STATUS = {"unsummarized", "summarized", "draft"}


class Catalog:
    """literature_catalog.json 读写与校验"""

    def __init__(self, path: Path = CATALOG_PATH):
        self.path = Path(path)

    @property
    def _lock_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".lock")

    def load(self) -> dict:
        if not self.path.exists():
            return {"version": "0.1", "description": "", "papers": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"catalog JSON 解析失败: {e}")
            return {"version": "0.1", "description": "", "papers": []}

    def save(self, data: dict) -> None:
        """原子写入：加锁 → 写 tmp → 校验 JSON → os.replace → 解锁"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(self._lock_path))
        raw = json.dumps(data, ensure_ascii=False, indent=2)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with lock:
            tmp.write_text(raw, encoding="utf-8")
            # 校验写入完整性：回读确认可解析
            json.loads(tmp.read_text(encoding="utf-8"))
            os.replace(tmp, self.path)

    def list_papers(self) -> list[dict]:
        return self.load().get("papers", [])

    def get(self, paper_id: str) -> dict | None:
        for p in self.list_papers():
            if p.get("paper_id") == paper_id:
                return p
        return None

    def has(self, paper_id: str) -> bool:
        return self.get(paper_id) is not None

    def upsert(self, entry: dict) -> None:
        data = self.load()
        papers = data.get("papers", [])
        for i, p in enumerate(papers):
            if p.get("paper_id") == entry.get("paper_id"):
                papers[i] = entry
                break
        else:
            papers.append(entry)
        data["papers"] = papers
        self.save(data)

    def delete(self, paper_id: str) -> bool:
        data = self.load()
        papers = data.get("papers", [])
        new = [p for p in papers if p.get("paper_id") != paper_id]
        if len(new) == len(papers):
            return False
        data["papers"] = new
        self.save(data)
        return True

    def validate(self) -> list[str]:
        """返回错误信息列表，空表示通过"""
        errors = []
        bib_keys_seen = []
        data = self.load()
        if "papers" not in data:
            return ["顶层缺少 papers 字段"]
        papers = data["papers"]
        seen_ids = set()
        for i, p in enumerate(papers):
            ctx = f"papers[{i}] (paper_id={p.get('paper_id', '?')})"
            for f in REQUIRED_FIELDS:
                if f not in p:
                    errors.append(f"{ctx} 缺少字段 {f}")
            pid = p.get("paper_id")
            if not pid:
                errors.append(f"{ctx} paper_id 为空")
            elif pid in seen_ids:
                errors.append(f"{ctx} paper_id 重复")
            else:
                seen_ids.add(pid)
            if p.get("status") not in VALID_STATUS:
                errors.append(f"{ctx} status 非法: {p.get('status')} (应为 {VALID_STATUS})")
            ai = p.get("ai_summary", {})
            if not isinstance(ai, dict):
                errors.append(f"{ctx} ai_summary 不是对象")
            else:
                for f in AI_SUMMARY_FIELDS:
                    if f not in ai:
                        errors.append(f"{ctx} ai_summary 缺少 {f}")
            tags = p.get("tags", {})
            if not isinstance(tags, dict):
                errors.append(f"{ctx} tags 不是对象")
            else:
                for f in TAGS_FIELDS:
                    if f not in tags:
                        errors.append(f"{ctx} tags 缺少 {f}")
            hints = p.get("selection_hints", {})
            if not isinstance(hints, dict):
                errors.append(f"{ctx} selection_hints 不是对象")
            else:
                for f in HINTS_FIELDS:
                    if f not in hints:
                        errors.append(f"{ctx} selection_hints 缺少 {f}")
                pri = hints.get("priority")
                if pri is not None and not (isinstance(pri, int) and 1 <= pri <= 5):
                    errors.append(f"{ctx} priority 应为 1-5 整数, 实为 {pri}")
            cit = p.get("citation", {})
            if not isinstance(cit, dict):
                errors.append(f"{ctx} citation 不是对象")
            else:
                for f in CITATION_FIELDS:
                    if f not in cit:
                        errors.append(f"{ctx} citation 缺少 {f}")
                bk = cit.get("bib_key")
                if bk:
                    bib_keys_seen.append((bk, ctx))
                else:
                    errors.append(f"{ctx} citation.bib_key 为空")
                bt = cit.get("bibtex", "")
                if bt and not bt.strip().startswith("@"):
                    errors.append(f"{ctx} citation.bibtex 应以 @ 开头")
        # bib_key 全局唯一
        seen = set()
        for bk, ctx in bib_keys_seen:
            if bk in seen:
                errors.append(f"{ctx} bib_key 重复: {bk}")
            else:
                seen.add(bk)
        return errors

    def unsummarized(self, manifest_paper_ids: list[str]) -> list[str]:
        """返回 manifest 中存在但 catalog 缺失或未总结的 paper_id"""
        papers = {p.get("paper_id"): p for p in self.list_papers()}
        out = []
        for pid in manifest_paper_ids:
            entry = papers.get(pid)
            if entry is None or entry.get("status") != "summarized":
                out.append(pid)
        return out

    def build_compact_catalog(self) -> str:
        """生成给大模型看的紧凑目录文本：每篇一行核心摘要"""
        lines = ["# 文献目录（紧凑视图）", ""]
        for p in self.list_papers():
            pid = p.get("paper_id", "?")
            ai = p.get("ai_summary", {}) or {}
            one = ai.get("one_sentence", "") or "(未总结)"
            pri = (p.get("selection_hints") or {}).get("priority", "-")
            tags = p.get("tags", {}) or {}
            topic = ",".join(tags.get("topic", []))
            lines.append(f"- [{pri}] {pid}  {one}  [主题:{topic}]")
        return "\n".join(lines)
