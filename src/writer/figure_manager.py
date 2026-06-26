"""图片复制与追踪：把确认使用的图从 data/papers/<pid>/images/ 复制到 job figures/

原则：
  1. 只有确认为使用的图才复制（默认从 figures 列表，不自动复制全部候选）；
  2. 候选图不自动进 TeX；
  3. 每张复制图必须有 source record（README.md 含 original_path）；
  4. TeX 中只能引用 write/<job>/figures 下的复制图。
"""
import re
import shutil
from pathlib import Path

from src.writer.job_manager import JobManager
from src.catalog import Catalog
from src.naming import validate_paper_id, validate_image_name, safe_child
from config.settings import PAPERS_DIR


def copy_figures(job_id: str, figures: list[dict] | None = None,
                 jm: JobManager | None = None,
                 catalog: Catalog | None = None) -> dict:
    """复制指定图到 write/<job>/figures/<paper_id>/ 并生成 source record README。

    figures: [{"paper_id","image","suggested_caption"?}]，为 None 时**不复制**任何图
            （避免把全部候选图当使用图）。调用方应传明确要用的图列表。
    """
    jm = jm or JobManager()
    catalog = catalog or Catalog()
    jdir = jm.job_dir(job_id)

    if figures is None:
        return {"copied": [], "used_figures": [],
                "note": "未提供 figures 列表，未复制任何图（需明确指定要用的图）"}

    bib_map = {p["paper_id"]: (p.get("citation") or {}).get("bib_key", "")
               for p in catalog.list_papers()}

    copied = []
    used = []
    for item in figures:
        pid = item.get("paper_id")
        img = item.get("image")
        if not pid or not img:
            continue
        # 防路径穿越：校验 pid + img，使用 safe_child 拼接
        try:
            validate_paper_id(pid)
            validate_image_name(img)
        except ValueError:
            continue
        src = safe_child(PAPERS_DIR, pid, "images", img)
        if not src.is_file():
            continue
        dest_dir = jdir / "figures" / pid
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / img
        shutil.copy2(src, dest)

        # source record README（按图追加，含 original_path）
        readme = dest_dir / "README.md"
        record = (
            f"\n## {img}\n"
            f"- copied_file: write/{jm.job_dir(job_id).name}/figures/{pid}/{img}\n"
            f"- original_path: data/papers/{pid}/images/{img}\n"
            f"- paper_id: {pid}\n"
            f"- bib_key: {bib_map.get(pid, '')}\n"
            f"- source_markdown: data/papers/{pid}/paper.md\n"
            f"- suggested_caption: {item.get('suggested_caption', '')}\n"
            f"- used_in_tex: false\n"
            f"- notes:\n"
        )
        if not readme.exists():
            readme.write_text("# Figure source record\n" + record, encoding="utf-8")
        else:
            with readme.open("a", encoding="utf-8") as f:
                f.write(record)

        copied.append(str(dest))
        used.append({"paper_id": pid, "image": img,
                     "tex_path": f"../figures/{pid}/{img}",
                     "original_path": f"data/papers/{pid}/images/{img}"})

    jm.set_step(job_id, "figures_copied", True, extra={"used_figures": used})
    return {"copied": copied, "used_figures": used}
