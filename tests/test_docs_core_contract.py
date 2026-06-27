"""核心契约文档存在性与关键词检查。

确保 AGENTS.md / CLAUDE.md / docs/PROJECT_CONTRACT.md 存在且包含必需关键词。
防止后续代码代理删除核心需求。
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

REQUIRED_FILES = [
    PROJECT_ROOT / "AGENTS.md",
    PROJECT_ROOT / "CLAUDE.md",
    PROJECT_ROOT / "docs" / "PROJECT_CONTRACT.md",
    PROJECT_ROOT / "docs" / "PDF_RESOLVER_DESIGN.md",
    PROJECT_ROOT / "docs" / "PDF_RESOLVER_INTEGRATION_PLAN.md",
    PROJECT_ROOT / "docs" / "THIRD_PARTY_INTEGRATION.md",
    PROJECT_ROOT / "docs" / "ZOTERO_INTEGRATION.md",
]

# 关键词不用改，已经在上一轮改过了


REQUIRED_KEYWORDS = [
    "核心契约",
    "access policy",
    "oa_only",
    "开放获取",
    "resolver chain",
    "domain catalog",
    "可以重复索引",
    "paper 物理存储",
    "不能重复",
    "library_index.json",
    "compact",
    "pending PDF",
    "duplicate detection",
    "RAG",
    "LLM client",
    "pack_repo.py",
]


def test_core_contract_files_exist():
    for f in REQUIRED_FILES:
        assert f.exists(), f"missing: {f}"


def test_core_contract_contains_keywords():
    """每个必要关键词至少在一个契约文档中出现。"""
    all_text = ""
    for f in REQUIRED_FILES:
        all_text += f.read_text(encoding="utf-8").lower() + "\n"
    missing = []
    for kw in REQUIRED_KEYWORDS:
        if kw.lower() not in all_text:
            missing.append(kw)
    assert missing == [], f"keywords missing from contract docs: {missing}"
