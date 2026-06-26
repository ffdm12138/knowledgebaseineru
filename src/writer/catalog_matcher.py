"""目录匹配：根据 normalized_task 在 literature_catalog.json 中筛候选文献

不做 embedding，基于 ai_summary / tags / selection_hints / priority 让大模型判断。
生成 catalog_candidates.json、reading_plan.md、selected_papers.json（模板）。
"""
import json
from pathlib import Path

from src.writer.job_manager import JobManager
from src.catalog import Catalog


def match_catalog(job_id: str, jm: JobManager | None = None,
                  catalog: Catalog | None = None) -> dict:
    """生成目录匹配 prompt + 候选文献模板。

    返回 {"prompt", "prompt_path", "candidates_path", "selected_path", "reading_plan_path"}
    """
    jm = jm or JobManager()
    catalog = catalog or Catalog()
    jdir = jm.job_dir(job_id)

    norm = (jdir / "input" / "normalized_task.md").read_text(encoding="utf-8")
    compact = catalog.build_compact_catalog()
    papers = catalog.list_papers()

    # 候选文献模板：全部列入，priority/bib_key 取自 catalog，理由留空待 LLM/人工填
    candidates = []
    for p in papers:
        cit = p.get("citation", {}) or {}
        candidates.append({
            "paper_id": p.get("paper_id"),
            "bib_key": cit.get("bib_key", ""),
            "title": p.get("title", ""),
            "year": p.get("year"),
            "priority": (p.get("selection_hints") or {}).get("priority", 3),
            "reason": "",  # 待填：为什么入选
            "expected_use": "",  # introduction / method / validation / discussion
            "need_fulltext": True,
        })

    cand_path = jdir / "planning" / "catalog_candidates.json"
    cand_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")

    # selected_papers.json：与 candidates 同结构，用户/LLM 裁剪后保留最终精读列表
    sel_path = jdir / "planning" / "selected_papers.json"
    sel_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")

    # reading_plan.md 模板
    plan = jdir / "planning" / "reading_plan.md"
    plan.write_text(
        "# 阅读计划\n\n> 由 catalog_matcher 生成骨架，请用大模型补全（见匹配 prompt）。\n\n"
        "## 研究任务摘要\n" + norm[:400] + "\n\n"
        "## 候选文献（见 catalog_candidates.json）\n\n"
        "## 最终精读列表（见 selected_papers.json，待裁剪）\n",
        encoding="utf-8")

    # 匹配 prompt
    prompt = f"""你是一位科研导师。请根据下面的研究任务与文献目录，判断哪些文献需要全文精读。

要求：
1. 输出 JSON，字段见下方 schema；
2. candidate_papers 给出入选文献 + 理由 + 预期用途（introduction/method/validation/discussion）；
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
    {{"paper_id": "", "bib_key": "", "priority": 5, "reason": "",
      "expected_use": "", "need_fulltext": true}}
  ],
  "excluded_papers": [{{"paper_id": "", "reason": ""}}]
}}
"""
    prompt_path = jdir / "logs" / "prompts" / "01_catalog_matching_prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")

    jm.set_step(job_id, "catalog_matched", True)
    return {
        "prompt": prompt,
        "prompt_path": str(prompt_path),
        "candidates_path": str(cand_path),
        "selected_path": str(sel_path),
        "reading_plan_path": str(plan),
    }
