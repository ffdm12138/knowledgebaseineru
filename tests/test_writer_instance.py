"""测试 JobManager 多实例隔离（WRITE_DIR 清理）"""
import tempfile
from pathlib import Path
from src.writer.job_manager import JobManager


def test_job_manager_uses_instance_write_dir():
    """JobManager(write_dir=tmp) 的 meta 中 job_dir 应指向 tmp"""
    with tempfile.TemporaryDirectory() as td:
        jm = JobManager(write_dir=Path(td))
        info = jm.create(topic="测试任务")
        assert "job_id" in info
        meta = info["meta"]
        # job_dir 应在 tmp 内
        assert td in meta["job_dir"], \
            f"Expected job_dir under {td}, got {meta['job_dir']}"
        # jm.job_dir 也指向 tmp
        jdir = jm.job_dir(info["job_id"])
        assert str(jdir).startswith(td)


def test_two_instances_independent():
    """两个 JobManager 实例的编号不共享"""
    with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
        jm1 = JobManager(write_dir=Path(td1))
        jm2 = JobManager(write_dir=Path(td2))
        info1 = jm1.create(topic="任务A")
        info2 = jm2.create(topic="任务B")
        # 两个实例独立编号，job_dir 各自在对应 tmp 下
        assert td1 in info1["meta"]["job_dir"]
        assert td2 in info2["meta"]["job_dir"]
        assert td1 not in info2["meta"]["job_dir"]


def test_create_input_file_rejected_if_abs_path():
    """JobManager.create 拒绝绝对路径 input_file"""
    with tempfile.TemporaryDirectory() as td:
        jm = JobManager(write_dir=Path(td))
        with __import__("pytest").raises(ValueError, match="绝对路径|路径穿越"):
            jm.create(topic="test", input_file="/etc/passwd")


def test_create_input_file_rejected_if_dotdot():
    """JobManager.create 拒绝含 .. 的 input_file"""
    with tempfile.TemporaryDirectory() as td:
        jm = JobManager(write_dir=Path(td))
        with __import__("pytest").raises(ValueError, match="绝对路径|路径穿越"):
            jm.create(topic="test", input_file="../../secret")
