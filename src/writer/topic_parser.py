"""研究内容归一化：把用户输入归一化为 normalized_task.md

不做复杂理解，只整理成结构化模板 + 生成让大模型补全的 prompt。
"""
from pathlib import Path

from src.writer.job_manager import JobManager


def normalize_task(job_id: str, jm: JobManager | None = None) -> dict:
    """读取 research_input.md，写出 normalized_task.md（结构化模板）。

    返回 {"normalized_path", "prompt"} —— prompt 交给大模型补全细节。
    """
    jm = jm or JobManager()
    jdir = jm.job_dir(job_id)
    inp = jdir / "input" / "research_input.md"
    content = inp.read_text(encoding="utf-8") if inp.exists() else ""

    template = f"""# 归一化研究任务（normalized_task）

> 由 topic_parser 自动生成结构骨架。请用大模型补全 prompt（见返回）填实各字段。

## 原始输入

{content}

## 1. 研究主题
（待补全）

## 2. 核心科学问题
（待补全）

## 3. 研究对象
（待补全）

## 4. 空间尺度
（待补全）

## 5. 时间尺度
（待补全）

## 6. 方法类型
（如：野外观测 / 风洞实验 / 数值模拟 / 理论建模 / 综述整合）

## 7. 可能需要的文献类型
（待补全）

## 8. 预期写作目标
（如：博士论文综述章节 / 引言 / 方法）
"""
    out_path = jdir / "input" / "normalized_task.md"
    out_path.write_text(template, encoding="utf-8")

    prompt = f"""请把下面的用户研究内容归一化为结构化研究任务，按以下 8 个字段填写，输出 Markdown：

1. 研究主题
2. 核心科学问题（1-3 条）
3. 研究对象
4. 空间尺度
5. 时间尺度
6. 方法类型
7. 可能需要的文献类型（按主题/方法分类）
8. 预期写作目标

# 用户原始输入
{content}
"""
    return {"normalized_path": str(out_path), "prompt": prompt}
