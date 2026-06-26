"""LaTeX 项目生成：main.tex + introduction.tex + method.tex + references.bib

生成骨架（含 \\cite 占位与 \\input 结构）+ TeX 写作 prompt。
references.bib 由 bib_manager 从全局库按 selected_papers 抽取。
"""
import json
from pathlib import Path

from src.writer.job_manager import JobManager
from src.writer.bib_manager import export_job_bib, validate_job_citations
from src.catalog import Catalog


MAIN_TEX = r"""\documentclass[12pt,a4paper]{ctexart}

\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{natbib}
\usepackage{geometry}
\usepackage{hyperref}

\geometry{margin=2.5cm}

\title{__TITLE__}
\author{}
\date{}

\begin{document}

\maketitle

\input{sections/introduction}
\input{sections/method}

\bibliographystyle{plainnat}
\bibliography{references}

\end{document}
"""

INTRO_TEX = r"""% Introduction —— 博士论文标准
% 结构：宏观重要性 → 气候/工程/灾害意义 → 已有认识 → 实验/观测/理论/模型分别解决什么
%      → 关键机制链条 → 当前方法不足 → 本研究切入点 → 研究目标与贡献
% 所有引用使用 \cite{bib_key}，禁止裸作者年份，禁止编造。

\section{Introduction}

% TODO: 由大模型基于 story_plan / evidence_table / paper_notes 填写。
% 提示：不要简单堆文献，要有矛盾递进，从问题导向引出方法。
"""

METHOD_TEX = r"""% Method
% 综述型 method 结构：文献筛选原则 → 分类框架 → 机制分析框架
%                    → 模型比较框架 → 证据整合方法 → 图表公式整理原则

\section{Method}

% TODO: 由大模型基于 story_plan / paper_notes 填写。
"""


def _selected_bib_keys(job_id: str, jdir: Path, catalog: Catalog) -> list[str]:
    """确定要纳入 references.bib 的 bib_key 列表。
    优先 run_meta.selected_papers（deep-read 记录），否则 selected_papers.json。"""
    keys = []
    bib_map = {p["paper_id"]: (p.get("citation") or {}).get("bib_key", "")
               for p in catalog.list_papers()}

    meta_path = jdir / "logs" / "run_meta.json"
    pids = []
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        pids = meta.get("selected_papers") or []
    if not pids:
        sel = jdir / "planning" / "selected_papers.json"
        if sel.exists():
            for it in json.loads(sel.read_text(encoding="utf-8")):
                if it.get("need_fulltext", True):
                    pids.append(it.get("paper_id"))
    for pid in pids:
        bk = bib_map.get(pid, "")
        if bk:
            keys.append(bk)
    return keys


def build_tex(job_id: str, title: str | None = None,
              jm: JobManager | None = None, catalog: Catalog | None = None) -> dict:
    jm = jm or JobManager()
    catalog = catalog or Catalog()
    jdir = jm.job_dir(job_id)
    tex_dir = jdir / "tex"
    (tex_dir / "sections").mkdir(parents=True, exist_ok=True)

    meta = jm.load_meta(job_id) or {}
    title = title or meta.get("topic", job_id)

    (tex_dir / "main.tex").write_text(MAIN_TEX.replace("__TITLE__", title), encoding="utf-8")
    (tex_dir / "sections" / "introduction.tex").write_text(INTRO_TEX, encoding="utf-8")
    (tex_dir / "sections" / "method.tex").write_text(METHOD_TEX, encoding="utf-8")

    # references.bib
    bib_keys = _selected_bib_keys(job_id, jdir, catalog)
    bib_info = export_job_bib(job_id, bib_keys, jm=jm)

    # TeX 写作 prompt
    norm = (jdir / "input" / "normalized_task.md").read_text(encoding="utf-8") if (jdir / "input" / "normalized_task.md").exists() else ""
    story = (jdir / "planning" / "story_plan.md").read_text(encoding="utf-8") if (jdir / "planning" / "story_plan.md").exists() else ""
    prompt = f"""请基于下面的研究任务、故事线与精读证据，撰写博士论文标准的 introduction.tex 与 method.tex。

要求：
1. introduction 按 8 步结构（宏观重要性→意义→已有认识→各方解决什么→机制链条→不足→切入点→目标贡献），有矛盾递进；
2. method 按综述型结构（筛选原则→分类→机制分析→模型比较→证据整合→图表公式整理）；
3. 所有引用用 \\cite{{bib_key}}，可用 key：{bib_keys}；
4. 禁止裸作者年份、禁止编造文献/图号/公式/DOI；
5. 输出两段完整 LaTeX 正文（不含 \\section）。

# 研究任务
{norm}

# 故事线
{story}
"""
    prompt_path = jdir / "logs" / "prompts" / "04_tex_writing_prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")

    # 记录 used_bib_keys
    jm.set_step(job_id, "tex_generated", True, extra={"used_bib_keys": bib_keys})
    return {
        "main_tex": str(tex_dir / "main.tex"),
        "introduction_tex": str(tex_dir / "sections" / "introduction.tex"),
        "method_tex": str(tex_dir / "sections" / "method.tex"),
        "references_bib": bib_info["references_bib"],
        "bib_count": bib_info["count"],
        "prompt": prompt,
        "prompt_path": str(prompt_path),
    }
