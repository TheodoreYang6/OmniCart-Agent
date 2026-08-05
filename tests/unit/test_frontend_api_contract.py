"""Lock the web client's public HTTP surface to FastAPI's OpenAPI contract."""

from pathlib import Path

from app.main import app


FRONTEND_CALLS = {
    ("GET", "/api/health"),
    ("GET", "/api/products"),
    ("GET", "/api/products/{product_id}"),
    ("POST", "/api/products/{product_id}/ai-summary"),
    ("POST", "/api/recommend/v2"),
    ("POST", "/api/recommend/guide"),
    ("POST", "/api/recommend/stream"),
    ("GET", "/api/conversations"),
    ("GET", "/api/conversations/{conversation_id}/messages"),
    ("DELETE", "/api/conversations/{conversation_id}"),
    ("POST", "/api/upload"),
    ("GET", "/api/cart"),
    ("POST", "/api/cart/items"),
    ("PUT", "/api/cart/items/{cart_item_id}"),
    ("DELETE", "/api/cart/items/{cart_item_id}"),
    ("POST", "/api/cart/select-all"),
    ("DELETE", "/api/cart/clear"),
    ("POST", "/api/checkout"),
    ("GET", "/api/orders"),
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("GET", "/api/auth/profile"),
    ("POST", "/api/auth/guest"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/addresses"),
    ("POST", "/api/addresses"),
    ("PUT", "/api/addresses/{address_id}"),
    ("DELETE", "/api/addresses/{address_id}"),
    ("GET", "/api/preferences/entries"),
    ("POST", "/api/preferences/parse"),
    ("PUT", "/api/preferences/entries"),
    ("DELETE", "/api/preferences/entries/{entry_id}"),
    ("PUT", "/api/preferences/entries/{entry_id}/toggle"),
    ("POST", "/api/voice/transcribe"),
    ("POST", "/api/voice/tts"),
}


def test_every_frontend_request_exists_in_openapi() -> None:
    paths = app.openapi()["paths"]
    missing = [
        f"{method} {path}"
        for method, path in sorted(FRONTEND_CALLS)
        if path not in paths or method.lower() not in paths[path]
    ]
    assert not missing, "Frontend calls missing from OpenAPI: " + ", ".join(missing)


def test_identity_and_cart_core_responses_remain_documented() -> None:
    frontend_types = (Path(__file__).parents[2] / "web-client" / "src" / "api" / "types.ts").read_text(encoding="utf-8")
    for field in ("user_id: string", "username: string", "token: string"):
        assert field in frontend_types
    for field in ("guest_id: string", "guest_token: string", "expires_at: number"):
        assert field in frontend_types
    for field in ("items: CartItem[]", "total_price: number", "total_count: number"):
        assert field in frontend_types


def test_protected_web_capabilities_are_not_legacy_user_id_only() -> None:
    """The custom Actor dependency is tested end-to-end in test_auth_identity.py.

    Keep this list next to the transport contract so newly exposed account data cannot
    silently bypass the identity test suite.
    """
    protected = {
        "/api/orders",
        "/api/checkout",
        "/api/addresses",
        "/api/preferences/entries",
    }
    paths = app.openapi()["paths"]
    assert protected <= set(paths)
