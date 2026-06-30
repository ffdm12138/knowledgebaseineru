"""Resolver registry — 统一管理所有 PDF resolver 的注册和构建。

设计目标：
- 所有 resolver class 集中在 src/fetch/resolvers/。
- fetch_pipeline.py 不再有行内 bridge class。
- 新增 resolver 只需在 RESOLVER_REGISTRY 注册。
"""
from src.fetch.access_policy import AccessPolicy
from src.fetch.resolvers.browser_resolvers import BrowserAssistedResolver
from src.fetch.resolvers.custom_resolvers import ExternalCommandResolver
from src.fetch.resolvers.institutional_resolvers import (
    InstitutionalBrowserResolver,
    PublisherTDMResolver,
)
from src.fetch.resolvers.local_resolvers import LocalManualResolver
from src.fetch.resolvers.oa_resolvers import (
    ArxivResolver,
    OpenAlexResolver,
    PublisherOAResolver,
    SemanticScholarResolver,
    UnpaywallResolver,
)
from src.fetch.resolvers.preprint_resolvers import BiorxivResolver, PmcOaResolver
from src.fetch.resolvers.ref_downloader_bridge import RefDownloaderResolver
from src.fetch.resolvers.tdm_resolvers import (
    ElsevierTdmResolver,
    SpringerDirectResolver,
    WileyTdmResolver,
)
from src.fetch.resolvers.base import PdfResolver


class SciHubResolver(PdfResolver):
    """Sci-Hub resolver —— unsafe optional / 默认 disabled / 不属于 OA_ONLY 主流程。

    仅当 ``AccessMode.CUSTOM`` 且 ``allow_scihub=True`` 时才被启用；
    ``OA_ONLY`` 默认链路绝不包含 Sci-Hub。详见 ``access_policy.py``
    与 ``docs/DEPENDENCIES_AND_EXTERNAL_TOOLS.md``。
    """
    name = "scihub"
    access_modes = ("custom",)

    def resolve(self, ctx):
        from src.fetch.fetch_scihub import resolve_scihub
        return resolve_scihub(ctx.doi)


# ── 注册表 ────────────────────────────────────────

RESOLVER_REGISTRY: dict[str, type[PdfResolver]] = {
    # OA
    "unpaywall": UnpaywallResolver,
    "openalex": OpenAlexResolver,
    "semantic_scholar": SemanticScholarResolver,
    "arxiv": ArxivResolver,
    "publisher_oa": PublisherOAResolver,
    "springer_direct": SpringerDirectResolver,
    # Preprint / PMC
    "biorxiv": BiorxivResolver,
    "pmc_oa": PmcOaResolver,
    # TDM（需 token）
    "wiley_tdm": WileyTdmResolver,
    "elsevier_tdm": ElsevierTdmResolver,
    # Institutional
    "publisher_tdm": PublisherTDMResolver,
    "institutional_browser": InstitutionalBrowserResolver,
    # Browser assisted
    "browser_assisted": BrowserAssistedResolver,
    # Local
    "local_manual": LocalManualResolver,
    # Unsafe / non-OA
    "scihub": SciHubResolver,
    "custom": ExternalCommandResolver,
    # Bridge
    "ref_downloader": RefDownloaderResolver,
}


def build_resolvers(policy: AccessPolicy) -> list:
    """根据 access policy 构建 resolver 实例列表。"""
    resolvers = []
    for name in policy.enabled_resolver_names():
        cls = RESOLVER_REGISTRY.get(name)
        if cls:
            if cls is ExternalCommandResolver:
                argv = (policy.extra or {}).get("custom_command_argv") or []
                resolvers.append(cls(command_argv=argv))
            else:
                resolvers.append(cls())
    return resolvers
