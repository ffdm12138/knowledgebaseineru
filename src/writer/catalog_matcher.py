"""目录匹配：根据 normalized_task 在 literature_catalog.json 中筛候选文献

语义严格区分：
  catalog_candidates.json —— 目录级候选（可含全部文献），need_fulltext 初始为 null
  selected_papers.json    —— 初始为空，仅保存人工/LLM 确认要精读的文献

match_catalog() 只设置 catalog_match_prompt_generated=True，
不设置 catalog_selection_confirmed=True。
"""
import json
from datetime import datetime
from pathlib import Path

from src.writer.job_manager import JobManager
from src.catalog import Catalog


def load_selected(job_id: str, jm: JobManager | None = None) -> dict:
    """读取 selected_papers.json，返回完整结构（不存在则返回 pending 空结构）"""
    jm = jm or JobManager()
    p = jm.job_dir(job_id) / "planning" / "selected_papers.json"
    if not p.exists():
        return {"selected_papers": [], "selection_status": "pending_llm_or_manual_review",
                "confirmed_at": None, "confirmed_by": None, "notes": ""}
    return json.loads(p.read_text(encoding="utf-8"))


def selected_paper_ids(job_id: str, jm: JobManager | None = None) -> list[str]:
    """返回已确认精读的 paper_id 列表（未确认或空则返回空列表）"""
    data = load_selected(job_id, jm)
    if data.get("selection_status") != "confirmed":
        return []
    return [p.get("paper_id") for p in data.get("selected_papers", []) if p.get("paper_id")]



def match_catalog(job_id: str, jm: JobManager | None = None,
                  catalog: Catalog | None = None,
                  force: bool = False) -> dict:
    """生成目录匹配 prompt + 候选文献。selected_papers.json 初始为空。

    覆盖保护：若 selected_papers.json 已确认（confirmed），默认拒绝覆盖（force=True 可强制重建）。
    返回 {"prompt", "prompt_path", "candidates_path", "selected_path", "reading_plan_path"}
    """
    jm = jm or JobManager()
    catalog = catalog or Catalog()
    jdir = jm.job_dir(job_id)

    norm = (jdir / "input" / "normalized_task.md").read_text(encoding="utf-8")
    compact = catalog.build_compact_catalog()
    papers = catalog.list_papers()

    # candidates：目录级候选，need_fulltext 初始 null（不默认全部 true）
    candidates = []
    for p in papers:
        cit = p.get("citation", {}) or {}
        candidates.append({
            "paper_id": p.get("paper_id"),
            "bib_key": cit.get("bib_key", ""),
            "catalog_priority": (p.get("selection_hints") or {}).get("priority", 3),
            "candidate_reason": "",  # 待 LLM/人工填
            "expected_use": "",
            "need_fulltext": None,
        })

    cand_data = {
        "topic_summary": "",
        "core_research_questions": [],
        "candidate_papers": candidates,
        "excluded_papers": [],
        "status": "prompt_generated",
    }
    cand_path = jdir / "planning" / "catalog_candidates.json"
    cand_path.write_text(json.dumps(cand_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # selected_papers.json：初始为空，待确认
    sel_path = jdir / "planning" / "selected_papers.json"
    if sel_path.exists() and not force:
        existing = load_selected(job_id, jm)
        if existing.get("selection_status") == "confirmed":
            raise RuntimeError(
                "selected_papers.json 已确认（confirmed），拒绝覆盖。传 force=True 强制重建。")
    sel_data = {
        "selected_papers": [],
        "selection_status": "pending_llm_or_manual_review",
        "confirmed_at": None,
        "confirmed_by": None,
        "notes": "",
    }
    sel_path.write_text(json.dumps(sel_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # reading_plan.md 模板
    plan = jdir / "planning" / "reading_plan.md"
    plan.write_text(
        "# 阅读计划\n\n> 由 catalog_matcher 生成骨架，请用大模型补全（见匹配 prompt）。\n\n"
        "## 研究任务摘要\n" + norm[:400] + "\n\n"
        "## 候选文献（见 catalog_candidates.json）\n\n"
        "## 最终精读列表（见 selected_papers.json，待 confirm-papers 确认）\n",
        encoding="utf-8")

    # 匹配 prompt
    prompt = f"""你是一位科研导师。请根据下面的研究任务与文献目录，判断哪些文献需要全文精读。

要求：
1. 输出 JSON，字段见下方 schema；
2. candidate_papers 给出入选文献 + 理由 + 预期用途（introduction/method/validation/discussion）+ need_fulltext(true/false)；
3. excluded_papers 给出排除文献 + 理由；
4. 只基于目录信息判断，不编造目录里没有的文献。

# 研究任务
{norm}

# 文献目录（紧凑视图）
{compact}

# 输出 schema
{{
  "topic_summary": "",
  "core_research_questions": [],
  "candidate_papers": [
    {{"paper_id": "", "bib_key": "", "catalog_priority": 3,
      "candidate_reason": "", "expected_use": "", "need_fulltext": true}}
  ],
  "excluded_papers": [{{"paper_id": "", "reason": ""}}]
}}
"""
    prompt_path = jdir / "logs" / "prompts" / "01_catalog_matching_prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")

    # 只标记 prompt 已生成，不标记 selection 已确认
    jm.set_step(job_id, "catalog_match_prompt_generated", True)
    return {
        "prompt": prompt,
        "prompt_path": str(prompt_path),
        "candidates_path": str(cand_path),
        "selected_path": str(sel_path),
        "reading_plan_path": str(plan),
        "selection_confirmed": False,
    }


def confirm_selected_papers(job_id: str, selected: list[dict],
                            confirmed_by: str = "manual",
                            jm: JobManager | None = None,
                            catalog: Catalog | None = None) -> dict:
    """确认最终精读文献列表。

    selected: [{"paper_id","reason","expected_use","priority"}]（其余字段自动从 catalog 补全）
    写入 selected_papers.json（selection_status=confirmed），更新 run_meta，
    设置 catalog_selection_confirmed=True。
    """
    jm = jm or JobManager()
    catalog = catalog or Catalog()
    jdir = jm.job_dir(job_id)

    if not selected:
        raise ValueError("selected 不能为空")

    bib_map = {p["paper_id"]: (p.get("citation") or {}).get("bib_key", "")
               for p in catalog.list_papers()}
    paper_ids = []
    enriched = []
    for item in selected:
        pid = item.get("paper_id")
        if not pid:
            raise ValueError("selected 条目缺少 paper_id")
        bk = item.get("bib_key") or bib_map.get(pid, "")
        enriched.append({
            "paper_id": pid,
            "bib_key": bk,
            "reason": item.get("reason", ""),
            "expected_use": item.get("expected_use", ""),
            "priority": item.get("priority", 3),
        })
        paper_ids.append(pid)

    sel_data = {
        "selected_papers": enriched,
        "selection_status": "confirmed",
        "confirmed_at": datetime.now().isoformat(timespec="seconds"),
        "confirmed_by": confirmed_by,
        "notes": "",
    }
    sel_path = jdir / "planning" / "selected_papers.json"
    sel_path.write_text(json.dumps(sel_data, ensure_ascii=False, indent=2), encoding="utf-8")

    jm.set_step(job_id, "catalog_selection_confirmed", True,
                extra={"selected_papers": paper_ids})
    jm.append_note(job_id, f"确认精读文献 {len(paper_ids)} 篇 by {confirmed_by}")
    return {"selected_path": str(sel_path), "selected_papers": enriched,
            "paper_ids": paper_ids, "selection_confirmed": True}
