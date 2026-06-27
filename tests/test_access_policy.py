"""access_policy 数据模型测试。"""
from src.fetch.access_policy import AccessMode, AccessPolicy


def test_default_is_oa_only():
    p = AccessPolicy()
    assert p.mode == AccessMode.OA_ONLY
    assert p.enabled_resolver_names() == [
        "unpaywall", "openalex", "semantic_scholar", "arxiv", "publisher_oa",
        "wiley_tdm", "springer_direct", "elsevier_tdm",
        "biorxiv", "pmc_oa", "scihub",
    ]


def test_oa_only_excludes_non_oa():
    p = AccessPolicy(mode=AccessMode.OA_ONLY)
    enabled = p.enabled_resolver_names()
    assert "publisher_tdm" not in enabled
    assert "institutional_browser" not in enabled
    assert "browser_assisted" not in enabled
    assert "local_manual" not in enabled


def test_institutional_includes_extra():
    p = AccessPolicy(mode=AccessMode.INSTITUTIONAL)
    enabled = p.enabled_resolver_names()
    assert "unpaywall" in enabled
    assert "publisher_tdm" in enabled
    assert "institutional_browser" in enabled


def test_browser_assisted():
    p = AccessPolicy(mode=AccessMode.BROWSER_ASSISTED)
    enabled = p.enabled_resolver_names()
    assert "browser_assisted" in enabled
    assert "publisher_tdm" not in enabled


def test_local_manual_only():
    p = AccessPolicy(mode=AccessMode.LOCAL_MANUAL)
    assert p.enabled_resolver_names() == ["local_manual"]


def test_custom_only_when_configured():
    p = AccessPolicy(mode=AccessMode.CUSTOM, allow_custom_resolvers=False)
    assert "unpaywall" in p.enabled_resolver_names()  # base OA still present
    # custom resolvers not added unless flag set
    enabled = p.enabled_resolver_names()
    assert "my_resolver" not in enabled

    p2 = AccessPolicy(mode=AccessMode.CUSTOM, allow_custom_resolvers=True,
                      custom_resolvers=["my_resolver"])
    enabled2 = p2.enabled_resolver_names()
    assert "my_resolver" in enabled2


def test_clone_with():
    p = AccessPolicy(mode=AccessMode.OA_ONLY)
    p2 = p.clone_with(mode=AccessMode.INSTITUTIONAL)
    assert p2.mode == AccessMode.INSTITUTIONAL
    assert p.mode == AccessMode.OA_ONLY  # unchanged
