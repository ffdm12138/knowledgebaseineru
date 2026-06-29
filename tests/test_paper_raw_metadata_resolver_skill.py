"""Tests for the paper_raw_metadata_resolver skill files and boundary docs."""
from __future__ import annotations

import json
from pathlib import Path


_ROOT = Path(__file__).resolve().parent.parent / "skills" / "paper_raw_metadata_resolver"


def test_resolver_skill_files_exist():
    for name in [
        "SKILL.md",
        "README.md",
        "CLAUDE.md",
        "metadata_candidate_schema.json",
        "metadata_patch_schema.json",
        "examples/example_input.md",
        "examples/example_candidates.json",
        "examples/example_metadata_patch.json",
    ]:
        assert (_ROOT / name).exists(), f"missing skill file: {name}"


def test_resolver_skill_has_frontmatter():
    text = (_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "name: paper_raw_metadata_resolver" in text
    assert "description:" in text


def test_resolver_skill_documents_boundaries():
    text = (_ROOT / "SKILL.md").read_text(encoding="utf-8").lower()
    # input only from paper_raw
    assert "data/paper_raw" in text
    assert "metadata.json" in text
    # never read formal sources
    assert "data/papers" in text
    assert "never read" in text or "不得读取" in text or "不得读" in text
    # never fabricate DOI
    assert "doi" in text
    assert "fabricate" in text or "编造" in text
    # LLM-guessed DOI is invalid
    assert "llm" in text and ("invalid" in text or "无效" in text)
    # must NOT set metadata_match.status
    assert "metadata_match.status" in text
    assert "不得" in text or "must not" in text or "must not set" in text
    # outputs candidates + patch only
    assert "candidates" in text and "patch" in text


def test_candidate_schema_requires_doi_pattern():
    schema = json.loads((_ROOT / "metadata_candidate_schema.json").read_text(encoding="utf-8"))
    assert schema["type"] == "object"
    cand_item = schema["properties"]["candidates"]["items"]
    doi_prop = cand_item["properties"]["doi"]
    assert "pattern" in doi_prop
    assert doi_prop["pattern"].startswith("^10")
    rec = schema["properties"]["recommendation"]["properties"]["decision"]
    assert "auto_matched" in rec["enum"]
    assert "manual_review" in rec["enum"]


def test_patch_schema_shares_curator_shape():
    schema = json.loads((_ROOT / "metadata_patch_schema.json").read_text(encoding="utf-8"))
    props = schema["properties"]
    for key in ("title", "authors", "year", "container", "publication", "identifiers", "links"):
        assert key in props, f"patch schema missing {key}"
    assert "doi" in props["identifiers"]["properties"]


def test_examples_are_valid_json():
    cands = json.loads((_ROOT / "examples/example_candidates.json").read_text(encoding="utf-8"))
    assert "candidates" in cands and "recommendation" in cands
    patch = json.loads((_ROOT / "examples/example_metadata_patch.json").read_text(encoding="utf-8"))
    assert "identifiers" in patch and patch["identifiers"]["doi"]
