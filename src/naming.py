"""paper_id 命名工具

新上传文件的 paper_id 由文件名 stem 清洗得到（文件系统安全，保留中文）。
规范命名（年份_作者_标题）由 AI 在补全 catalog 条目时建议，用户确认后可手动改名。
"""
import re
from pathlib import Path

# Windows 文件系统非法字符
_ILLEGAL = re.compile(r'[\\/:*?"<>|]')


def derive_paper_id(filename: str) -> str:
    """从上传文件名推导 paper_id：取 stem，非法字符替换为 _，空白折叠为 _"""
    stem = Path(filename).stem
    stem = _ILLEGAL.sub("_", stem)
    stem = re.sub(r"\s+", "_", stem.strip())
    return stem or "untitled"
