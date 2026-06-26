"""Phase 6 验收：CLI 普通模式禁止 backend/effort 覆盖。

产品固定 hybrid-engine + medium；仅 MINERU_ALLOW_BACKEND_OVERRIDE=true 时
才允许 pipeline/vlm-engine/high。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def _run_cli(module: str, args: list[str], env_override: dict | None = None):
    """运行 CLI 模块（不真正转换，只触发 argparse + override 校验后退出）。"""
    import os
    env = {**os.environ, "MINERU_ALLOW_BACKEND_OVERRIDE": "false"}
    if env_override:
        env.update(env_override)
    # 加 --help 之外的参数；用非法目录让其在校验后早退（校验在 parse 后立即发生）
    proc = subprocess.run(
        [PY, "-m", module] + args,
        capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=30)
    return proc


def test_batch_convert_backend_pipeline_rejected():
    """override=false 时 batch_convert --backend pipeline 报错"""
    proc = _run_cli("batch_convert", ["data/raw", "--backend", "pipeline"])
    assert proc.returncode != 0
    assert "不被允许" in proc.stderr or "backend" in proc.stderr.lower()


def test_batch_convert_effort_high_rejected():
    """override=false 时 --effort high 报错"""
    proc = _run_cli("batch_convert", ["data/raw", "--effort", "high"])
    assert proc.returncode != 0
    assert "不被允许" in proc.stderr or "effort" in proc.stderr.lower()


def test_watcher_effort_high_rejected():
    """override=false 时 watcher --effort high 报错"""
    proc = _run_cli("watcher", ["--effort", "high", "--once"])
    assert proc.returncode != 0


def test_default_backend_effort_accepted():
    """默认 hybrid-engine + medium 不报 override 错（用空目录避免真实转换）"""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        proc = _run_cli("batch_convert", [td])
    # 不会因 override 报错（空目录会早退，但 stderr 不含「不被允许」）
    assert "不被允许" not in proc.stderr


def test_override_true_allows_pipeline():
    """override=true 时允许 pipeline（不报 override 错，用空目录避免真实转换）"""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        proc = _run_cli("batch_convert", [td, "--backend", "pipeline"],
                        env_override={"MINERU_ALLOW_BACKEND_OVERRIDE": "true"})
    assert "不被允许" not in proc.stderr


def test_override_true_allows_high():
    """override=true 时允许 high effort（watcher --once 空目录早退）"""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        # watcher 扫描目录用 MINERU_DATA_DIR 指向空目录
        proc = _run_cli("watcher", ["--effort", "high", "--once"],
                        env_override={"MINERU_ALLOW_BACKEND_OVERRIDE": "true",
                                      "MINERU_DATA_DIR": td})
    assert "不被允许" not in proc.stderr
