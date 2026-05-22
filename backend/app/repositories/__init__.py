"""Repositories 包 — 导出工厂函数和实现类。"""

from app.repositories.product_repo import ProductRepository, get_product_repo
from app.repositories.base_product_repo import BaseProductRepository
from app.repositories.json_product_repo import JsonProductRepository
from app.repositories.pg_product_repo import PgProductRepository
from app.repositories.vector_repo import VectorRepository, get_vector_repo
from app.repositories.base_vector_repo import BaseVectorRepository
from app.repositories.stub_vector_repo import StubVectorRepository
from app.repositories.qdrant_vector_repo import QdrantVectorRepository
from app.repositories.pg_cart_repo import (
    PgCartRepository,
    MemCartRepository,
    get_cart_repo,
)
from app.repositories.pg_preference_repo import (
    PgPreferenceRepository,
    MemPreferenceRepository,
    get_preference_repo,
)
from app.repositories.user_repo import (
    PgUserRepository,
    MemUserRepository,
    get_user_repo,
)
from app.repositories.address_repo import (
    PgAddressRepository,
    MemAddressRepository,
    get_address_repo,
)

__all__ = [
    "get_product_repo",
    "ProductRepository",
    "BaseProductRepository",
    "JsonProductRepository",
    "PgProductRepository",
    "get_vector_repo",
    "VectorRepository",
    "BaseVectorRepository",
    "StubVectorRepository",
    "QdrantVectorRepository",
    "get_cart_repo",
    "PgCartRepository",
    "MemCartRepository",
    "get_preference_repo",
    "PgPreferenceRepository",
    "MemPreferenceRepository",
    "get_user_repo",
    "PgUserRepository",
    "MemUserRepository",
    "get_address_repo",
    "PgAddressRepository",
    "MemAddressRepository",
]
