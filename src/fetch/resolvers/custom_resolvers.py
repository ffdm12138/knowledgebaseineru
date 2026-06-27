"""External command plugin resolver。

允许用户配置外部命令作为 PDF 获取插件。默认禁用，须显式启用。
命令输出必须是 JSON，至少包含 ``success``、``pdf_path/pdf_url``、``source``、``message``。
"""
import json
import subprocess
from pathlib import Path

from loguru import logger

from ..models import FetchResult
from .base import PdfResolver, ResolveContext


class ExternalCommandResolver(PdfResolver):
    name = "custom"
    access_modes = ("custom",)

    def __init__(self, command_template: str = ""):
        self.command_template = command_template

    def resolve(self, context: ResolveContext) -> FetchResult:
        if not self.command_template:
            return FetchResult(
                doi=context.doi, error="no command template configured",
            )
        cmd = self.command_template.replace("{doi}", context.doi)
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                return FetchResult(
                    doi=context.doi, source="custom", error=result.stderr.strip(),
                )
            output = json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            return FetchResult(
                doi=context.doi, source="custom", error="command timed out",
            )
        except json.JSONDecodeError as e:
            return FetchResult(
                doi=context.doi, source="custom", error=f"invalid JSON output: {e}",
            )
        except Exception as e:
            return FetchResult(
                doi=context.doi, source="custom", error=str(e),
            )

        pdf_path = output.get("pdf_path", "")
        pdf_url = output.get("pdf_url", "")
        return FetchResult(
            doi=context.doi,
            success=bool(pdf_path or pdf_url),
            source="custom",
            resolver=self.name,
            access_mode="custom",
            access_status="custom",
            pdf_url=pdf_url,
            output_path=pdf_path,
            metadata={"command": cmd, "raw_output": output},
        )
