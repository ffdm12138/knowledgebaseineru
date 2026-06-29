import os

import pytest

from src.mineru_runtime import (
    MinerURunner,
    MinerURuntimeConfig,
    _join_cuda_bin,
    build_mineru_env,
    describe_runtime,
    preflight_gpu,
    runtime_config_from_env,
)


def test_join_cuda_bin_windows():
    assert _join_cuda_bin(r"C:\CUDA\v12.6") == r"C:\CUDA\v12.6\bin"
    assert _join_cuda_bin(r"C:\CUDA\v12.6\\") == r"C:\CUDA\v12.6\bin"


def test_join_cuda_bin_posix():
    assert _join_cuda_bin("/usr/local/cuda") == "/usr/local/cuda/bin"
    assert _join_cuda_bin("/usr/local/cuda/") == "/usr/local/cuda/bin"


def test_build_mineru_env_prepends_cuda_bin():
    config = MinerURuntimeConfig(cuda_path=r"C:\CUDA\v12.6")
    env = build_mineru_env(config, base_env={"PATH": r"C:\Windows"})

    assert env["CUDA_PATH"] == r"C:\CUDA\v12.6"
    assert env["PATH"].startswith(r"C:\CUDA\v12.6\bin")


def test_build_mineru_env_posix_cuda_bin():
    config = MinerURuntimeConfig(cuda_path="/usr/local/cuda")
    env = build_mineru_env(config, base_env={"PATH": "/usr/bin"})

    assert env["CUDA_PATH"] == "/usr/local/cuda"
    assert env["PATH"].startswith("/usr/local/cuda/bin")


def test_build_mineru_env_injects_cuda_visible_devices():
    config = MinerURuntimeConfig(cuda_visible_devices="0")
    env = build_mineru_env(config, base_env={"PATH": "/usr/bin"})

    assert env["CUDA_VISIBLE_DEVICES"] == "0"


def test_runtime_config_from_env(monkeypatch):
    monkeypatch.setenv("MINERU_RUNNER", "api")
    monkeypatch.setenv("MINERU_API_URL", "http://127.0.0.1:9000")
    monkeypatch.setenv("MINERU_REQUIRE_GPU", "true")

    config = runtime_config_from_env()

    assert config.runner == MinerURunner.API
    assert config.api_url == "http://127.0.0.1:9000"
    assert config.require_gpu is True


def test_describe_runtime_serializes_runner():
    data = describe_runtime(MinerURuntimeConfig(runner=MinerURunner.CLI))

    assert data["runner"] == "cli"


def test_require_gpu_true_fails_when_nvidia_smi_missing(monkeypatch):
    monkeypatch.setenv("MINERU_REQUIRE_GPU", "true")
    monkeypatch.setattr("src.mineru_runtime.shutil.which", lambda name: None)

    health = preflight_gpu()

    assert health.ok is False
    assert health.nvidia_smi is False
