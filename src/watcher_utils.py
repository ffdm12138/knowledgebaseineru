"""watcher 辅助：文件稳定性检测、临时后缀识别"""
import time
from pathlib import Path


def is_file_stable(path: Path, wait_seconds: float = 1.0) -> bool:
    """判断文件是否已停止增长（复制完成）。size 两次相同且 > 0。"""
    p = Path(path)
    if not p.exists() or not p.is_file():
        return False
    try:
        size1 = p.stat().st_size
    except OSError:
        return False
    if size1 == 0:
        return False
    time.sleep(wait_seconds)
    if not p.exists():
        return False
    try:
        size2 = p.stat().st_size
    except OSError:
        return False
    return size1 == size2 and size2 > 0


def is_uploading_temp(path: Path) -> bool:
    """是否为上传临时文件（如 xxx.pdf.uploading / .part / .tmp）"""
    name = Path(path).name.lower()
    return name.endswith(".uploading") or name.endswith(".part") or name.endswith(".tmp")
