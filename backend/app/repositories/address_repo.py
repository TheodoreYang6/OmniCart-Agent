"""地址仓库 — PostgreSQL 持久化 + 内存降级。"""

import logging
import uuid
from typing import Optional

from sqlalchemy import select, delete

from app.core.database import get_session_sync, run_async
from app.models.address import AddressModel

logger = logging.getLogger(__name__)


class PgAddressRepository:
    """PostgreSQL 地址仓库。"""


    async def _alist(self, user_id: str) -> list[dict]:
        factory = get_session_sync()
        if factory is None:
            return []
        async with factory() as session:
            result = await session.execute(
                select(AddressModel).where(AddressModel.user_id == user_id)
            )
            rows = result.scalars().all()
            return [_row_to_dict(r) for r in rows]

    async def _acreate(self, user_id: str, data: dict) -> Optional[dict]:
        factory = get_session_sync()
        if factory is None:
            return None
        address_id = f"addr_{uuid.uuid4().hex[:12]}"
        async with factory() as session:
            addr = AddressModel(user_id=user_id, address_id=address_id, **data)
            session.add(addr)
            if data.get("is_default"):
                await self._aclear_default(session, user_id, address_id)
            await session.commit()
            return _row_to_dict(addr)

    async def _aupdate(self, address_id: str, user_id: str, data: dict) -> Optional[dict]:
        factory = get_session_sync()
        if factory is None:
            return None
        async with factory() as session:
            result = await session.execute(
                select(AddressModel).where(
                    AddressModel.address_id == address_id,
                    AddressModel.user_id == user_id,
                )
            )
            addr = result.scalars().first()
            if not addr:
                return None
            for k, v in data.items():
                if v is not None:
                    setattr(addr, k, v)
            if data.get("is_default"):
                await self._aclear_default(session, user_id, address_id)
            await session.commit()
            return _row_to_dict(addr)

    async def _adelete(self, address_id: str, user_id: str) -> bool:
        factory = get_session_sync()
        if factory is None:
            return False
        async with factory() as session:
            result = await session.execute(
                delete(AddressModel).where(
                    AddressModel.address_id == address_id,
                    AddressModel.user_id == user_id,
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def _aclear_default(self, session, user_id: str, exclude_id: str):
        result = await session.execute(
            select(AddressModel).where(
                AddressModel.user_id == user_id,
                AddressModel.is_default == True,
                AddressModel.address_id != exclude_id,
            )
        )
        for row in result.scalars().all():
            row.is_default = False

    # ---- 同步接口 ----

    def list(self, user_id: str) -> list[dict]:
        return run_async(self._alist(user_id))

    def create(self, user_id: str, data: dict) -> Optional[dict]:
        return run_async(self._acreate(user_id, data))

    def update(self, address_id: str, user_id: str, data: dict) -> Optional[dict]:
        return run_async(self._aupdate(address_id, user_id, data))

    def delete(self, address_id: str, user_id: str) -> bool:
        return run_async(self._adelete(address_id, user_id))


def _row_to_dict(addr: AddressModel) -> dict:
    return {
        "address_id": addr.address_id,
        "user_id": addr.user_id,
        "name": addr.name,
        "phone": addr.phone,
        "province": addr.province or "",
        "city": addr.city or "",
        "district": addr.district or "",
        "detail": addr.detail or "",
        "is_default": addr.is_default,
    }


class MemAddressRepository:
    """内存地址仓库 — 降级实现。"""

    def __init__(self):
        self._store: dict[str, dict] = {}  # address_id → dict

    def list(self, user_id: str) -> list[dict]:
        return [a for a in self._store.values() if a["user_id"] == user_id]

    def create(self, user_id: str, data: dict) -> dict:
        address_id = f"addr_{uuid.uuid4().hex[:12]}"
        addr = {"address_id": address_id, "user_id": user_id,
                "is_default": data.get("is_default", False)}
        addr.update(data)
        if data.get("is_default"):
            for a in self._store.values():
                if a["user_id"] == user_id:
                    a["is_default"] = False
        self._store[address_id] = addr
        return dict(addr)

    def update(self, address_id: str, user_id: str, data: dict) -> Optional[dict]:
        addr = self._store.get(address_id)
        if not addr or addr["user_id"] != user_id:
            return None
        for k, v in data.items():
            if v is not None:
                addr[k] = v
        if data.get("is_default"):
            for a in self._store.values():
                if a["user_id"] == user_id and a["address_id"] != address_id:
                    a["is_default"] = False
        return dict(addr)

    def delete(self, address_id: str, user_id: str) -> bool:
        addr = self._store.get(address_id)
        if not addr or addr["user_id"] != user_id:
            return False
        del self._store[address_id]
        return True


# ---- 工厂 ----

_addr_repo: PgAddressRepository | MemAddressRepository | None = None


def get_address_repo() -> PgAddressRepository | MemAddressRepository:
    global _addr_repo
    if _addr_repo is None:
        from app.core.config import USE_POSTGRES
        if USE_POSTGRES:
            _addr_repo = PgAddressRepository()
        else:
            _addr_repo = MemAddressRepository()
    return _addr_repo
