"""配置中心单测（core.config）—— 验证 pydantic-settings 解析 + 向后兼容扁平 re-export。

测试环境由 tests/conftest.py 预置：DATABASE_URL / QDRANT_URL / REDIS_URL 均为空、
OMNICART_MOCK_MODE=true。
"""

from __future__ import annotations


def test_settings_flat_reexports_match_grouped():
    import app.core.config as cfg

    # 扁平常量 == 分组字段（向后兼容层正确）
    assert cfg.SERVICE_NAME == cfg.settings.service_name
    assert cfg.SERVICE_VERSION == cfg.settings.service_version
    assert cfg.MOCK_MODE == cfg.settings.mock_mode
    assert cfg.QWEN_BASE_URL == cfg.settings.qwen_base_url
    assert cfg.EMBEDDING_DIMENSION == cfg.settings.embedding_dimension
    assert cfg.USE_POSTGRES == cfg.settings.use_postgres
    assert cfg.USE_QDRANT == cfg.settings.use_qdrant
    assert cfg.USE_REDIS == cfg.settings.use_redis


def test_settings_types_parsed():
    import app.core.config as cfg

    assert isinstance(cfg.PORT, int)
    assert isinstance(cfg.DEFAULT_TOP_K, int)
    assert isinstance(cfg.DECISION_LLM_TIMEOUT, float)
    assert isinstance(cfg.MOCK_MODE, bool)
    for name in [
        "REDIS_CACHE_TTL_VISUAL",
        "REDIS_CACHE_TTL_SEARCH",
        "REDIS_CACHE_TTL_REWRITE",
        "REDIS_CACHE_TTL_WORKFLOW",
    ]:
        assert isinstance(getattr(cfg, name), int)


def test_settings_derived_flags_defaults():
    # DATABASE_URL / QDRANT_URL 默认空 → 派生开关 False（不依赖 conftest）
    import app.core.config as cfg

    assert cfg.settings.use_postgres is False
    assert cfg.settings.use_qdrant is False
    # 默认值
    assert cfg.SERVICE_NAME == "omnicart-agent"
    assert cfg.MOCK_MODE is True
