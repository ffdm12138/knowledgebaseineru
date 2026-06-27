"""resolver 接口测试（全部 mock，不访问网络）。"""
from unittest.mock import patch

import pytest
from src.fetch.access_policy import AccessMode, AccessPolicy
from src.fetch.fetch_pipeline import _build_resolvers, fetch_oa_pdf
from src.fetch.resolvers.base import ResolveContext
from src.fetch.resolvers.oa_resolvers import (ArxivResolver,
                                              OpenAlexResolver,
                                              PublisherOAResolver,
                                              SemanticScholarResolver,
                                              UnpaywallResolver)
from src.fetch.resolvers.browser_resolvers import BrowserAssistedResolver
from src.fetch.resolvers.institutional_resolvers import (
    InstitutionalBrowserResolver, PublisherTDMResolver)
from src.fetch.resolvers.local_resolvers import LocalManualResolver
from src.fetch.models import FetchResult


def test_oa_resolver_enabled_only_in_oa():
    oa = AccessPolicy(mode=AccessMode.OA_ONLY)
    inst = AccessPolicy(mode=AccessMode.INSTITUTIONAL)
    for cls in [UnpaywallResolver, OpenAlexResolver, SemanticScholarResolver,
                ArxivResolver, PublisherOAResolver]:
        r = cls()
        assert r.enabled(oa)
        assert r.enabled(inst)  # OA resolvers also enabled in institutional


def test_institutional_resolver_enabled_only_in_institutional():
    oa = AccessPolicy(mode=AccessMode.OA_ONLY)
    inst = AccessPolicy(mode=AccessMode.INSTITUTIONAL)
    for cls in [PublisherTDMResolver, InstitutionalBrowserResolver]:
        r = cls()
        assert not r.enabled(oa)
        assert r.enabled(inst)


def test_browser_resolver_enabled_only_in_browser():
    ba = AccessPolicy(mode=AccessMode.BROWSER_ASSISTED)
    oa = AccessPolicy(mode=AccessMode.OA_ONLY)
    r = BrowserAssistedResolver()
    assert r.enabled(ba)
    assert not r.enabled(oa)


def test_local_manual_resolver():
    r = LocalManualResolver()
    assert not r.enabled(AccessPolicy(mode=AccessMode.OA_ONLY))
    assert r.enabled(AccessPolicy(mode=AccessMode.LOCAL_MANUAL))


def test_unpaywall_resolver_mock(monkeypatch):
    """mock oa_resolvers 中的 resolve_unpaywall。"""
    from src.fetch.resolvers import oa_resolvers
    monkeypatch.setattr(
        oa_resolvers, "resolve_unpaywall",
        lambda doi: FetchResult(doi=doi, success=True, pdf_url="https://example.org/p.pdf"),
    )
    r = UnpaywallResolver()
    ctx = ResolveContext(doi="10.1/x")
    result = r.resolve(ctx)
    assert result.success


def test_browser_assisted_requires_action():
    from src.fetch.models import FetchResult
    r = BrowserAssistedResolver()
    ctx = ResolveContext(doi="10.1/test")
    result = r.resolve(ctx)
    assert result.success
    assert result.requires_user_action is True
    assert "doi.org" in result.landing_url


def test_publisher_tdm_requires_action():
    r = PublisherTDMResolver()
    result = r.resolve(ResolveContext(doi="10.1/test"))
    assert result.success
    assert result.requires_user_action is True
    assert "register_manual_pdf" in result.action_hint


def test_build_resolvers_oa_only():
    policy = AccessPolicy(mode=AccessMode.OA_ONLY)
    resolvers = _build_resolvers(policy)
    names = [r.name for r in resolvers]
    assert "unpaywall" in names
    assert "publisher_tdm" not in names
    assert "browser_assisted" not in names


def test_build_resolvers_institutional():
    policy = AccessPolicy(mode=AccessMode.INSTITUTIONAL)
    resolvers = _build_resolvers(policy)
    names = [r.name for r in resolvers]
    assert "publisher_tdm" in names
    assert "institutional_browser" in names


@patch("src.fetch.fetch_pipeline._build_resolvers")
def test_fetch_oa_pdf_calls_fetch_pdf(mock_build):
    """fetch_oa_pdf 仍可正常工作（mock resolver 返回）。"""
    result = fetch_oa_pdf("10.1/test", dry_run=True)
    assert result.error
