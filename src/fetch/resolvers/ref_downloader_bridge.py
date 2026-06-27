"""ref-downloader 桥接器。

通过子进程调用 ref-downloader CLI，利用 Edge/Chrome 机构登录态
访问 20+ 出版商（ACS/Nature/Elsevier/Wiley/IEEE/RSC/IOP 等）。

用户须自行安装：pip install ref-downloader
子进程调用方式，不直接依赖 ref-downloader Python 包。

仓库：https://github.com/ltczding-gif/ref-downloader (MIT License)
"""
import json
import subprocess
from pathlib import Path

from loguru import logger

from src.fetch.models import FetchResult
from src.fetch.resolvers.base import PdfResolver, ResolveContext


class RefDownloaderResolver(PdfResolver):
    name = "ref_downloader"
    access_modes = ("institutional", "custom")

    def resolve(self, context: ResolveContext) -> FetchResult:
        """通过子进程调用 ref-downloader CLI 下载参考文献 PDF。

        返回的 FetchResult：
          - success=True + pdf_url → 成功获取 PDF
          - requires_user_action=True → 提示用户安装/配置
        """
        # 检查 CLI 是否可用
        try:
            result = subprocess.run(
                ["ref-downloader", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return self._not_installed(context.doi)
        except FileNotFoundError:
            return self._not_installed(context.doi)
        except subprocess.TimeoutExpired:
            return self._not_installed(context.doi)
        except Exception as exc:
            return self._not_installed(context.doi, extra=str(exc))

        # CLI 可用，调用下载
        try:
            proc = subprocess.run(
                ["ref-downloader", context.doi, "--output", "-", "--browser", "edge"],
                capture_output=True, text=True, timeout=300,
            )
            if proc.returncode != 0:
                return FetchResult(
                    doi=context.doi, source="ref_downloader", error=proc.stderr.strip(),
                    resolver=self.name, access_mode="institutional",
                    access_status="institutional_access",
                    requires_user_action=True,
                    action_hint=f"ref-downloader failed: {proc.stderr[:200]}",
                )

            # 解析 JSON 报告
            report = json.loads(proc.stdout)
            pdf_path = report.get("pdf_path") or ""
            pdf_url = report.get("pdf_url") or ""
            return FetchResult(
                doi=context.doi,
                success=True,
                source="ref_downloader",
                resolver=self.name,
                access_mode="institutional",
                access_status="institutional_access",
                pdf_url=pdf_url,
                output_path=pdf_path,
                metadata={"ref_downloader_report": report},
            )

        except json.JSONDecodeError as e:
            return FetchResult(
                doi=context.doi, source="ref_downloader", error=f"invalid JSON: {e}",
                resolver=self.name,
            )
        except subprocess.TimeoutExpired:
            return FetchResult(
                doi=context.doi, source="ref_downloader", error="timeout (300s)",
                resolver=self.name,
            )
        except Exception as exc:
            return FetchResult(
                doi=context.doi, source="ref_downloader", error=str(exc),
                resolver=self.name,
            )

    def _not_installed(self, doi: str, extra: str = "") -> FetchResult:
        hint = (
            "ref-downloader 未安装。请运行：pip install ref-downloader"
            "\n确保 Edge 浏览器已登录机构账号后重试。"
        )
        if extra:
            hint += f"\n详情：{extra}"
        return FetchResult(
            doi=doi,
            success=True,
            source="ref_downloader",
            resolver=self.name,
            access_mode="institutional",
            access_status="institutional_access",
            requires_user_action=True,
            action_hint=hint,
        )
