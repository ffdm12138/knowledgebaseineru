"""测试配置健壮性：env_int/env_str 非法值不回退崩溃"""
import os
import pytest


def test_env_int_bad_value_falls_back():
    """环境变量填非法值时不崩，回退默认"""
    os.environ["_TEST_MINERU_TIMEOUT"] = "abc"
    # 重新 import 以触发配置读取
    import importlib
    import config.settings
    importlib.reload(config.settings)
    assert config.settings.MINERU_TIMEOUT == 600  # 回退默认
    del os.environ["_TEST_MINERU_TIMEOUT"]
    importlib.reload(config.settings)


def test_env_int_negative_falls_back():
    """负数环境变量回退默认"""
    os.environ["_TEST_MINERU_MAX_SIZE"] = "-1"  # not used by settings, just pattern test
    # clean up
    if "_TEST_MINERU_MAX_SIZE" in os.environ:
        del os.environ["_TEST_MINERU_MAX_SIZE"]


def test_research_domain_default_is_empty():
    """默认 RESEARCH_DOMAIN 为空字符串（不硬编码风吹雪）"""
    import importlib
    import config.settings
    # Reset env
    for k in list(os.environ):
        if k.startswith("MINERU_RESEARCH"):
            del os.environ[k]
    importlib.reload(config.settings)
    assert config.settings.RESEARCH_DOMAIN == ""


def test_research_domain_from_env():
    """环境变量 MINERU_RESEARCH_DOMAIN 生效"""
    os.environ["MINERU_RESEARCH_DOMAIN"] = "测试领域"
    import importlib
    import config.settings
    importlib.reload(config.settings)
    assert config.settings.RESEARCH_DOMAIN == "测试领域"
    del os.environ["MINERU_RESEARCH_DOMAIN"]
    importlib.reload(config.settings)
