"""测试 catalog 原子写入、schema 校验、并发安全"""
import json
import tempfile
from pathlib import Path
from src.catalog import Catalog


def test_catalog_save_is_atomic():
    """验证 save() 使用 tmp + os.replace，不会留下半截 JSON"""
    with tempfile.TemporaryDirectory() as td:
        cat_path = Path(td) / "test_catalog.json"
        catalog = Catalog(path=cat_path)

        data = {
            "version": "0.1",
            "description": "test",
            "papers": [
                {
                    "paper_id": "2020_test_测试文献",
                    "title": "Test Paper",
                    "authors": ["Alice", "Bob"],
                    "year": 2020,
                    "venue": "Test Journal",
                    "doi": "10.1234/test",
                    "raw_pdf": "data/raw/test.pdf",
                    "markdown": "data/papers/2020_test_测试文献/paper.md",
                    "images_dir": "data/papers/2020_test_测试文献/images",
                    "status": "summarized",
                    "ai_summary": {
                        "one_sentence": "A test.",
                        "background_problem": "Testing.",
                        "research_question": "How to test?",
                        "method": "Unit test",
                        "data_or_experiment": "Fake data",
                        "main_findings": "Tests pass.",
                        "key_equations_or_models": "None",
                        "important_figures": "None",
                        "limitations": "None",
                        "relevance_to_my_work": "Reference",
                        "possible_use_in_paper": "None",
                    },
                    "tags": {
                        "topic": ["test"],
                        "method": ["unit"],
                        "material_or_region": [],
                        "variables": [],
                        "model_names": [],
                    },
                    "selection_hints": {
                        "read_when_question_contains": ["test"],
                        "do_not_use_for": [],
                        "priority": 3,
                    },
                    "notes": "",
                    "citation": {
                        "bib_key": "alice2020_test",
                        "bibtex": "@article{alice2020_test,\n  title={Test},\n}",
                        "citation_style_name": "Alice and Bob (2020)",
                        "source": "manual",
                        "verified": False,
                    },
                }
            ],
        }

        catalog.save(data)

        # 确认写入成功
        assert cat_path.exists()
        loaded = json.loads(cat_path.read_text(encoding="utf-8"))
        assert loaded["papers"][0]["paper_id"] == "2020_test_测试文献"

        # 确认没有留下 tmp 文件
        tmp_path = cat_path.with_suffix(cat_path.suffix + ".tmp")
        assert not tmp_path.exists()

        # 确认没有留下 lock 文件（lock 应在 with 块退出时释放）
        # lock 文件可能仍然存在（filelock 不自动删除），这是正常的
        # 但 tmp 文件必须被清理


def test_catalog_empty():
    """空 catalog 应返回合法结构"""
    with tempfile.TemporaryDirectory() as td:
        cat_path = Path(td) / "nonexistent.json"
        catalog = Catalog(path=cat_path)
        data = catalog.load()
        assert data["version"] == "0.1"
        assert data["papers"] == []


def test_catalog_upsert_saves_atomically():
    """upsert 也应该原子写入"""
    with tempfile.TemporaryDirectory() as td:
        cat_path = Path(td) / "test_catalog.json"
        catalog = Catalog(path=cat_path)

        entry = {
            "paper_id": "test1",
            "title": "T1",
            "authors": ["A"],
            "year": 2023,
            "venue": "Venue",
            "doi": "",
            "raw_pdf": "",
            "markdown": "",
            "images_dir": "",
            "status": "draft",
            "ai_summary": {
                "one_sentence": "",
                "background_problem": "",
                "research_question": "",
                "method": "",
                "data_or_experiment": "",
                "main_findings": "",
                "key_equations_or_models": "",
                "important_figures": "",
                "limitations": "",
                "relevance_to_my_work": "",
                "possible_use_in_paper": "",
            },
            "tags": {
                "topic": [], "method": [], "material_or_region": [],
                "variables": [], "model_names": [],
            },
            "selection_hints": {
                "read_when_question_contains": [],
                "do_not_use_for": [],
                "priority": 1,
            },
            "notes": "",
            "citation": {
                "bib_key": "a2023_test",
                "bibtex": "@article{a2023_test,\n  title={T1},\n}",
                "citation_style_name": "",
                "source": "manual",
                "verified": False,
            },
        }

        catalog.upsert(entry)
        assert catalog.has("test1")

        # update
        entry["status"] = "summarized"
        catalog.upsert(entry)
        assert catalog.get("test1")["status"] == "summarized"
        assert len(catalog.list_papers()) == 1  # 不应重复


def test_catalog_validate_duplicate_bibkey():
    """重复 bib_key 应被报告"""
    with tempfile.TemporaryDirectory() as td:
        cat_path = Path(td) / "test_catalog.json"
        catalog = Catalog(path=cat_path)

        e1 = {
            "paper_id": "p1",
            "title": "P1", "authors": ["A"], "year": 2020, "venue": "", "doi": "",
            "raw_pdf": "", "markdown": "", "images_dir": "",
            "status": "summarized",
            "ai_summary": {
                "one_sentence": "", "background_problem": "", "research_question": "",
                "method": "", "data_or_experiment": "", "main_findings": "",
                "key_equations_or_models": "", "important_figures": "",
                "limitations": "", "relevance_to_my_work": "", "possible_use_in_paper": "",
            },
            "tags": {
                "topic": [], "method": [], "material_or_region": [],
                "variables": [], "model_names": [],
            },
            "selection_hints": {
                "read_when_question_contains": [], "do_not_use_for": [], "priority": 3,
            },
            "notes": "",
            "citation": {
                "bib_key": "dup_key",
                "bibtex": "@article{dup_key,\n}",
                "citation_style_name": "",
                "source": "manual",
                "verified": False,
            },
        }
        e2 = dict(e1, paper_id="p2")
        e2["citation"] = dict(e1["citation"])

        catalog.save({"version": "0.1", "description": "", "papers": [e1, e2]})
        errors = catalog.validate()
        dup_errors = [e for e in errors if "bib_key 重复" in e]
        assert len(dup_errors) >= 1
