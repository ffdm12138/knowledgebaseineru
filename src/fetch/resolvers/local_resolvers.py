"""Local manual resolver for user-provided PDF paths."""
from pathlib import Path

from ..models import FetchResult
from .base import PdfResolver, ResolveContext


class LocalManualResolver(PdfResolver):
    name = "local_manual"
    access_modes = ("local_manual",)

    def resolve(self, context: ResolveContext) -> FetchResult:
        pdf_path = (context.metadata or {}).get("pdf_path", "")
        return FetchResult(
            doi=context.doi,
            success=True if pdf_path else False,
            source="local_manual",
            resolver=self.name,
            access_mode="local_manual",
            access_status="manual",
            requires_user_action=False,
            output_path=str(pdf_path) if pdf_path else "",
            metadata={
                "doi": context.doi,
                "title": context.title,
                "year": context.year,
                "access_mode": "local_manual",
                "resolver": self.name,
                "pdf_path": str(pdf_path) if pdf_path else "",
            },
        )
