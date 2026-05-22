"""Address API — 收货地址 CRUD。"""

from fastapi import APIRouter, HTTPException

from app.schemas.address import AddressCreate, AddressUpdate
from app.schemas.cart import DEMO_USER_ID
from app.repositories.address_repo import get_address_repo

router = APIRouter()


@router.get("/api/addresses")
async def list_addresses(user_id: str = DEMO_USER_ID):
    repo = get_address_repo()
    return {"addresses": repo.list(user_id)}


@router.post("/api/addresses")
async def create_address(req: AddressCreate, user_id: str = DEMO_USER_ID):
    repo = get_address_repo()
    data = req.model_dump()
    result = repo.create(user_id, data)
    if result is None:
        raise HTTPException(status_code=500, detail="failed to create address")
    return result


@router.put("/api/addresses/{address_id}")
async def update_address(address_id: str, req: AddressUpdate, user_id: str = DEMO_USER_ID):
    repo = get_address_repo()
    data = {k: v for k, v in req.model_dump().items() if v is not None}
    result = repo.update(address_id, user_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="address not found")
    return result


@router.delete("/api/addresses/{address_id}")
async def delete_address(address_id: str, user_id: str = DEMO_USER_ID):
    repo = get_address_repo()
    ok = repo.delete(address_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="address not found")
    return {"ok": True}
