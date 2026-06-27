"""PDF access policy — 控制启用哪些 resolver 后端。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AccessMode(str, Enum):
    OA_ONLY = "oa_only"
    INSTITUTIONAL = "institutional"
    BROWSER_ASSISTED = "browser_assisted"
    LOCAL_MANUAL = "local_manual"
    CUSTOM = "custom"


@dataclass
class AccessPolicy:
    """PDF 获取策略：控制启用哪些 resolver、超时、行为。"""

    mode: AccessMode = AccessMode.OA_ONLY
    allow_browser: bool = False
    allow_institutional: bool = False
    allow_publisher_tdm: bool = True
    allow_preprints: bool = True
    allow_manual_import: bool = True
    allow_custom_resolvers: bool = False
    custom_resolvers: list[str] = field(default_factory=list)
    max_attempts_per_resolver: int = 1
    timeout_seconds: int = 60
    user_agent: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def enabled_resolver_names(self) -> list[str]:
        """根据 mode 返回该策略下启用的 resolver 名称列表。"""
        if self.mode == AccessMode.OA_ONLY:
            return self._oa_resolvers()
        if self.mode == AccessMode.INSTITUTIONAL:
            return self._oa_resolvers() + self._institutional_resolvers()
        if self.mode == AccessMode.BROWSER_ASSISTED:
            return self._oa_resolvers() + ["browser_assisted"]
        if self.mode == AccessMode.LOCAL_MANUAL:
            return ["local_manual"]
        if self.mode == AccessMode.CUSTOM:
            base = self._oa_resolvers()
            if self.allow_custom_resolvers:
                base = base + list(self.custom_resolvers)
            return base
        return []

    @staticmethod
    def _oa_resolvers() -> list[str]:
        return ["unpaywall", "openalex", "semantic_scholar", "arxiv", "publisher_oa",
                "wiley_tdm", "springer_direct", "elsevier_tdm",
                "biorxiv", "pmc_oa", "scihub"]

    @staticmethod
    def _institutional_resolvers() -> list[str]:
        return ["publisher_tdm", "institutional_browser"]

    def clone_with(self, **overrides) -> AccessPolicy:
        kwargs = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        kwargs.update(overrides)
        return AccessPolicy(**kwargs)
