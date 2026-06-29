"""Match/enrich metadata for data/paper_raw/<000001>/<000001>.pdf."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from config.settings import PAPER_RAW_DIR
from src.discovery.models import normalize_doi
from src.services.metadata_enrichment_service import enrich_from_pdf, enrich_from_doi
from src.services.v2_library import empty_metadata, merge_missing_metadata
from src.utils.atomic_io import atomic_write_json


def _source_ids(root: Path, all_sources: bool, one: str | None) -> list[str]:
    if one:
        return [one]
    if all_sources:
        return sorted(p.name for p in root.iterdir() if p.is_dir() and p.name.isdigit() and len(p.name) == 6)
    raise ValueError("--source-id or --all is required")


def _patch_from_enrichment(source_id: str, result) -> dict:
    patch = empty_metadata(source_id, source_type="metadata_match")
    if getattr(result, "title", ""):
        patch["title"]["original"] = result.title
    if getattr(result, "year", None) is not None:
        patch["year"] = result.year
    if getattr(result, "doi", ""):
        patch["identifiers"]["doi"] = result.doi
    if getattr(result, "venue", ""):
        patch["container"]["journal"] = result.venue
    if getattr(result, "publisher", ""):
        patch["container"]["publisher"] = result.publisher
    for attr, key in (
        ("volume", "volume"),
        ("number", "number"),
        ("issue", "issue"),
        ("pages", "pages"),
        ("article_number", "article_number"),
    ):
        value = getattr(result, attr, "")
        if value:
            patch["publication"][key] = str(value)
    if not patch["publication"]["number"] and patch["publication"]["issue"]:
        patch["publication"]["number"] = patch["publication"]["issue"]
    if not patch["publication"]["issue"] and patch["publication"]["number"]:
        patch["publication"]["issue"] = patch["publication"]["number"]
    if getattr(result, "issn", ""):
        patch["identifiers"]["issn"] = result.issn
    if getattr(result, "url", ""):
        patch["links"]["url"] = result.url
    if getattr(result, "published", ""):
        patch["date"]["published"] = result.published
    authors = getattr(result, "authors", None) or []
    if authors:
        normalized = []
        for author in authors:
            if isinstance(author, dict):
                normalized.append({
                    "full_name": author.get("full_name") or author.get("name") or "",
                    "family": author.get("family") or "",
                    "given": author.get("given") or "",
                    "orcid": author.get("orcid") or "",
                    "affiliation": author.get("affiliation") or "",
                })
            else:
                normalized.append({"full_name": str(author), "family": "", "given": "", "orcid": "", "affiliation": ""})
        patch["authors"] = normalized
        patch["first_author"] = {"family": normalized[0].get("family", ""), "display": normalized[0].get("full_name", "")}
    return patch


def _has_bibliographic_identity(metadata: dict) -> bool:
    doi = ((metadata.get("identifiers") or {}).get("doi") or "").strip()
    title = ((metadata.get("title") or {}).get("original") or "").strip()
    year = metadata.get("year")
    authors = metadata.get("authors") or []
    has_author = any((a.get("full_name") or a.get("family")) for a in authors if isinstance(a, dict))
    return bool(doi and title and year and has_author)


def main() -> int:
    parser = argparse.ArgumentParser(description="Match metadata for v2 paper_raw PDFs.")
    parser.add_argument("--source-id", default=None)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--paper-raw-dir", type=Path, default=PAPER_RAW_DIR)
    parser.add_argument("--manual-confirm", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    write = args.apply and not args.dry_run
    report = []
    for source_id in _source_ids(args.paper_raw_dir, args.all, args.source_id):
        folder = args.paper_raw_dir / source_id
        pdf = folder / f"{source_id}.pdf"
        meta_path = folder / f"{source_id}.metadata.json"
        item = {"source_id": source_id, "status": "planned", "warnings": []}
        if not pdf.exists() or not meta_path.exists():
            item.update({"status": "failed", "error": "source PDF or metadata missing"})
            report.append(item)
            continue
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        try:
            result = None
            doi = ((metadata.get("identifiers") or {}).get("doi") or "").strip()
            if doi:
                try:
                    result = enrich_from_doi(doi)
                except Exception as exc:
                    item["warnings"].append(f"DOI enrichment failed: {exc}")
            if result is None:
                result = enrich_from_pdf(pdf)
            result_doi = normalize_doi(getattr(result, "doi", ""))
            existing_doi = normalize_doi(doi)
            doi_conflict = bool(existing_doi and result_doi and existing_doi != result_doi)
            if doi_conflict:
                item["warnings"].append(
                    "Crossref DOI conflicts with existing metadata.identifiers.doi; manual confirmation required"
                )
            patch = _patch_from_enrichment(source_id, result)
            metadata, merge_warnings = merge_missing_metadata(metadata, patch)
            item["warnings"].extend(merge_warnings)
            final_doi = normalize_doi((metadata.get("identifiers") or {}).get("doi"))
            if final_doi:
                metadata["identifiers"]["doi"] = final_doi
            if args.manual_confirm and not final_doi:
                item["warnings"].append("manual confirmation requires metadata.identifiers.doi")
            if not final_doi:
                item["warnings"].append("metadata.identifiers.doi is required for matched metadata")
            matched = bool(final_doi and _has_bibliographic_identity(metadata) and not doi_conflict)
            status = "manual_confirmed" if args.manual_confirm and matched else "matched" if matched else "unmatched"
            metadata["metadata_match"] = {
                "status": status,
                "source": getattr(result, "source", "") if matched else "",
                "confidence": float(getattr(result, "confidence", 0.0) or (0.8 if matched else 0.0)),
                "matched_at": datetime.now().isoformat(timespec="seconds"),
                "warnings": item["warnings"] or ([] if matched else ["no reliable metadata match"]),
                "candidates": [],
            }
            item["status"] = status
            if write:
                atomic_write_json(meta_path, metadata, indent=2)
                if status == "unmatched":
                    atomic_write_json(folder / ".import_status.json", {
                        "status": "metadata_unmatched",
                        "reason": "; ".join(metadata["metadata_match"]["warnings"]),
                        "created_at": datetime.now().isoformat(timespec="seconds"),
                    }, indent=2)
        except Exception as exc:
            item.update({"status": "failed", "error": str(exc)})
            logger.error("metadata match failed for {}: {}", source_id, exc)
        report.append(item)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"applied": write, "items": report}, ensure_ascii=False, indent=2))
    return 1 if any(i["status"] == "failed" for i in report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
