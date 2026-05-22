"""Address Schemas。"""

from pydantic import BaseModel, Field


class AddressCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=32)
    phone: str = Field(..., min_length=1, max_length=20)
    province: str = ""
    city: str = ""
    district: str = ""
    detail: str = ""
    is_default: bool = False


class AddressUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    province: str | None = None
    city: str | None = None
    district: str | None = None
    detail: str | None = None
    is_default: bool | None = None


class AddressResponse(BaseModel):
    address_id: str
    user_id: str
    name: str
    phone: str
    province: str = ""
    city: str = ""
    district: str = ""
    detail: str = ""
    is_default: bool = False
