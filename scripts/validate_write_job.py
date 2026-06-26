"""校验写作任务产物完整性（内容可用性校验，非仅文件存在）

检查项见 Phase 8 规范：基础文件、状态、内容（TODO 模板识别、字符阈值、引用一致、
图路径与 source README、证据表有效 claim、故事结构）。
通过后设置 run_meta.steps.validated=True, status=validated。
退出码 0 通过，1 有 fatal 错误。
用法: python scripts/validate_write_job.py --job 001_xxx
"""
import re
import sys
import json
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from loguru import logger
from src.writer.job_manager import JobManager
from src.writer.bib_manager import validate_job_citations, validate_job_bib, portability_check
from src.writer.catalog_matcher import load_selected


TODO_MARKERS = ["TODO", "待填", "TEMPLATE_ONLY", "由大模型补全", "待补全"]
MIN_TEX_CHARS = 120


def _has_todo(text: str) -> bool:
    return any(m in text for m in TODO_MARKERS)


def validate_job(job_id: str, jm: "JobManager | None" = None) -> dict:
    """核心校验逻辑（供 CLI 与 API 共用）。返回
    {valid, errors, warnings, portable, cited_keys, bib_keys}。
    通过时设置 run_meta.steps.validated=True, status=validated。"""
    jm = jm or JobManager()
    jdir = jm.job_dir(job_id)
    errors = []
    warnings = []
    if not jdir.exists():
        return {"valid": False, "errors": [f"任务不存在: {job_id}"], "warnings": [],
                "portable": False, "cited_keys": [], "bib_keys": []}

    # ---- 基础文件 ----
    must = {
        "logs/run_meta.json": jdir / "logs" / "run_meta.json",
        "input/research_input.md": jdir / "input" / "research_input.md",
        "input/normalized_task.md": jdir / "input" / "normalized_task.md",
        "planning/selected_papers.json": jdir / "planning" / "selected_papers.json",
        "reading/evidence_table.md": jdir / "reading" / "evidence_table.md",
        "planning/story_plan.md": jdir / "planning" / "story_plan.md",
        "planning/chapter_outline.md": jdir / "planning" / "chapter_outline.md",
        "tex/main.tex": jdir / "tex" / "main.tex",
        "tex/sections/introduction.tex": jdir / "tex" / "sections" / "introduction.tex",
        "tex/sections/method.tex": jdir / "tex" / "sections" / "method.tex",
        "tex/references.bib": jdir / "tex" / "references.bib",
    }
    for name, p in must.items():
        if not p.exists():
            errors.append(f"缺少 {name}")

    meta = jm.load_meta(job_id) or {"steps": {}}
    steps = meta.get("steps", {})

    if must["planning/selected_papers.json"].exists():
        sel = load_selected(job_id, jm)
        if sel.get("selection_status") != "confirmed":
            errors.append("selected_papers.json 未确认（selection_status != confirmed）")
        elif not sel.get("selected_papers"):
            errors.append("selected_papers.json confirmed 但 selected_papers 为空")
    for step in ["catalog_selection_confirmed", "deep_read_notes_filled",
                 "story_plan_filled", "tex_template_generated", "tex_content_filled"]:
        if not steps.get(step):
            errors.append(f"run_meta.steps.{step} 不为 True")

    for name in ["introduction", "method"]:
        p = jdir / "tex" / "sections" / f"{name}.tex"
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        if "TEMPLATE_ONLY" in text:
            errors.append(f"{name}.tex 仍含 TEMPLATE_ONLY 模板标记")
        elif _has_todo(text):
            errors.append(f"{name}.tex 仍含 TODO/待填 标记")
        elif len(re.sub(r"\s+", "", re.sub(r"%.*", "", text))) < MIN_TEX_CHARS:
            errors.append(f"{name}.tex 正文字符数不足 {MIN_TEX_CHARS}")

    cite = validate_job_citations(job_id, jm=jm)
    for k in cite["missing_in_bib"]:
        errors.append(f"\\cite{{{k}}} 在 references.bib 中找不到")
    for k in cite["unused_in_bib"]:
        warnings.append(f"references.bib 中 {k} 未被引用")
    errors += [f"job bib: {e}" for e in validate_job_bib(job_id, jm=jm)]

    for tex in jdir.rglob("*.tex"):
        text = tex.read_text(encoding="utf-8")
        for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}", text):
            ref = m.group(1).strip()
            resolved = (tex.parent / ref).resolve()
            try:
                rel = resolved.relative_to(jdir.resolve())
                if "figures" not in str(rel).replace("\\", "/"):
                    errors.append(f"{tex.name}: \\includegraphics{{{ref}}} 未指向 figures/")
            except ValueError:
                errors.append(f"{tex.name}: \\includegraphics{{{ref}}} 指向 job 目录外")
                continue
            if not resolved.exists():
                errors.append(f"{tex.name}: \\includegraphics{{{ref}}} 文件不存在")
            else:
                parts = Path(ref).parts
                if len(parts) >= 2:
                    pid_dir = parts[-2]
                    readme = jdir / "figures" / pid_dir / "README.md"
                    if not readme.exists():
                        errors.append(f"figures/{pid_dir}/ 缺少 README.md（图源记录）")
                    elif "original_path" not in readme.read_text(encoding="utf-8"):
                        errors.append(f"figures/{pid_dir}/README.md 缺少 original_path")

    ev = must["reading/evidence_table.md"]
    if ev.exists():
        ev_text = ev.read_text(encoding="utf-8")
        valid_rows = [ln for ln in ev_text.splitlines()
                      if ln.startswith("| ") and "待填" not in ln
                      and ln.count("|") >= 5 and not ln.startswith("| Claim")]
        valid_rows = [r for r in valid_rows if not re.match(r"^\|\s*[-:|]+\s*\|", r)]
        if not valid_rows:
            errors.append("evidence_table.md 无有效 claim")

    sp = must["planning/story_plan.md"]
    if sp.exists():
        spt = sp.read_text(encoding="utf-8")
        if "TEMPLATE_ONLY" in spt:
            errors.append("story_plan.md 仍是 TEMPLATE_ONLY 模板")
        for sec in ["scientific_background", "contradiction_or_gap", "mechanism_chain",
                    "literature_logic", "research_entry_point",
                    "introduction_logic", "method_logic"]:
            if sec not in spt:
                errors.append(f"story_plan.md 缺少 section: {sec}")

    port = portability_check(job_id, jm=jm)
    errors += port["errors"]

    valid = len(errors) == 0
    if valid:
        jm.set_step(job_id, "validated", True)
        jm.set_status(job_id, "validated")
    else:
        jm.set_step(job_id, "validated", False)
    return {"valid": valid, "errors": errors, "warnings": warnings,
            "portable": port["portable"], "portability_note": port["note"],
            "cited_keys": cite["cited_keys"], "bib_keys": cite["bib_keys"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    args = ap.parse_args()
    result = validate_job(args.job)
    if result["valid"]:
        logger.info(f"✅ 写作任务 {args.job} 校验通过（可移植: {result['portable']}）")
        for w in result["warnings"]:
            logger.warning(f"  ⚠ {w}")
        return 0
    logger.error(f"❌ {args.job} 发现 {len(result['errors'])} 个 fatal 问题：")
    for e in result["errors"]:
        logger.error(f"  - {e}")
    for w in result["warnings"]:
        logger.warning(f"  ⚠ {w}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
