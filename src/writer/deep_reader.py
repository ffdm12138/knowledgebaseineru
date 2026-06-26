"""全文精读：读取选中文献 paper.md，生成精读笔记模板 + 证据表 + 候选图清单

生成 deep reading prompt，由大模型填实 paper_notes 内容。
"""
import json
from pathlib import Path

from src.writer.job_manager import JobManager
from src.library import PaperLibrary
from src.catalog import Catalog
from config.settings import PAPER_MD_MAX_CHARS


NOTE_TEMPLATE = """# {pid}

## Citation
\\cite{{{bib_key}}}

## Why this paper is selected
（待填）

## Research problem
（待填）

## Method
（待填）

## Key equations / parameterizations
（待填）

## Key figures
（待填）

## Main findings
（待填）

## Limitations
（待填）

## How it supports my story
（待填）

## Directly usable sentences or ideas
（待填）

## Evidence extracted from full text
（待填，标注 paper.md 中可定位的位置）

## Figure candidates
（待填：列出 data/papers/{pid}/images/ 中值得引用的图及理由）
"""


def _figure_candidates_block(pid: str, library: PaperLibrary) -> str:
    imgs = library.list_images(pid)
    if not imgs:
        return f"- {pid}: 无图片\n"
    lines = [f"- {pid}: {len(imgs)} 张图，候选："]
    for name in imgs[:10]:
        lines.append(f"  - `{name}` ——（待填图意与是否引用）")
    return "\n".join(lines) + "\n"


def deep_read(job_id: str, paper_ids: list[str],
              jm: JobManager | None = None,
              library: PaperLibrary | None = None,
              catalog: Catalog | None = None) -> dict:
    """对指定 paper_ids 生成精读笔记模板 + 证据表 + 候选图清单 + 精读 prompt"""
    jm = jm or JobManager()
    library = library or PaperLibrary()
    catalog = catalog or Catalog()
    jdir = jm.job_dir(job_id)

    notes_dir = jdir / "reading" / "paper_notes"
    notes_dir.mkdir(parents=True, exist_ok=True)

    bib_key_of = {p["paper_id"]: (p.get("citation") or {}).get("bib_key", "")
                  for p in catalog.list_papers()}
    full_texts = library.read_multiple(paper_ids, max_chars_each=PAPER_MD_MAX_CHARS)

    created_notes = []
    fig_lines = []
    for pid in paper_ids:
        bib = bib_key_of.get(pid, "")
        note_path = notes_dir / f"{pid}.md"
        note_path.write_text(NOTE_TEMPLATE.format(pid=pid, bib_key=bib), encoding="utf-8")
        created_notes.append(str(note_path))
        fig_lines.append(_figure_candidates_block(pid, library))

    # evidence_table.md
    ev = jdir / "reading" / "evidence_table.md"
    ev.write_text(
        "# 证据表\n\n"
        "| Claim | Supporting paper | Bib key | Evidence location | Use in thesis |\n"
        "|---|---|---|---|---|\n"
        "| （待填） | | | | |\n", encoding="utf-8")

    # figure_candidates.md
    fc = jdir / "reading" / "figure_candidates.md"
    fc.write_text("# 候选引用图片清单\n\n> 由 deep_reader 自动列出图片，图意待填。\n\n"
                  + "".join(fig_lines), encoding="utf-8")

    # 精读 prompt
    fulltext_block = ""
    for pid in paper_ids:
        md = full_texts.get(pid, "(读取失败)")
        bib = bib_key_of.get(pid, "")
        fulltext_block += f"\n\n## [{pid}]  \\cite{{{bib}}}\n\n{md}\n"

    prompt = f"""请对下面若干篇文献全文逐一精读，为每篇产出结构化笔记，并整合一份证据表。

每篇笔记字段：
Why this paper is selected / Research problem / Method / Key equations / Key figures /
Main findings / Limitations / How it supports my story / Directly usable sentences /
Evidence extracted from full text（标注可定位位置）/ Figure candidates（从图片清单中选）。

证据表按 `| Claim | Supporting paper | Bib key | Evidence location | Use in thesis |` 输出。
所有结论必须能在全文中找到证据，禁止编造。
# 文献全文
{fulltext_block}
"""
    prompt_path = jdir / "logs" / "prompts" / "02_deep_reading_prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")

    jm.set_step(job_id, "deep_reading_done", True,
                extra={"selected_papers": paper_ids})
    return {
        "prompt": prompt,
        "prompt_path": str(prompt_path),
        "notes": created_notes,
        "evidence_table": str(ev),
        "figure_candidates": str(fc),
    }
