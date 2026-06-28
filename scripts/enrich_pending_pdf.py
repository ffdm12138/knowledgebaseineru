"""Enrich a pending PDF sidecar with metadata.

Extracts DOI from filename/sidecar/PDF text, queries Crossref for canonical metadata,
and writes proposed_paper_id + normalized metadata back to the sidecar JSON.

用法:
  python scripts/enrich_pending_pdf.py data/raw/<domain>/pending/foo.pdf
  python scripts/enrich_pending_pdf.py data/raw/<domain>/pending/foo.pdf --apply
  python scripts/enrich_pending_pdf.py data/raw/<domain>/pending/foo.pdf --chinese-title "高速冲蚀6061铝合金" --apply
  python scripts/enrich_pending_pdf.py data/raw/<domain>/pending/foo.pdf --doi 10.xxxx/xxxxx --apply
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.services.metadata_enrichment_service import (
    enrich_from_pdf,
    enrich_from_doi,
    extract_doi_from_filename,
)
from src.utils.atomic_io import atomic_write_json


def _read_sidecar(pdf_path: Path) -> dict:
    sidecar = pdf_path.with_suffix(".json")
    if sidecar.exists():
        try:
            return json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich a pending PDF with metadata.")
    parser.add_argument("pdf_path", type=Path, help="pending PDF path or path to data/papers/<id>/")
    parser.add_argument("--apply", action="store_true", help="write to sidecar (default dry-run)")
    parser.add_argument("--doi", default="", help="explicit DOI (skip extraction)")
    parser.add_argument("--chinese-title", default="", help="中文标题")
    parser.add_argument("--force", action="store_true", help="overwrite existing canonical_paper_id")
    args = parser.parse_args()

    pdf_path = args.pdf_path
    if not pdf_path.exists():
        logger.error(f"file not found: {pdf_path}")
        return 1

    # Check if it's a paper directory (data/papers/<id>/)
    if pdf_path.is_dir() and (pdf_path / "paper.md").exists():
        paper_md = pdf_path / "paper.md"
        # Try to find DOI from paper.md
        from src.services.metadata_enrichment_service import extract_doi_from_paper_md
        text = paper_md.read_text(encoding="utf-8")
        doi = args.doi or extract_doi_from_paper_md(text) or ""
        logger.info(f"paper directory: {pdf_path.name}")
        if doi:
            logger.info(f"DOI from paper.md: {doi}")
        sidecar_data = {"doi": doi}
    else:
        sidecar_data = _read_sidecar(pdf_path)

    # Check for existing canonical_paper_id
    if sidecar_data.get("canonical_paper_id") and not args.force:
        logger.warning(
            f"sidecar already has canonical_paper_id: {sidecar_data['canonical_paper_id']}. "
            f"Use --force to overwrite."
        )
        return 0

    # Enrich
    if args.doi:
        doi = args.doi
        result = enrich_from_doi(doi, chinese_title=args.chinese_title)
    elif pdf_path.is_dir():
        result = enrich_from_doi(doi, chinese_title=args.chinese_title)
    else:
        result = enrich_from_pdf(
            pdf_path,
            sidecar=sidecar_data,
            chinese_title=args.chinese_title or sidecar_data.get("chinese_title", ""),
        )

    # Output
    print(f"\n{'='*60}")
    print(f"PDF: {pdf_path}")
    print(f"DOI: {result.doi or '(not found)'}")
    print(f"Title: {result.title or '(not found)'}")
    print(f"Year: {result.year or '(not found)'}")
    print(f"Authors: {', '.join(result.authors) if result.authors else '(not found)'}")
    print(f"First author: {result.first_author or '(not found)'}")
    print(f"Venue: {result.venue or '(not found)'}")
    print(f"Source: {result.source}")
    print(f"Confidence: {result.confidence}")
    print(f"Chinese title: {result.chinese_title or '(none)'}")
    print(f"Proposed paper_id: {result.proposed_paper_id}")
    if result.warnings:
        print(f"Warnings:")
        for w in result.warnings:
            print(f"  - {w}")
    print(f"{'='*60}")

    if not args.apply:
        logger.info("[dry-run] use --apply to write to sidecar")
        return 0

    # Write sidecar
    sidecar_path = pdf_path.with_suffix(".json") if not pdf_path.is_dir() else pdf_path / "sidecar.json"
    sidecar = sidecar_data if not pdf_path.is_dir() else {}
    sidecar.update({
        "doi": result.doi or sidecar.get("doi", ""),
        "title": result.title or sidecar.get("title", ""),
        "year": result.year if result.year is not None else sidecar.get("year"),
        "authors": result.authors or sidecar.get("authors", []),
        "first_author": result.first_author or sidecar.get("first_author", ""),
        "venue": result.venue or sidecar.get("venue", ""),
        "metadata_source": result.source,
        "metadata_confidence": result.confidence,
        "proposed_paper_id": result.proposed_paper_id,
    })
    if result.chinese_title:
        sidecar["chinese_title"] = result.chinese_title
    if result.warnings:
        sidecar.setdefault("warnings", []).extend(result.warnings)

    atomic_write_json(sidecar_path, sidecar, indent=2)
    logger.info(f"[OK] sidecar written: {sidecar_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
