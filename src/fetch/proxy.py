"""共享的 fetch 代理配置解析。

把原本散落在 ``fetch_scihub.py`` / ``tdm_resolvers.py`` 里的代理构造逻辑集中到一处，
让合法的 TDM / publisher resolver 不必再语义上依赖 Sci-Hub 模块。

语义：
- 读取项目已有的代理环境变量/配置 ``config.settings.FETCH_PROXY``；
- 返回 ``requests`` 可用的 ``proxies`` dict，或 ``None``（直连）；
- 不依赖 Sci-Hub，也不引入新的第三方依赖。
"""
from __future__ import annotations

from config.settings import FETCH_PROXY


def get_fetch_proxies() -> dict | None:
    """返回 ``requests`` 可用的 proxies dict，无配置时返回 ``None``（直连）。

    读取 ``FETCH_PROXY``（形如 ``http://127.0.0.1:7890``），同时映射到
    ``http`` 与 ``https`` scheme。空值视为未配置，返回 ``None``。
    """
    if FETCH_PROXY:
        return {"http": FETCH_PROXY, "https": FETCH_PROXY}
    return None
