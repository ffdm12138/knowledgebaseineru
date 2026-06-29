"""MinerU runtime configuration and preflight helpers."""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

from src.path_utils import is_windows_abs_path


class MinerURunner(str, Enum):
    CLI = "cli"
    API = "api"                  # 未实现的 HTTP upload adapter（纯 API 模式）
    CLI_API_PROXY = "cli_api_proxy"  # CLI + --api-url → 常驻 mineru-api


@dataclass
class MinerURuntimeConfig:
    runner: MinerURunner = MinerURunner.CLI
    api_url: str = "http://127.0.0.1:8000"
    require_gpu: bool = False
    cuda_path: str = ""
    cuda_visible_devices: str = ""
    backend: str = "hybrid-engine"
    effort: str = "medium"
    method: str = "auto"


@dataclass
class MinerURuntimeHealth:
    ok: bool
    runner: str
    message: str = ""
    nvidia_smi: bool | None = None
    cli_available: bool | None = None
    api_available: bool | None = None


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def runtime_config_from_env() -> MinerURuntimeConfig:
    runner = os.environ.get("MINERU_RUNNER", "cli").strip().lower() or "cli"
    valid = {r.value for r in MinerURunner}
    if runner not in valid:
        raise ValueError(f"invalid MINERU_RUNNER: {runner}. Valid: {sorted(valid)}")
    return MinerURuntimeConfig(
        runner=MinerURunner(runner),
        api_url=os.environ.get("MINERU_API_URL", "http://127.0.0.1:8000").strip()
        or "http://127.0.0.1:8000",
        require_gpu=_env_bool("MINERU_REQUIRE_GPU", False),
        cuda_path=os.environ.get("CUDA_PATH", "").strip(),
        cuda_visible_devices=os.environ.get("CUDA_VISIBLE_DEVICES", "").strip(),
        backend=os.environ.get("MINERU_BACKEND", "hybrid-engine").strip() or "hybrid-engine",
        effort=os.environ.get("MINERU_EFFORT", "medium").strip() or "medium",
        method=os.environ.get("MINERU_METHOD", "auto").strip() or "auto",
    )


def _join_cuda_bin(cuda_path: str) -> str:
    """Join CUDA bin directory preserving native path separator style.

    On Windows, ``os.path.join(r"C:\\CUDA\\v12.6", "bin")`` produces
    ``C:\\CUDA\\v12.6/bin`` (mixed slashes) when the test runs on a POSIX
    Python.  Conversely, ``os.path.join("/usr/local/cuda", "bin")`` on a
    Windows Python produces ``/usr/local/cuda\\bin``.

    This helper keeps Windows drive-letter paths with backslashes and
    POSIX paths with forward slashes, regardless of the host platform.
    """
    cuda_path = cuda_path.rstrip("\\/")
    if is_windows_abs_path(cuda_path):
        return cuda_path + "\\bin"
    # POSIX path or relative path — always use forward slash to avoid
    # backslash leakage on Windows Python.
    return cuda_path + "/bin"


def build_mineru_env(config: MinerURuntimeConfig | None = None, base_env: dict | None = None) -> dict:
    config = config or runtime_config_from_env()
    env = dict(base_env or os.environ)

    # 硬编码 CUDA_PATH 默认值，不依赖 shell 环境变量。
    # lmdeploy / mineru-api 启动时强制要求 CUDA_PATH 存在。
    _CUDA_FALLBACK = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6"
    cuda = config.cuda_path or _CUDA_FALLBACK
    env["CUDA_PATH"] = cuda
    cuda_bin = _join_cuda_bin(cuda)
    path_parts = env.get("PATH", "").split(os.pathsep) if env.get("PATH") else []
    if cuda_bin and cuda_bin not in path_parts:
        env["PATH"] = os.pathsep.join([cuda_bin] + path_parts)

    if config.cuda_visible_devices:
        env["CUDA_VISIBLE_DEVICES"] = config.cuda_visible_devices

    # 修复 SSL_CERT_FILE：如果环境变量指向不存在的文件，移除它，
    # 否则 httpx/ssl 会报 FileNotFoundError 导致 mineru CLI 启动失败。
    ssl_cert = env.get("SSL_CERT_FILE", "")
    if ssl_cert and not Path(ssl_cert).exists():
        env.pop("SSL_CERT_FILE", None)
    return env


