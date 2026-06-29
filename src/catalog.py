"""Read-only v2 catalog access backed by data/catalog/all.catalog.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.settings import ALL_CATALOG_PATH
from src.services.v2_library import AllCatalogBuilder


def _read_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        return default or {}
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt_score(value: Any) -> str:
    return str(value) if value not in (None, "") else "-"


def build_compact_catalog_text(papers: list[dict]) -> str:
    lines = ["# 文献目录（紧凑视图）", ""]
    for entry in papers:
        pid = entry.get("paper_id", "")
        number = entry.get("paper_number", "")
        catalog = entry.get("catalog") or {}
        metadata = entry.get("metadata") or {}
        display = catalog.get("display") or {}
        card = catalog.get("research_card") or {}
        classification = catalog.get("classification") or {}
        screening = catalog.get("screening") or {}
        title = display.get("title_zh") or display.get("title_original") or (metadata.get("title") or {}).get("original", "")
        year = display.get("year")
        if year is None or year == "":
            year = metadata.get("year") or ""
        venue = display.get("venue") or ""
        doi = display.get("doi") or ""
        domain_bits = []
        if classification.get("primary_domain"):
            domain_bits.append(str(classification["primary_domain"]))
        topics = classification.get("topics") or []
        if topics:
            domain_bits.append(",".join(topics))
        domain = " / ".join(domain_bits)
        read_decision = screening.get("read_decision") or ""
        relevance = _fmt_score(screening.get("relevance_score"))
        priority = _fmt_score(screening.get("reading_priority"))
        one_sentence = card.get("one_sentence_summary_zh") or "(未总结)"
        method = card.get("method_zh") or ""
        conclusion = card.get("main_conclusion_zh") or ""
        usefulness = card.get("usefulness_for_project_zh") or ""
        best_for = ",".join(screening.get("best_for_sections") or [])
        lines.append(f"- [{priority}] {number} {pid} {title}")
        meta_bits = []
        if year not in ("", None):
            meta_bits.append(str(year))
        if display.get("authors_short"):
            meta_bits.append(display["authors_short"])
        if venue:
            meta_bits.append(venue)
        if doi:
            meta_bits.append(doi)
        if meta_bits:
            lines.append(f"  meta: {' | '.join(meta_bits)}")
        if domain:
            lines.append(f"  domain: {domain}")
        decision_bits = []
        if read_decision:
            decision_bits.append(f"read={read_decision}")
        decision_bits.append(f"relevance={relevance}")
        decision_bits.append(f"priority={priority}")
        lines.append(f"  screening: {' '.join(decision_bits)}")
        lines.append(f"  summary: {one_sentence}")
        if method:
            lines.append(f"  method: {method}")
        if conclusion:
            lines.append(f"  conclusion: {conclusion}")
        if usefulness:
            lines.append(f"  usefulness: {usefulness}")
        if best_for:
            lines.append(f"  best_for_sections: {best_for}")
    return "\n".join(lines)


class Catalog:
    """Small compatibility wrapper over the v2 all-catalog file."""

    def __init__(self, path: Path = ALL_CATALOG_PATH):
        self.path = Path(path)

    @staticmethod
    def _empty_data() -> dict:
        return {"schema_version": "1.0", "papers": []}

    def load(self) -> dict:
        if not self.path.exists():
            return AllCatalogBuilder(all_catalog_path=self.path).build(write=True)
        return _read_json(self.path, self._empty_data())

    def list_papers(self) -> list[dict]:
        return list(self.load().get("papers", []))

    def get(self, paper_id_or_number: str) -> dict | None:
        for item in self.list_papers():
            if item.get("paper_id") == paper_id_or_number or item.get("paper_number") == paper_id_or_number:
                return item
        return None

    def validate(self) -> list[str]:
        errors: list[str] = []
        data = self.load()
        if not isinstance(data.get("papers"), list):
            return ["all catalog missing papers list"]
        seen_numbers: set[str] = set()
        seen_ids: set[str] = set()
        for i, item in enumerate(data["papers"]):
            ctx = f"papers[{i}]"
            for key in ("paper_number", "paper_id", "folder_path", "main_md", "pdf", "images_dir", "metadata_file", "catalog_file", "metadata", "catalog"):
                if key not in item:
                    errors.append(f"{ctx} missing {key}")
            number = item.get("paper_number")
            pid = item.get("paper_id")
            if number in seen_numbers:
                errors.append(f"{ctx} duplicate paper_number {number}")
            if pid in seen_ids:
                errors.append(f"{ctx} duplicate paper_id {pid}")
            seen_numbers.add(number)
            seen_ids.add(pid)
        return errors

    def build_compact_catalog(self, topics: list[str] | None = None) -> str:
        papers = self.list_papers()
        if topics:
            wanted = set(topics)
            papers = [
                p for p in papers
                if wanted & set(((p.get("catalog") or {}).get("classification") or {}).get("topics") or [])
            ]
        return build_compact_catalog_text(papers)

    def compact_items(self, topics: list[str] | None = None) -> list[dict[str, Any]]:
        papers = self.list_papers()
        if topics:
            wanted = set(topics)
            papers = [
                p for p in papers
                if wanted & set(((p.get("catalog") or {}).get("classification") or {}).get("topics") or [])
            ]
        return papers
