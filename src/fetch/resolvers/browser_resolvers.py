"""Browser-assisted resolver：不下载，只返回 landing page 和提示。"""
from ..models import FetchResult
from .base import PdfResolver, ResolveContext


class BrowserAssistedResolver(PdfResolver):
    name = "browser_assisted"
    access_modes = ("browser_assisted",)

    def resolve(self, context: ResolveContext) -> FetchResult:
        return FetchResult(
            doi=context.doi,
            success=True,
            source="browser_assisted",
            resolver=self.name,
            access_mode="browser_assisted",
            access_status="browser_assisted",
            requires_user_action=True,
            landing_url=f"https://doi.org/{context.doi}",
            action_hint=(
                f"用浏览器打开 https://doi.org/{context.doi}，"
                f"手动下载 PDF，放入 pending 目录后运行 "
                f"python scripts/register_manual_pdf.py <pdf> --doi {context.doi}"
            ),
        )