def preflight_gpu(require_gpu: bool | None = None) -> MinerURuntimeHealth:
    config = runtime_config_from_env()
    required = config.require_gpu if require_gpu is None else require_gpu
    nvidia_smi = shutil.which("nvidia-smi") is not None
    if not nvidia_smi:
        return MinerURuntimeHealth(
            ok=not required,
            runner=config.runner.value,
            message="nvidia-smi not found" if required else "GPU check skipped; nvidia-smi not found",
            nvidia_smi=False,
        )
    try:
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        ok = result.returncode == 0
    except Exception:
        ok = False
    return MinerURuntimeHealth(
        ok=ok or not required,
        runner=config.runner.value,
        message="nvidia-smi ok" if ok else "nvidia-smi failed",
        nvidia_smi=ok,
    )


def preflight_mineru_cli(mineru_exe: str = "mineru") -> MinerURuntimeHealth:
    config = runtime_config_from_env()
    try:
        result = subprocess.run(
            [mineru_exe, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=build_mineru_env(config),
            timeout=10,
        )
        ok = result.returncode == 0
        msg = (result.stdout or result.stderr or "").strip()
    except Exception as exc:
        ok = False
        msg = str(exc)
    return MinerURuntimeHealth(ok=ok, runner=MinerURunner.CLI.value, message=msg, cli_available=ok)


def preflight_mineru_api(api_url: str | None = None, timeout: float = 5.0) -> MinerURuntimeHealth:
    config = runtime_config_from_env()
    url = (api_url or config.api_url).rstrip("/")
    try:
        import requests

        response = requests.get(f"{url}/health", timeout=timeout)
        if response.status_code >= 400:
            response = requests.get(url, timeout=timeout)
        ok = response.status_code < 400
        msg = f"HTTP {response.status_code}"
    except Exception as exc:
        ok = False
        msg = str(exc)
    required = config.require_gpu or config.runner == MinerURunner.API
    return MinerURuntimeHealth(
        ok=ok or not required,
        runner=MinerURunner.API.value,
        message=msg,
        api_available=ok,
    )


def list_gpu_processes() -> dict:
    """列出 GPU 上的 compute 进程（pid, process_name, used_memory）。

    Returns:
        dict: {
            "available": bool,
            "processes": [{"pid": int, "process_name": str, "used_memory_mb": int}, ...],
            "error": str (仅失败时),
        }
    """
    import datetime as _dt
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return {"available": False, "processes": [], "error": "nvidia-smi not found"}
    try:
        result = subprocess.run(
            [nvidia_smi, "--query-compute-apps=pid,process_name,used_memory",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15,
        )
        if result.returncode != 0:
            return {"available": False, "processes": [],
                    "error": f"nvidia-smi exit {result.returncode}"}
        procs = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue
            try:
                procs.append({
                    "pid": int(parts[0].strip()),
                    "process_name": parts[1].strip(),
                    "used_memory_mb": int(parts[2].strip()),
                })
            except (ValueError, IndexError):
                continue
        return {"available": True, "processes": procs}
    except Exception as exc:
        return {"available": False, "processes": [], "error": str(exc)}


def describe_runtime(config: MinerURuntimeConfig | None = None) -> dict:
    config = config or runtime_config_from_env()
    data = asdict(config)
    data["runner"] = config.runner.value
    return data


def snapshot_nvidia_smi() -> dict:
    """采集 nvidia-smi GPU 快照（单次采样）。

    无 nvidia-smi 时不抛异常，返回 ``{"available": False}``。

    Returns:
        dict: {
            "available": bool,
            "timestamp": str,
            "gpus": [{"name": str, "memory_used_mb": int, "memory_total_mb": int,
                       "gpu_util_pct": int, "memory_util_pct": int}, ...],
            "error": str (仅失败时),
        }
    """
    import datetime as _dt
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return {"available": False, "timestamp": _dt.datetime.now().isoformat(),
                "error": "nvidia-smi not found"}
    try:
        result = subprocess.run(
            [nvidia_smi,
             "--query-gpu=name,memory.used,memory.total,utilization.gpu,utilization.memory",
             "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if result.returncode != 0:
            return {"available": False, "timestamp": _dt.datetime.now().isoformat(),
                    "error": f"nvidia-smi exit {result.returncode}: {result.stderr.strip()[-200:]}"}
        gpus = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 5:
                continue
            try:
                gpus.append({
                    "name": parts[0],
                    "memory_used_mb": int(float(parts[1])),
                    "memory_total_mb": int(float(parts[2])),
                    "gpu_util_pct": int(float(parts[3])),
                    "memory_util_pct": int(float(parts[4])),
                })
            except (ValueError, IndexError):
                continue
        return {"available": True, "timestamp": _dt.datetime.now().isoformat(), "gpus": gpus}
    except Exception as exc:
        return {"available": False, "timestamp": _dt.datetime.now().isoformat(),
                "error": str(exc)}
