import pytest
from fastapi import HTTPException, Request

from app.core.identity import Actor, create_guest_identity, require_user, resolve_actor, verify_guest_token
from app.repositories.pg_cart_repo import MemCartRepository
from app.schemas.cart import CartItemCreate


def test_guest_token_is_signed_and_tamper_proof():
    actor, token, expires_at = create_guest_identity()
    verified = verify_guest_token(token)
    assert verified and verified.user_id == actor.user_id
    assert expires_at > 0
    assert verify_guest_token(token[:-1] + ("a" if token[-1] != "a" else "b")) is None


@pytest.mark.asyncio
async def test_forged_legacy_user_id_is_rejected(monkeypatch):
    monkeypatch.setattr("app.core.identity.settings.allow_legacy_user_id", False)
    request = Request({"type": "http", "headers": [], "method": "GET", "path": "/api/cart"})
    with pytest.raises(HTTPException) as exc:
        await resolve_actor(request, authorization="", x_guest_token="", legacy_user_id="victim")
    assert exc.value.status_code == 401


def test_guest_cannot_access_protected_resources():
    with pytest.raises(HTTPException) as exc:
        require_user(Actor("guest_test", "guest"))
    assert exc.value.status_code == 401


def test_guest_cart_merge_caps_quantity_and_clears_source():
    repo = MemCartRepository()
    item = CartItemCreate(product_id="P1", sku_id="S1", quantity=70)
    repo.add_item(item, "guest_1", title="商品")
    repo.add_item(item, "user_1", title="商品")
    assert repo.merge_cart("guest_1", "user_1") == 1
    assert repo.get_cart("guest_1").items == []
    assert repo.get_cart("user_1").items[0].quantity == 99
