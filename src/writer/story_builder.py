"""科研故事线构建：基于精读笔记 + 证据表组织博士论文级故事线

生成 story_plan.md、chapter_outline.md 模板 + 故事线 prompt。
"""
from pathlib import Path

from src.writer.job_manager import JobManager


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else "(尚未生成)"


def build_story(job_id: str, jm: JobManager | None = None) -> dict:
    jm = jm or JobManager()
    jdir = jm.job_dir(job_id)
    plan_dir = jdir / "planning"
    read_dir = jdir / "reading"

    norm = _read(jdir / "input" / "normalized_task.md")
    # 汇总精读笔记
    notes_dir = read_dir / "paper_notes"
    notes_text = ""
    if notes_dir.exists():
        for n in sorted(notes_dir.glob("*.md")):
            notes_text += f"\n\n## {n.stem}\n\n" + _read(n)[:2000]
    evidence = _read(read_dir / "evidence_table.md")

    story_plan = plan_dir / "story_plan.md"
    story_plan.write_text(
        "# 科研故事线（story_plan）\n\n> 由 story_builder 生成骨架，请用大模型补全（见故事线 prompt）。\n\n"
        "## 故事递进（博士论文标准）\n"
        "1. 大背景：为什么这个问题重要？\n"
        "2. 观测/模拟/实验困难在哪里？\n"
        "3. 传统方法解决了什么？\n"
        "4. 传统方法还缺什么？\n"
        "5. 关键物理机制是什么？\n"
        "6. 现有模型/实验如何描述这个机制？\n"
        "7. 为什么还需要新的研究？\n"
        "8. 本研究准备怎么推进？\n"
        "9. introduction 应该怎么铺垫？\n"
        "10. method 应该如何承接？\n"
        "\n（逐条待填，每条标注支撑文献 bib_key）\n", encoding="utf-8")

    outline = plan_dir / "chapter_outline.md"
    outline.write_text(
        "# 章节大纲（chapter_outline）\n\n> 待大模型基于故事线补全。\n\n"
        "## Introduction\n- （待填）\n\n## Method\n- （待填）\n",
        encoding="utf-8")

    prompt = f"""你是博士论文导师。请基于下面的研究任务、精读笔记与证据表，组织博士论文级科研故事线。

要求按 10 步递进输出故事线（大背景→困难→传统方法→不足→关键机制→现有描述→新研究必要性→本研究推进→intro铺垫→method承接），
每步标注支撑文献 bib_key，并给出 introduction 与 method 的章节大纲。

# 研究任务
{norm}

# 精读笔记（节选）
{notes_text or '(暂无，请先生成精读笔记)'}

# 证据表
{evidence}
"""
    prompt_path = jdir / "logs" / "prompts" / "03_storyline_prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")

    jm.set_step(job_id, "story_built", True)
    return {
        "prompt": prompt,
        "prompt_path": str(prompt_path),
        "story_plan": str(story_plan),
        "chapter_outline": str(outline),
    }
