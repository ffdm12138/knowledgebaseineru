"""文档一致性检查：确保 AGENTS/CLAUDE/README/docs 入口与关键边界声明保持同步。

不访问网络，不依赖真实 data/papers。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ── 1. README 链接存在 ─────────────────────────────────────────────
def test_readme_links_to_core_docs_exist():
    readme = _read("README.md")
    for rel in [
        "AGENTS.md",
        "CLAUDE.md",
        "docs/PROJECT_STATUS.md",
        "docs/PROJECT_CONTRACT.md",
        "docs/DEPENDENCIES_AND_EXTERNAL_TOOLS.md",
        "docs/WRITING_QUALITY_ACCEPTANCE.md",
        "docs/WRITER_PRODUCTIZATION_PLAN.md",
    ]:
        assert (ROOT / rel).exists(), f"README 引用的文档缺失: {rel}"
        assert rel in readme, f"README 未链接到 {rel}"


# ── 2. AGENTS.md / CLAUDE.md 关键边界 ──────────────────────────────
_AGENT_BOUNDARY_TERMS = [
    "ingest-v2.1",
    "writing-v0.1",
    "conda run -n mineru",
    "metadata",
    "catalog",
    "write/jobs",
    "RAG",
    "Sci-Hub",
]


def test_agents_md_contains_boundary_terms():
    text = _read("AGENTS.md")
    for term in _AGENT_BOUNDARY_TERMS:
        assert term in text, f"AGENTS.md 缺少术语: {term}"
    # Sci-Hub 必须标注 unsafe optional 或 default disabled
    assert ("unsafe optional" in text) or ("default disabled" in text), (
        "AGENTS.md 未标注 Sci-Hub unsafe optional / default disabled"
    )


def test_claude_md_contains_boundary_terms():
    text = _read("CLAUDE.md")
    for term in _AGENT_BOUNDARY_TERMS:
        assert term in text, f"CLAUDE.md 缺少术语: {term}"
    assert ("unsafe optional" in text) or ("default disabled" in text), (
        "CLAUDE.md 未标注 Sci-Hub unsafe optional / default disabled"
    )


# ── 3. PROJECT_STATUS.md ───────────────────────────────────────────
def test_project_status_covers_required_terms():
    text = _read("docs/PROJECT_STATUS.md")
    for term in [
        "ingest-v2.1",
        "writing-v0.1",
        "data/paper_raw",
        "data/papers",
        "write/jobs",
    ]:
        assert term in text, f"PROJECT_STATUS.md 缺少术语: {term}"


# ── 4. PROJECT_CONTRACT.md ─────────────────────────────────────────
def test_project_contract_covers_required_terms():
    text = _read("docs/PROJECT_CONTRACT.md")
    for term in [
        "content-only",
        "metadata",
        "catalog",
        "DOI",
        "RAG",
        "embedding",
        "vector DB",
    ]:
        assert term in text, f"PROJECT_CONTRACT.md 缺少术语: {term}"


# ── 5. DEPENDENCIES_AND_EXTERNAL_TOOLS.md ──────────────────────────
def test_dependencies_doc_covers_required_terms():
    text = _read("docs/DEPENDENCIES_AND_EXTERNAL_TOOLS.md")
    for term in [
        "mineru[all]",
        "PyMuPDF",
        "Crossref",
        "OpenAlex",
        "Unpaywall",
        "Sci-Hub",
        "unsafe optional",
        "ChromaDB",
        "sentence-transformers",
        "RAG",
    ]:
        assert term in text, f"DEPENDENCIES_AND_EXTERNAL_TOOLS.md 缺少术语: {term}"


# ── 6. README 不得把 write/jobs 列为可提交 ─────────────────────────
def test_readme_does_not_list_write_jobs_as_committable():
    text = _read("README.md")
    # README 应明确 write/jobs 是运行时、不提交 / 只跟踪 .gitkeep
    assert "write/jobs" in text or ".gitkeep" in text
    for forbidden in ["提交 write/jobs", "提交 `write/jobs", "write/jobs 入库"]:
        assert forbidden not in text, f"README 误将 write/jobs 列为可提交: {forbidden}"


# ── 7. PROJECT_CONTRACT 不得鼓励 RAG/embedding ─────────────────────
def test_project_contract_does_not_encourage_rag_or_embedding():
    text = _read("docs/PROJECT_CONTRACT.md")
    lower = text.lower()
    for forbidden in ["use rag", "enable embedding", "引入 rag", "启用 embedding",
                      "引入 embedding", "启用 rag"]:
        assert forbidden not in lower, f"PROJECT_CONTRACT 出现鼓励性文字: {forbidden}"
