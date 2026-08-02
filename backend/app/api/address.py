"""Address API — 收货地址 CRUD。"""

from fastapi import APIRouter, HTTPException

from app.schemas.address import AddressCreate, AddressUpdate
from app.schemas.cart import DEMO_USER_ID
from app.repositories.address_repo import get_address_repo

router = APIRouter()


def _uid(uid: str) -> str:
    return uid if uid and uid.strip() else DEMO_USER_ID


@router.get("/api/addresses")
async def list_addresses(user_id: str = DEMO_USER_ID):
    repo = get_address_repo()
    return {"addresses": repo.list(_uid(user_id))}


@router.post("/api/addresses")
async def create_address(req: AddressCreate, user_id: str = DEMO_USER_ID):
    repo = get_address_repo()
    # P1-1: body 里的 user_id 优先（此前被静默丢弃→写到 demo 用户名下）；query 参数向后兼容
    effective_uid = _uid(req.user_id or user_id)
    data = req.model_dump(exclude={"user_id"})
    result = repo.create(effective_uid, data)
    if result is None:
        raise HTTPException(status_code=500, detail="failed to create address")
    return result


@router.put("/api/addresses/{address_id}")
async def update_address(address_id: str, req: AddressUpdate, user_id: str = DEMO_USER_ID):
    repo = get_address_repo()
    effective_uid = _uid(req.user_id or user_id)
    data = {k: v for k, v in req.model_dump(exclude={"user_id"}).items() if v is not None}
    result = repo.update(address_id, effective_uid, data)
    if result is None:
        raise HTTPException(status_code=404, detail="address not found")
    return result


@router.delete("/api/addresses/{address_id}")
async def delete_address(address_id: str, user_id: str = DEMO_USER_ID):
    repo = get_address_repo()
    ok = repo.delete(address_id, _uid(user_id))
    if not ok:
        raise HTTPException(status_code=404, detail="address not found")
    return {"ok": True}
