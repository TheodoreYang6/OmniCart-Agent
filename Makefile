# OmniCart Agent — 常用命令收敛（对齐 amap 的工程化工具链）
# 用法：make <target>。PY 可覆盖：make test PY=python3.11

PY ?= python
PORT ?= 8006

.PHONY: help install lint fmt test test-unit smoke run governance registry

help:
	@echo "install    安装依赖 + 开发工具(ruff/pytest)"
	@echo "lint       ruff 门禁（framework/providers/config）"
	@echo "fmt        ruff 自动格式化 + 修复"
	@echo "test       跑单元测试（tests/unit + backend/tests/unit）"
	@echo "smoke      MOCK 模式起服务（Ctrl-C 停）"
	@echo "run        本地起服务（--reload）"
	@echo "governance 组件治理校验"
	@echo "registry   生成组件注册表 docs/COMPONENT_REGISTRY.md"

install:
	$(PY) -m pip install -r requirements.txt
	$(PY) -m pip install ruff pytest pytest-asyncio pytest-cov

lint:
	ruff check backend/app/framework backend/app/providers backend/app/core/config.py
	ruff format --check backend/app/framework backend/app/providers backend/app/core/config.py

fmt:
	ruff check --fix backend/app/framework backend/app/providers
	ruff format backend/app/framework backend/app/providers backend/app/model_gateway backend/app/core/config.py

test: test-unit

test-unit:
	pytest tests/unit backend/tests/unit -v

smoke:
	cd backend && OMNICART_MOCK_MODE=true $(PY) -m uvicorn app.main:app --host 127.0.0.1 --port $(PORT)

run:
	cd backend && $(PY) -m uvicorn app.main:app --host 127.0.0.1 --port $(PORT) --reload

governance:
	PYTHONPATH=backend $(PY) scripts/check_governance.py

registry:
	PYTHONPATH=backend $(PY) scripts/gen_component_registry.py
