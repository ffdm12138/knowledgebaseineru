"""写作任务管理：创建/列出/加载 write/<job>/ 目录结构

任务目录命名：write/001_<topic_slug>/、write/002_<topic_slug>/ ...
"""
import json
import re
from pathlib import Path
from datetime import datetime
from loguru import logger

from config.settings import PROJECT_ROOT

WRITE_DIR = PROJECT_ROOT / "write"

# 任务标准子目录
JOB_SUBDIRS = ["input", "planning", "reading/paper_notes", "tex/sections",
               "figures", "logs/prompts"]


def _slugify(topic: str) -> str:
    """从研究内容生成 slug：取前 6-16 个中文字符或 3-8 个英文词，清洗非法字符"""
    topic = topic.strip()
    if not topic:
        return "untitled"
    # 优先取中文连续段
    zh = re.findall(r"[一-鿿]+", topic)
    if zh:
        s = "".join(zh)[:16]
    else:
        words = re.findall(r"[A-Za-z0-9]+", topic)[:8]
        s = "_".join(words) if words else "untitled"
    # 文件系统安全
    s = re.sub(r'[\\/:*?"<>|]', "", s)
    return s.strip() or "untitled"


def _next_job_num() -> int:
    """扫描 write/ 找最大编号 +1"""
    if not WRITE_DIR.exists():
        return 1
    max_n = 0
    for d in WRITE_DIR.iterdir():
        m = re.match(r"^(\d+)_", d.name)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def _empty_run_meta(job_id: str, topic: str, input_type: str,
                    target: str, language: str) -> dict:
    return {
        "job_id": job_id,
        "job_dir": str(WRITE_DIR / job_id),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "input_type": input_type,
        "target": target,
        "language": language,
        "topic": topic,
        "status": "created",
        "steps": {
            "catalog_match_prompt_generated": False,
            "catalog_selection_confirmed": False,
            "deep_read_prompt_generated": False,
            "deep_read_notes_filled": False,
            "story_prompt_generated": False,
            "story_plan_filled": False,
            "tex_template_generated": False,
            "tex_content_filled": False,
            "figures_copied": False,
            "bib_exported": False,
            "validated": False,
        },
        "selected_papers": [],
        "used_bib_keys": [],
        "used_figures": [],
        "notes": [],
    }


class JobManager:
    """写作任务目录管理"""

    def __init__(self, write_dir: Path = WRITE_DIR):
        self.write_dir = Path(write_dir)

    def job_dir(self, job_id: str) -> Path:
        return self.write_dir / job_id

    def list_jobs(self) -> list[dict]:
        """列出所有任务的 run_meta 摘要"""
        out = []
        if not self.write_dir.exists():
            return out
        for d in sorted(self.write_dir.iterdir()):
            if d.is_dir() and re.match(r"^\d+_", d.name):
                meta_path = d / "logs" / "run_meta.json"
                if meta_path.exists():
                    out.append(json.loads(meta_path.read_text(encoding="utf-8")))
                else:
                    out.append({"job_id": d.name, "status": "created"})
        return out

    def load_meta(self, job_id: str) -> dict | None:
        p = self.job_dir(job_id) / "logs" / "run_meta.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def save_meta(self, job_id: str, meta: dict) -> None:
        meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
        p = self.job_dir(job_id) / "logs" / "run_meta.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def touch(self, job_id: str) -> None:
        """仅刷新 updated_at"""
        meta = self.load_meta(job_id)
        if meta is not None:
            self.save_meta(job_id, meta)

    def set_step(self, job_id: str, step: str, value: bool = True,
                 extra: dict | None = None) -> dict:
        meta = self.load_meta(job_id)
        if meta is None:
            raise FileNotFoundError(f"任务不存在: {job_id}")
        if step not in meta["steps"]:
            raise KeyError(f"未知 step: {step}")
        meta["steps"][step] = value
        if extra:
            meta.update(extra)
        self.save_meta(job_id, meta)
        return meta

    def set_status(self, job_id: str, status: str) -> dict:
        meta = self.load_meta(job_id)
        if meta is None:
            raise FileNotFoundError(f"任务不存在: {job_id}")
        meta["status"] = status
        self.save_meta(job_id, meta)
        return meta

    def set_selected_papers(self, job_id: str, paper_ids: list[str]) -> dict:
        meta = self.load_meta(job_id)
        if meta is None:
            raise FileNotFoundError(f"任务不存在: {job_id}")
        meta["selected_papers"] = list(paper_ids)
        self.save_meta(job_id, meta)
        return meta

    def append_note(self, job_id: str, note: str) -> dict:
        meta = self.load_meta(job_id)
        if meta is None:
            raise FileNotFoundError(f"任务不存在: {job_id}")
        meta.setdefault("notes", []).append(
            f"[{datetime.now().isoformat(timespec='seconds')}] {note}")
        self.save_meta(job_id, meta)
        return meta

    def step_is(self, job_id: str, step: str) -> bool:
        """安全查询某 step 是否为 True"""
        meta = self.load_meta(job_id)
        if meta is None:
            return False
        return bool(meta.get("steps", {}).get(step, False))

    def require_step(self, job_id: str, step: str, action: str) -> None:
        """前置校验：若 step 未完成则抛 RuntimeError，提示先做某动作"""
        if not self.step_is(job_id, step):
            raise RuntimeError(
                f"Cannot {action}: run_meta.steps.{step} is not True. "
                f"请先完成前置步骤。")

    def create(self, topic: str | None = None, input_file: str | None = None,
               target: str = "phd_thesis", language: str = "zh") -> dict:
        """创建一个写作任务目录。topic 与 input_file 至少给一个。"""
        if not topic and not input_file:
            raise ValueError("必须提供 topic 或 input_file")

        # 读取输入文件内容
        input_text = ""
        if input_file:
            ip = Path(input_file)
            if not ip.exists():
                raise FileNotFoundError(f"输入文件不存在: {input_file}")
            input_text = ip.read_text(encoding="utf-8")
            if not topic:
                topic = input_text[:60]

        slug = _slugify(topic or "untitled")
        num = _next_job_num()
        job_id = f"{num:03d}_{slug}"
        jdir = self.job_dir(job_id)
        for sub in JOB_SUBDIRS:
            (jdir / sub).mkdir(parents=True, exist_ok=True)

        # research_input.md
        (jdir / "input" / "research_input.md").write_text(
            input_text if input_text else f"# 研究内容\n\n{topic}\n", encoding="utf-8")

        # run_meta.json
        input_type = "input_file" if input_file else "topic_text"
        meta = _empty_run_meta(job_id, topic or slug, input_type, target, language)
        self.save_meta(job_id, meta)

        logger.info(f"创建写作任务: {job_id} -> {jdir}")
        return {"job_id": job_id, "job_dir": str(jdir), "meta": meta}

    def job_files(self, job_id: str) -> list[str]:
        """列出任务目录下所有文件（相对 job_dir 的路径）"""
        jdir = self.job_dir(job_id)
        if not jdir.exists():
            return []
        return [str(p.relative_to(jdir)).replace("\\", "/")
                for p in jdir.rglob("*") if p.is_file()]
