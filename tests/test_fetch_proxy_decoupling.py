"""代理解耦测试：确认 TDM resolver 不再语义依赖 Sci-Hub 模块。

不访问网络，不依赖本机代理环境变量。
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TDM_PATH = ROOT / "src" / "fetch" / "resolvers" / "tdm_resolvers.py"
SCIHUB_PATH = ROOT / "src" / "fetch" / "fetch_scihub.py"
PROXY_PATH = ROOT / "src" / "fetch" / "proxy.py"


def _imports_using_scihub_proxy(source: str) -> bool:
    """tdm_resolvers.py 是否仍从 fetch_scihub 导入 _get_proxies。"""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                if module == "src.fetch.fetch_scihub" and alias.name == "_get_proxies":
                    return True
    return False


def test_tdm_resolvers_do_not_import_scihub_proxy():
    src = TDM_PATH.read_text(encoding="utf-8")
    assert not _imports_using_scihub_proxy(src), (
        "tdm_resolvers.py 仍从 src.fetch.fetch_scihub 导入 _get_proxies，未解耦"
    )


def test_tdm_resolvers_use_shared_proxy():
    src = TDM_PATH.read_text(encoding="utf-8")
    assert "from src.fetch.proxy import get_fetch_proxies" in src
    assert "get_fetch_proxies()" in src
    # 不应残留对 Sci-Hub 模块代理函数的直接调用
    assert "_get_proxies()" not in src


def test_proxy_module_importable_and_returns_none_when_unset(monkeypatch):
    import src.fetch.proxy as proxy_mod

    # 不依赖本机代理环境：直接打桩 FETCH_PROXY
    monkeypatch.setattr(proxy_mod, "FETCH_PROXY", "", raising=False)
    assert proxy_mod.get_fetch_proxies() is None


def test_proxy_module_returns_dict_when_set(monkeypatch):
    import src.fetch.proxy as proxy_mod

    monkeypatch.setattr(proxy_mod, "FETCH_PROXY", "http://127.0.0.1:7890", raising=False)
    proxies = proxy_mod.get_fetch_proxies()
    assert proxies == {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}


def test_scihub_legacy_wrapper_delegates_to_proxy():
    """fetch_scihub 保留 _get_proxies 作为 legacy wrapper，但内部委托给 proxy 模块。"""
    src = SCIHUB_PATH.read_text(encoding="utf-8")
    assert "from src.fetch.proxy import get_fetch_proxies" in src
    assert "def _get_proxies" in src  # legacy wrapper 仍在
    assert "get_fetch_proxies()" in src


def test_scihub_not_in_oa_only():
    from src.fetch.access_policy import AccessMode, AccessPolicy

    enabled = AccessPolicy(mode=AccessMode.OA_ONLY).enabled_resolver_names()
    assert "scihub" not in enabled


def test_scihub_not_in_custom_when_allow_scihub_false():
    from src.fetch.access_policy import AccessMode, AccessPolicy

    enabled = AccessPolicy(mode=AccessMode.CUSTOM, allow_scihub=False).enabled_resolver_names()
    assert "scihub" not in enabled


def test_scihub_only_in_custom_when_allow_scihub_true():
    from src.fetch.access_policy import AccessMode, AccessPolicy

    enabled = AccessPolicy(mode=AccessMode.CUSTOM, allow_scihub=True).enabled_resolver_names()
    assert "scihub" in enabled
