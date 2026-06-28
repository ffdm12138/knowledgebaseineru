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
    PROJECT_ROOT / "docs" / "LLM_USAGE_WORKFLOW.md",
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


def test_docs_do_not_claim_start_bat_starts_watcher_by_default():
    docs = [
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "AGENTS.md",
        PROJECT_ROOT / "CLAUDE.md",
        PROJECT_ROOT / "docs" / "ARCHITECTURE.md",
    ]
    forbidden = [
        "start.bat 默认启动 watcher",
        "start.bat 默认启动的 watcher",
        "默认启动 watcher",
    ]
    for path in docs:
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, f"{path} still contains old watcher wording: {phrase}"


def test_no_legacy_rag_positive_docs_outside_archive():
    roots = [
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "AGENTS.md",
        PROJECT_ROOT / "CLAUDE.md",
        PROJECT_ROOT / "docs",
        PROJECT_ROOT / "skills",
        PROJECT_ROOT / "md",
    ]
    forbidden = [
        "ChromaDB 索引",
        "embedding 索引",
        "RAG 问答接口",
        "语义搜索 + RAG",
        "向量化 + ChromaDB",
        "POST /search",
        "POST /ask",
    ]
    files = []
    for root in roots:
        if root.is_file():
            files.append(root)
        elif root.exists():
            files.extend(p for p in root.rglob("*") if p.is_file() and "docs/archive" not in p.as_posix())
    for path in files:
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, f"{path} contains legacy RAG wording: {phrase}"


def test_agents_and_claude_key_semantics_aligned():
    required = [
        "START_WATCHER=0",
        "cli_api_proxy",
        "unregistered_converted",
        "register_manual_pdf.py",
        "import_pending_pdf.py --apply",
    ]
    for filename in ["AGENTS.md", "CLAUDE.md"]:
        text = (PROJECT_ROOT / filename).read_text(encoding="utf-8")
        for phrase in required:
            assert phrase in text, f"{filename} missing {phrase}"


def test_readme_does_not_describe_upload_as_formal_import():
    text = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "| POST | `/upload` | 上传 → MinerU 转 → 清理 → 入库 |" not in text
    assert "缺 metadata 时为 unregistered_converted" in text


def test_llm_usage_workflow_lists_stable_interfaces():
    path = PROJECT_ROOT / "docs" / "LLM_USAGE_WORKFLOW.md"
    text = path.read_text(encoding="utf-8")
    required = [
        "data/papers/<paper_id>/paper.md",
        "data/papers/<paper_id>/images/",
        "data/catalog/literature_catalog.json",
        "data/catalog/library_index.json",
        "data/catalog/domains/<domain>/literature_catalog.json",
        "data/catalog/domains/<domain>/references.bib",
        "data/manifests/papers_manifest.json",
    ]
    for phrase in required:
        assert phrase in text


def test_literature_library_manager_skill_exists_and_covers_workflows():
    base = PROJECT_ROOT / "skills" / "literature_library_manager"
    for name in ["SKILL.md", "README.md", "AGENTS.md", "CLAUDE.md"]:
        assert (base / name).exists()
    text = "\n".join((base / name).read_text(encoding="utf-8") for name in ["SKILL.md", "README.md"])
    for phrase in ["register_manual_pdf", "discover_papers", "fetch_pdf", "list_pending_pdfs", "import_pending_pdf"]:
        assert phrase in text


def test_domain_config_contains_expected_domains_and_invalid_domain_errors():
    import json
    from src.library_index import VALID_DOMAINS, validate_domains

    path = PROJECT_ROOT / "config" / "domains.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "abl_pbl",
        "blowing_snow_physics",
        "aeolian_snow_transport",
        "erosion_experiments",
        "openfoam_particle_modeling",
        "cryowrf_hydro",
    }
    assert required <= set(data)
    assert required <= set(VALID_DOMAINS)
    errors = validate_domains("not_a_domain", ["not_a_domain"])
    assert any("invalid primary_domain" in err for err in errors)
    assert any("invalid domain" in err for err in errors)
