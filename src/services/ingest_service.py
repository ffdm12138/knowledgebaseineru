"""IngestService — raw → MinerU 转换 → 清理 → manifest 注册的统一流程。

将 upload_service.py / batch_convert.py / watcher.py 的重复逻辑收敛至此。
"""
from pathlib import Path

from config.settings import MANIFEST_PATH, MINERU_TMP_DIR
from src.cleaner import MinerUOutputCleaner
from src.converter import MinerUConverter
from src.file_fingerprint import compute_sha256, file_meta
from src.manifest import PaperManifest
from src.services.conversion_ingest_pipeline import ConversionIngestPipeline
from src.services.paper_registry import PaperRegistryService


class IngestService:
    """文件摄取服务：转换 + 清理 + manifest 写入。"""

    def __init__(self, manifest: PaperManifest | None = None,
                 converter: MinerUConverter | None = None,
                 cleaner: MinerUOutputCleaner | None = None,
                 registry: PaperRegistryService | None = None,
                 tmp_dir: Path = MINERU_TMP_DIR):
        self.manifest = manifest or PaperManifest(MANIFEST_PATH)
        self.converter = converter or MinerUConverter()
        self.cleaner = cleaner or MinerUOutputCleaner()
        self.registry = registry or PaperRegistryService(manifest_path=self.manifest.path)
        self.tmp_dir = tmp_dir

    def convert_file(
        self,
        pdf_path: str | Path,
        paper_id: str,
        backend: str = "hybrid-engine",
        method: str = "auto",
        lang: str = "ch",
        effort: str = "medium",
        api_url: str | None = None,
        overwrite: bool = False,
        title: str = "",
        doi: str = "",
        year: int | None = None,
        primary_domain: str = "",
        domains: list[str] | None = None,
        source_kind: str = "ingest",
    ) -> dict:
        """转换单个 PDF 并注册到 manifest。

        Returns:
            dict: {"success": bool, "paper_id": str, "markdown": str,
                   "images_dir": str, "error": str, ...}
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            return {"success": False, "paper_id": paper_id, "error": f"文件不存在: {pdf_path}"}
        sha256 = compute_sha256(pdf_path)
        meta = file_meta(pdf_path)

        pipeline = ConversionIngestPipeline(
            manifest=self.manifest,
            converter=self.converter,
            cleaner=self.cleaner,
            registry=self.registry,
            tmp_dir=self.tmp_dir,
        )
        result = pipeline.convert_and_register(
            pdf_path=pdf_path,
            paper_id=paper_id,
            backend=backend,
            method=method,
            lang=lang,
            effort=effort,
            api_url=api_url,
            overwrite=overwrite,
            replace=True,
            title=title,
            doi=doi,
            year=year,
            primary_domain=primary_domain,
            domains=domains,
            source_kind=source_kind,
            raw_filename=pdf_path.name,
            raw_stem=pdf_path.stem,
            sha256=sha256,
            file_size=meta["file_size"],
            mtime=meta["mtime"],
        )
        if not result.get("success"):
            return {"success": False, "paper_id": paper_id, "error": result.get("error")}
        return {
            "success": True,
            "paper_id": paper_id,
            "markdown": result["markdown_path"],
            "images_dir": result["images_dir"],
            "char_count": result.get("char_count", 0),
            "images_count": result.get("images_count", 0),
        }
