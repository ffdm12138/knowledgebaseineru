"""MinerU 3.4 文档转换引擎

调用 mineru CLI 将PDF/DOCX/PPTX/XLSX/图片 转换为 Markdown
"""
import os
import shutil
import subprocess
from pathlib import Path
from loguru import logger


def _find_mineru_exe() -> str:
    """跨平台查找 mineru 可执行文件"""
    # 1. 优先 PATH 查找
    for name in ("mineru", "mineru.exe"):
        found = shutil.which(name)
        if found:
            return found
    # 2. fallback: Python 环境目录
    _py_dir = Path(os.sys.executable).parent
    for cand in (_py_dir / "mineru.exe",
                 _py_dir / "Scripts" / "mineru.exe",
                 _py_dir.parent / "Scripts" / "mineru.exe"):
        if cand.exists():
            return str(cand)
    return "mineru"  # 最后尝试直接调命令名，让 subprocess 按 PATH 解析


MINERU_EXE = _find_mineru_exe()

def mineru_available() -> bool:
    """检查 mineru CLI 是否可用"""
    try:
        r = subprocess.run([MINERU_EXE, "--version"], capture_output=True,
                           encoding="utf-8", errors="replace", timeout=10)
        return r.returncode == 0
    except Exception:
        return False


class MinerUConverter:
    """MinerU 3.4 文档转换器"""

    def __init__(self, proxy: str = None, timeout: int | None = None):
        """
        Args:
            proxy: 代理地址，如 "http://127.0.0.1:7890"，None则不走代理
            timeout: CLI 转换超时（秒），默认从 config 读取
        """
        self.proxy = proxy
        from config.settings import MINERU_TIMEOUT
        self.timeout = timeout or MINERU_TIMEOUT

    def _get_env(self) -> dict:
        """构建环境变量"""
        env = {**os.environ}
        if self.proxy:
            env["HTTP_PROXY"] = self.proxy
            env["HTTPS_PROXY"] = self.proxy
        return env

    def convert(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        backend: str = "hybrid-engine",
        method: str = "auto",
        lang: str = "ch",
        effort: str = "medium",
        api_url: str | None = None,
    ) -> dict:
        """统一转换入口。

        Args:
            input_path: 输入文件路径 (PDF/DOCX/PPTX/XLSX/图片)
            output_dir: 输出目录
            backend: 解析后端 "pipeline" | "vlm-engine" | "hybrid-engine"
            method: 解析方法 "auto" | "ocr" | "txt"
            lang: OCR语言 "ch" | "en" 等
            effort: hybrid-engine解析强度 "medium" | "high"
            api_url: mineru-api 地址。None 走 CLI；非 None 走 API（暂未实现）

        Returns:
            dict: {
                "success": bool,
                "markdown": str,
                "md_path": str,
                "output_dir": str,
                "source_file": str,
                "backend": "cli" | "api",
                "error": str (失败时),
            }
        """
        if api_url:
            return self.convert_via_api(input_path, output_dir, backend, method,
                                        lang, effort, api_url)
        return self.convert_via_cli(input_path, output_dir, backend, method,
                                    lang, effort)

    def convert_via_cli(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        backend: str = "hybrid-engine",
        method: str = "auto",
        lang: str = "ch",
        effort: str = "medium",
    ) -> dict:
        """通过 mineru CLI 子进程转换"""
        input_path = Path(input_path)
        output_dir = Path(output_dir)

        if not input_path.exists():
            return {"success": False, "error": f"文件不存在: {input_path}", "backend": "cli"}

        logger.info(f"[converter] backend=cli | {input_path.name} (backend={backend}, method={method})")

        cmd = [
            MINERU_EXE,
            "-p", str(input_path),
            "-o", str(output_dir),
            "-b", backend,
            "-m", method,
            "-l", lang,
        ]
        if backend == "hybrid-engine":
            cmd.extend(["--effort", effort])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self._get_env(),
                timeout=self.timeout,
            )

            if result.returncode != 0:
                error_msg = result.stderr[-500:] if result.stderr else "未知错误"
                logger.error(f"转换失败: {error_msg}")
                return {"success": False, "error": error_msg, "backend": "cli"}

            # 查找生成的Markdown文件
            # MinerU 3.4 输出结构: output_dir/<stem>/<method>/<stem>.md
            stem = input_path.stem
            md_path = output_dir / stem / method / f"{stem}.md"
            if not md_path.exists():
                # 尝试 auto 目录
                md_path = output_dir / stem / "auto" / f"{stem}.md"

            if md_path.exists():
                md_content = md_path.read_text(encoding="utf-8")
            else:
                md_content = ""
                logger.warning(f"未找到Markdown输出: {md_path}")

            logger.info(f"[converter] backend=cli 转换完成: {input_path.name}")
            return {
                "success": True,
                "markdown": md_content,
                "md_path": str(md_path) if md_path.exists() else "",
                "output_dir": str(output_dir / stem),
                "source_file": input_path.name,
                "backend": "cli",
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"转换超时({self.timeout}s)", "backend": "cli"}
        except Exception as e:
            return {"success": False, "error": str(e), "backend": "cli"}

    def convert_via_api(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        backend: str = "hybrid-engine",
        method: str = "auto",
        lang: str = "ch",
        effort: str = "medium",
        api_url: str = "",
    ) -> dict:
        """通过 mineru-api 服务转换。

        当前 watcher/server 路径未实现 HTTP 上传调用，明确报错，避免参数存在但无效。
        batch_convert.py 走 CLI 子进程 + --api-url，由其自行处理。
        """
        raise NotImplementedError(
            "converter.convert_via_api 尚未实现 HTTP 上传调用。"
            "watcher/server 请走 CLI（api_url=None）；如需经 mineru-api，用 batch_convert.py "
            "（CLI 子进程带 --api-url）。不允许 api_url 参数存在但无效。")

    def convert_batch(
        self,
        input_paths: list[str | Path],
        output_dir: str | Path,
        backend: str = "hybrid-engine",
        method: str = "auto",
        lang: str = "ch",
        effort: str = "medium",
    ) -> list[dict]:
        """批量转换"""
        results = []
        for path in input_paths:
            result = self.convert(path, output_dir, backend, method, lang, effort)
            results.append(result)
        return results
