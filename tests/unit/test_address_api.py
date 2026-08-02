"""P1-1 地址 API 数据隔离单测 —— body user_id 优先，不再静默写到 demo 用户。"""

from app.api.address import create_address, list_addresses
from app.schemas.address import AddressCreate


async def test_create_address_body_user_id_wins():
    req = AddressCreate(user_id="u_body_001", name="张三", phone="13800001111",
                        province="浙江", city="杭州", district="西湖", detail="路1号")
    res = await create_address(req, user_id="u_query_002")
    assert res["user_id"] == "u_body_001"


async def test_create_address_falls_back_to_query_param():
    req = AddressCreate(name="李四", phone="13900002222")
    res = await create_address(req, user_id="u_query_003")
    assert res["user_id"] == "u_query_003"


async def test_create_address_anonymous_falls_back_to_demo():
    from app.schemas.cart import DEMO_USER_ID

    req = AddressCreate(name="匿名", phone="13700003333")
    res = await create_address(req, user_id="")
    assert res["user_id"] == DEMO_USER_ID


async def test_list_addresses_isolated_per_user():
    req = AddressCreate(user_id="u_iso_a", name="A", phone="1")
    await create_address(req, user_id="")
    out_a = await list_addresses(user_id="u_iso_a")
    out_b = await list_addresses(user_id="u_iso_b")
    assert any(a["name"] == "A" for a in out_a["addresses"])
    assert not any(a["name"] == "A" for a in out_b["addresses"])
