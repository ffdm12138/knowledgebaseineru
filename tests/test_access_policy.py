"""access_policy 数据模型测试。"""
from src.fetch.access_policy import AccessMode, AccessPolicy


def test_default_is_oa_only():
    p = AccessPolicy()
    assert p.mode == AccessMode.OA_ONLY
    assert p.enabled_resolver_names() == [
        "unpaywall", "openalex", "semantic_scholar", "arxiv",
        "publisher_oa", "springer_direct",
        "biorxiv", "pmc_oa",
    ]


def test_oa_only_excludes_non_oa():
    p = AccessPolicy(mode=AccessMode.OA_ONLY)
    enabled = p.enabled_resolver_names()
    assert "publisher_tdm" not in enabled
    assert "institutional_browser" not in enabled
    assert "browser_assisted" not in enabled
    assert "local_manual" not in enabled
    assert "scihub" not in enabled
    assert "wiley_tdm" not in enabled
    assert "elsevier_tdm" not in enabled


def test_oa_only_no_scihub():
    """契约要求：OA_ONLY 不得含 Sci-Hub。"""
    p = AccessPolicy(mode=AccessMode.OA_ONLY)
    assert "scihub" not in p.enabled_resolver_names()
    # CUSTOM 且 allow_scihub=True 才启用
    p2 = AccessPolicy(mode=AccessMode.CUSTOM, allow_scihub=True)
    assert "scihub" in p2.enabled_resolver_names()
    p3 = AccessPolicy(mode=AccessMode.CUSTOM, allow_scihub=False)
    assert "scihub" not in p3.enabled_resolver_names()


def test_custom_tdm_controlled_by_flag():
    """CUSTOM 模式 TDM resolver 受 allow_publisher_tdm 控制。"""
    p = AccessPolicy(mode=AccessMode.CUSTOM, allow_publisher_tdm=True)
    enabled = p.enabled_resolver_names()
    assert "wiley_tdm" in enabled
    assert "elsevier_tdm" in enabled

    p2 = AccessPolicy(mode=AccessMode.CUSTOM, allow_publisher_tdm=False)
    enabled2 = p2.enabled_resolver_names()
    assert "wiley_tdm" not in enabled2
    assert "elsevier_tdm" not in enabled2


def test_institutional_includes_extra():
    p = AccessPolicy(mode=AccessMode.INSTITUTIONAL)
    enabled = p.enabled_resolver_names()
    assert "unpaywall" in enabled
    assert "publisher_tdm" in enabled
    assert "institutional_browser" in enabled
    assert "wiley_tdm" in enabled
    assert "elsevier_tdm" in enabled


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
