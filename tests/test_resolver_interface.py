"""resolver 接口测试（全部 mock，不访问网络）。"""
from unittest.mock import patch
from types import SimpleNamespace

import pytest
from src.fetch.access_policy import AccessMode, AccessPolicy
from src.fetch.fetch_pipeline import fetch_oa_pdf
from src.fetch.resolver_registry import build_resolvers
from src.fetch.resolvers.base import ResolveContext
from src.fetch.resolvers.custom_resolvers import ExternalCommandResolver
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


def testbuild_resolvers_oa_only():
    policy = AccessPolicy(mode=AccessMode.OA_ONLY)
    resolvers = build_resolvers(policy)
    names = [r.name for r in resolvers]
    assert "unpaywall" in names
    assert "publisher_tdm" not in names
    assert "browser_assisted" not in names


def testbuild_resolvers_institutional():
    policy = AccessPolicy(mode=AccessMode.INSTITUTIONAL)
    resolvers = build_resolvers(policy)
    names = [r.name for r in resolvers]
    assert "publisher_tdm" in names
    assert "institutional_browser" in names


def test_scihub_resolver_import_path_invokes_resolver(monkeypatch):
    from src.fetch import fetch_scihub

    monkeypatch.setattr(
        fetch_scihub,
        "resolve_scihub",
        lambda doi: FetchResult(doi=doi, success=True, source="scihub", pdf_url="https://x/p.pdf"),
    )
    policy = AccessPolicy(mode=AccessMode.CUSTOM, allow_scihub=True)
    scihub = next(r for r in build_resolvers(policy) if r.name == "scihub")
    result = scihub.resolve(ResolveContext(doi="10.1/test"))
    assert result.success is True
    assert result.source == "scihub"


def test_custom_resolver_builds_from_policy_extra():
    policy = AccessPolicy(
        mode=AccessMode.CUSTOM,
        allow_custom_resolvers=True,
        custom_resolvers=["custom"],
        extra={"custom_command_argv": ["resolver.exe", "--doi", "{doi}"]},
    )
    custom = next(r for r in build_resolvers(policy) if r.name == "custom")
    assert custom.command_argv == ["resolver.exe", "--doi", "{doi}"]


def test_custom_resolver_uses_argv_without_shell(monkeypatch, tmp_path):
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(b"%PDF-1.4 custom")
    calls = {}

    def fake_run(args, **kwargs):
        calls["args"] = args
        calls["shell"] = kwargs.get("shell")
        return SimpleNamespace(
            returncode=0,
            stdout='{"success": true, "pdf_path": "' + str(pdf).replace("\\", "\\\\") + '"}',
            stderr="",
        )

    monkeypatch.setattr("src.fetch.resolvers.custom_resolvers.subprocess.run", fake_run)
    resolver = ExternalCommandResolver(["resolver.exe", "--doi", "{doi}"])
    result = resolver.resolve(ResolveContext(
        doi='10.1/x"; del *',
        metadata={"allowed_output_dir": str(tmp_path)},
    ))
    assert result.success is True
    assert calls["shell"] is False
    assert calls["args"] == ["resolver.exe", "--doi", '10.1/x"; del *']


def test_custom_resolver_rejects_invalid_output_path(tmp_path):
    resolver = ExternalCommandResolver(["resolver.exe"])
    outside = tmp_path.parent / "outside.pdf"
    outside.write_bytes(b"%PDF-1.4 outside")

    completed = SimpleNamespace(
        returncode=0,
        stdout='{"pdf_path": "' + str(outside).replace("\\", "\\\\") + '"}',
        stderr="",
    )
    with patch("src.fetch.resolvers.custom_resolvers.subprocess.run", return_value=completed):
        result = resolver.resolve(ResolveContext(
            doi="10.1/x",
            metadata={"allowed_output_dir": str(tmp_path)},
        ))
    assert result.success is False
    assert "outside allowed directory" in result.error


def test_custom_resolver_missing_command_is_clear():
    result = ExternalCommandResolver().resolve(ResolveContext(doi="10.1/x"))
    assert result.success is False
    assert "not configured" in result.error


class FakeResolver:
    """不访问网络的假 resolver，返回 mock 结果。"""
    name = "fake_no_pdf"

    def resolve(self, ctx):
        return FetchResult(doi=ctx.doi, success=False, error="mock no pdf")

    def enabled(self, policy):
        return True


@patch("src.fetch.fetch_pipeline._build_resolvers")
def test_fetch_oa_pdf_calls_fetch_pdf(mock_build):
    """fetch_oa_pdf 在 dry_run 下走完 resolver chain，不访问网络。"""
    mock_build.return_value = [FakeResolver()]
    result = fetch_oa_pdf("10.1/test", dry_run=True)
    assert result.error
