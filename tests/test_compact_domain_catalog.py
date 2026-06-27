"""多领域 catalog compact 去重测试。"""
from src.domain_catalog import (
    compact_catalog_entries,
    compact_summary,
    load_domain_catalogs,
)


def _entry(pid, doi="", bib_key="", title="", year=None, domain="d1", hints=None):
    return {
        "paper_id": pid,
        "doi": doi,
        "title": title or pid,
        "year": year,
        "primary_domain": domain,
        "domains": [domain],
        "selection_hints": hints or {"read_when_question_contains": [], "do_not_use_for": [], "priority": 3},
        "citation": {"bib_key": bib_key},
        "_source_domain": domain,
    }


def test_compact_dedupes_by_paper_id_and_keeps_source_domains():
    entries = [
        _entry("p1", domain="blowing_snow_physics", hints={"read_when_question_contains": ["a"], "do_not_use_for": [], "priority": 3}),
        _entry("p1", domain="aeolian_snow_transport", hints={"read_when_question_contains": ["b"], "do_not_use_for": [], "priority": 3}),
        _entry("p2", domain="blowing_snow_physics"),
    ]
    out = compact_catalog_entries(entries)
    assert len(out) == 2
    p1 = next(e for e in out if e["paper_id"] == "p1")
    assert p1["source_domains"] == ["blowing_snow_physics", "aeolian_snow_transport"]
    # selection_hints 列表字段并集合并
    assert set(p1["selection_hints"]["read_when_question_contains"]) == {"a", "b"}


def test_compact_fallback_to_doi_then_bib_then_title():
    # 无 paper_id，按 doi 去重
    e1 = _entry("", doi="10.1/x", domain="d1")
    e2 = _entry("", doi="10.1/x", domain="d2")
    assert len(compact_catalog_entries([e1, e2])) == 1
    # 无 paper_id/doi，按 bib_key
    e3 = _entry("", bib_key="k1", domain="d1")
    e4 = _entry("", bib_key="k1", domain="d2")
    assert len(compact_catalog_entries([e3, e4])) == 1
    # 无 paper_id/doi/bib，按 title+year
    e5 = _entry("", title="Snow Storm", year=2020, domain="d1")
    e6 = _entry("", title="Snow Storm", year=2020, domain="d2")
    assert len(compact_catalog_entries([e5, e6])) == 1


def test_compact_summary_counts():
    entries = [
        _entry("p1", domain="d1"),
        _entry("p1", domain="d2"),
        _entry("p2", domain="d1"),
    ]
    out = compact_catalog_entries(entries)
    summary = compact_summary(entries, out)
    assert summary["raw_count"] == 3
    assert summary["compacted_count"] == 2
    assert summary["duplicate_count"] == 1
    assert summary["per_paper_domains"]["p1"] == ["d1", "d2"]


def test_load_domain_catalogs_rejects_invalid_domain():
    import pytest
    with pytest.raises(ValueError):
        load_domain_catalogs(["not_a_domain"])
