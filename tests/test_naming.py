"""测试 paper_id 命名、canonical 映射、校验、重复检测"""
import pytest
from src.naming import (derive_paper_id, sanitize_paper_id, is_known_duplicate,
                        canonical_paper_id_for, validate_paper_id)


def test_sanitize_replaces_illegal():
    assert sanitize_paper_id("a/b:c?d") == "a_b_c_d"
    assert sanitize_paper_id("  x  y ") == "x_y"
    assert sanitize_paper_id("") == "untitled"


def test_derive_uses_canonical_mapping():
    # 1982野外升华率实验.pdf 在 config/paper_ids.py 映射到规范 id
    pid = derive_paper_id("1982野外升华率实验.pdf")
    assert pid == "1982_schmidt_风吹雪垂直剖面"


def test_derive_fallback_to_cleaned_stem():
    pid = derive_paper_id("Some Random Paper.pdf")
    assert pid == "Some_Random_Paper"


def test_canonical_paper_id_for():
    assert canonical_paper_id_for("1982野外升华率实验.pdf") == "1982_schmidt_风吹雪垂直剖面"
    assert canonical_paper_id_for("unknown.pdf") is None


def test_is_known_duplicate():
    # Dery_Yau_1999 与 comola2017破碎 在 DUPLICATE_RAW_STEMS
    assert is_known_duplicate("Dery_Yau_1999_A_Bulk_Blowing_Snow_Model.pdf") is True
    assert is_known_duplicate("comola2017破碎.pdf") is True
    assert is_known_duplicate("1999悬移控制方程.pdf") is False


@pytest.mark.parametrize("bad", ["../../abc", "a/b", "a\\b", "..\\..\\test", "a:b", ""])
def test_validate_paper_id_rejects(bad):
    with pytest.raises(ValueError):
        validate_paper_id(bad)


def test_validate_paper_id_accepts():
    assert validate_paper_id("1999_dery_吹雪体相模型") == "1999_dery_吹雪体相模型"
    assert validate_paper_id("paper_2023") == "paper_2023"
