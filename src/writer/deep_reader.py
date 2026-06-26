"""全文精读：读取确认的 selected_papers 全文，生成精读笔记模板 + 证据表 + 候选图

状态语义：
  deep_read() 只设置 deep_read_prompt_generated=True，不设置 deep_read_notes_filled。
  mark_deep_reading_filled() 校验笔记非空模板后设置 deep_read_notes_filled=True。

前置：selected_papers.json 必须 selection_status=confirmed。
"""
import re
from pathlib import Path

from src.writer.job_manager import JobManager
from src.library import PaperLibrary
from src.catalog import Catalog
from src.writer.catalog_matcher import load_selected, selected_paper_ids
from config.settings import PAPER_MD_MAX_CHARS, PAPERS_DIR


# 模板/待填标记（用于判断笔记是否仍是空模板）
TODO_MARKERS = ["TODO", "待填", "（待填）", "TEMPLATE_ONLY", "由大模型补全", "待补全"]

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


def deep_read(job_id: str, paper_ids: list[str] | None = None,
              jm: JobManager | None = None,
              library: PaperLibrary | None = None,
              catalog: Catalog | None = None) -> dict:
    """对 selected_papers 生成精读笔记模板 + 证据表 + 候选图 + 精读 prompt。

    前置：catalog_selection_confirmed=True。
    paper_ids 为 None 时取 selected_papers.json 中已确认的列表。
    """
    jm = jm or JobManager()
    library = library or PaperLibrary()
    catalog = catalog or Catalog()
    jdir = jm.job_dir(job_id)

    # 前置校验：必须已确认 selected
    sel = load_selected(job_id, jm)
    if sel.get("selection_status") != "confirmed":
        raise RuntimeError(
            "Cannot deep-read before selected_papers.json is confirmed. "
            "Run confirm-papers first.")
    if paper_ids is None:
        paper_ids = [p["paper_id"] for p in sel.get("selected_papers", [])]
    if not paper_ids:
        raise RuntimeError("selected_papers 为空，无可精读文献。")

    # 校验每个 paper_id 的 paper.md 存在
    for pid in paper_ids:
        if not library.exists(pid):
            raise RuntimeError(f"找不到 paper.md: {pid} (data/papers/{pid}/paper.md)")

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

    ev = jdir / "reading" / "evidence_table.md"
    ev.write_text(
        "# 证据表\n\n"
        "| Claim | Supporting paper | Bib key | Evidence location | Use in thesis |\n"
        "|---|---|---|---|---|\n"
        "| （待填） | | | | |\n", encoding="utf-8")

    fc = jdir / "reading" / "figure_candidates.md"
    fc.write_text("# 候选引用图片清单\n\n> 由 deep_reader 自动列出图片，图意待填。\n\n"
                  + "".join(fig_lines), encoding="utf-8")

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

    # 只标记 prompt 已生成，不标记 notes 已填
    jm.set_step(job_id, "deep_read_prompt_generated", True)
    return {
        "prompt": prompt,
        "prompt_path": str(prompt_path),
        "notes": created_notes,
        "evidence_table": str(ev),
        "figure_candidates": str(fc),
        "notes_filled": False,
    }


def _section_filled(text: str) -> bool:
    """判断一段笔记文本是否已被实质填充（非纯模板）"""
    # 去掉标题行后，正文里去掉待填标记，看是否还有实质内容
    body = re.sub(r"^#.*$", "", text, flags=re.MULTILINE)
    body = re.sub(r"^\|.*\|$", "", body, flags=re.MULTILINE)  # 去表头/占位行
    for marker in TODO_MARKERS:
        body = body.replace(marker, "")
    # 剩余非空白字符数
    remaining = len(re.sub(r"\s+", "", body))
    return remaining >= 20


def validate_deep_reading_notes(job_id: str, jm: JobManager | None = None) -> list[str]:
    """校验精读笔记是否已被实质填充。返回错误列表（空=通过）"""
    jm = jm or JobManager()
    jdir = jm.job_dir(job_id)
    errors = []
    pids = selected_paper_ids(job_id, jm)
    if not pids:
        return ["selected_papers 未确认或为空，无法校验精读笔记"]

    notes_dir = jdir / "reading" / "paper_notes"
    for pid in pids:
        np = notes_dir / f"{pid}.md"
        if not np.exists():
            errors.append(f"缺少精读笔记: reading/paper_notes/{pid}.md")
            continue
        if not _section_filled(np.read_text(encoding="utf-8")):
            errors.append(f"精读笔记仍为模板/待填: {pid}.md")

    # 证据表至少一条有效 claim
    ev = jdir / "reading" / "evidence_table.md"
    if ev.exists():
        ev_text = ev.read_text(encoding="utf-8")
        # 有效行：表格数据行，含 paper_id 或 bib_key 标识，非占位
        valid_rows = [ln for ln in ev_text.splitlines()
                      if ln.startswith("| ") and "待填" not in ln
                      and ln.count("|") >= 5 and not ln.startswith("| Claim")]
        # 去掉表头分隔行
        valid_rows = [r for r in valid_rows if not re.match(r"^\|\s*[-:|]+\s*\|", r)]
        if not valid_rows:
            errors.append("evidence_table.md 无有效 claim（至少一条含 paper_id/bib_key 的数据行）")
        else:
            # 检查证据表覆盖率：选中的 paper_id 至少 70% 出现在 evidence 行中
            referenced_pids = set()
            for row in valid_rows:
                for pid in pids:
                    if pid in row:
                        referenced_pids.add(pid)
            if len(referenced_pids) < max(1, len(pids) * 0.7):
                missing = set(pids) - referenced_pids
                errors.append(f"evidence_table 覆盖不足（{len(referenced_pids)}/{len(pids)} 篇），"
                              f"缺少: {sorted(missing)}")
    else:
        errors.append("缺少 reading/evidence_table.md")
    return errors


def mark_deep_reading_filled(job_id: str, jm: JobManager | None = None) -> dict:
    """校验精读笔记通过后设置 deep_read_notes_filled=True"""
    jm = jm or JobManager()
    errors = validate_deep_reading_notes(job_id, jm)
    if errors:
        return {"filled": False, "errors": errors}
    jm.set_step(job_id, "deep_read_notes_filled", True)
    return {"filled": True, "errors": []}
