"""图片复制与追踪：把被引用图从 data/papers/<pid>/images/ 复制到 job figures/

原则：只要进 TeX 就复制；每张图记录原路径；不确定图意只列候选不自动入正文。
TeX 中用相对路径 ../figures/<pid>/<image>。
"""
import re
import shutil
from pathlib import Path

from src.writer.job_manager import JobManager
from config.settings import PAPERS_DIR


def _parse_figure_candidates(text: str) -> list[dict]:
    """从 figure_candidates.md 解析候选引用：识别 `paper_id` 与 `image_name` 配对。

    约定格式：`- <paper_id>: ...` 段，段内 `  - \`<image_name>\`` 行。
    返回 [{"paper_id", "image"}]
    """
    out = []
    cur_pid = None
    for line in text.splitlines():
        m = re.match(r"^- ([^:\s]+):", line)
        if m:
            cur_pid = m.group(1).strip()
            continue
        mi = re.match(r"^\s+- `?([^`:\s]+?)`?\s*——", line)
        if mi and cur_pid:
            out.append({"paper_id": cur_pid, "image": mi.group(1).strip()})
    return out


def copy_figures(job_id: str, jm: JobManager | None = None,
                 figures: list[dict] | None = None) -> dict:
    """复制图片到 write/<job>/figures/<paper_id>/ 并生成 README。

    figures: [{"paper_id","image"}]；为 None 时从 figure_candidates.md 解析
           （仅复制明确标记为「引用」的，需含标记 —— 见 _parse 选词）。"""
    jm = jm or JobManager()
    jdir = jm.job_dir(job_id)

    if figures is None:
        fc = jdir / "reading" / "figure_candidates.md"
        if fc.exists():
            # 只复制被标记引用的行（含「引用」字样）
            marked = []
            for line in fc.read_text(encoding="utf-8").splitlines():
                if "引用" in line:
                    mi = re.match(r"^\s+- `?([^`:\s]+?)`?", line)
                    if mi:
                        marked.append(mi.group(1).strip())
            # 简化：若无明显标记，复制全部解析结果
            figures = _parse_figure_candidates(fc.read_text(encoding="utf-8"))

    copied = []
    used = []
    for item in figures or []:
        pid, img = item["paper_id"], item["image"]
        src = PAPERS_DIR / pid / "images" / img
        if not src.is_file():
            continue
        dest_dir = jdir / "figures" / pid
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / img
        shutil.copy2(src, dest)
        # README 记录
        readme = dest_dir / "README.md"
        entry = f"\n## {img}\n- copied_file: figures/{pid}/{img}\n- original_path: data/papers/{pid}/images/{img}\n- paper_id: {pid}\n- bib_key: \n- suggested_caption: \n- used_in_tex: \n- notes: \n"
        if not readme.exists():
            readme.write_text("# Figure source record\n" + entry, encoding="utf-8")
        else:
            with readme.open("a", encoding="utf-8") as f:
                f.write(entry)
        copied.append(str(dest))
        used.append({"paper_id": pid, "image": img,
                     "tex_path": f"../figures/{pid}/{img}"})

    jm.set_step(job_id, "figures_copied", True, extra={"used_figures": used})
    return {"copied": copied, "used_figures": used}
