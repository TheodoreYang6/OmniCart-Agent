"""Signed guest identities and authenticated actor resolution.

The web client uses HttpOnly cookies while native clients may keep sending the
existing Bearer token.  Request-provided ``user_id`` values are compatibility
metadata only and are never trusted unless the explicit legacy flag is on.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from fastapi import Header, HTTPException, Query, Request

from app.core.config import settings
from app.repositories.user_repo import get_user_repo

SESSION_COOKIE = "omnicart_session"
GUEST_COOKIE = "omnicart_guest"


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: str
    kind: str
    token: str = ""
    username: str = ""

    @property
    def is_authenticated(self) -> bool:
        return self.kind == "user"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_guest_identity() -> tuple[Actor, str, int]:
    now = int(time.time())
    expires_at = now + max(1, settings.guest_ttl_days) * 86400
    guest_id = f"guest_{secrets.token_hex(12)}"
    payload = _b64encode(json.dumps(
        {"sub": guest_id, "kind": "guest", "iat": now, "exp": expires_at},
        separators=(",", ":"),
    ).encode("utf-8"))
    signature = _b64encode(hmac.new(
        settings.session_secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256,
    ).digest())
    token = f"{payload}.{signature}"
    return Actor(guest_id, "guest", token=token), token, expires_at


def verify_guest_token(token: str) -> Actor | None:
    try:
        payload, signature = token.split(".", 1)
        expected = _b64encode(hmac.new(
            settings.session_secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256,
        ).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(_b64decode(payload))
        if data.get("kind") != "guest" or int(data.get("exp", 0)) <= int(time.time()):
            return None
        guest_id = str(data.get("sub", ""))
        if not guest_id.startswith("guest_"):
            return None
        return Actor(guest_id, "guest", token=token)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


async def resolve_actor(
    request: Request,
    authorization: str = Header(default=""),
    x_guest_token: str = Header(default="", alias="X-Guest-Token"),
    legacy_user_id: str = Query(default="", alias="user_id"),
) -> Actor:
    bearer = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    session_token = request.cookies.get(SESSION_COOKIE, "")
    for token in (bearer, session_token):
        if not token:
            continue
        user = get_user_repo().get_by_token(token)
        if user:
            return Actor(
                user_id=str(user["user_id"]), kind="user", token=token,
                username=str(user.get("username", "")),
            )

    guest_token = x_guest_token or request.cookies.get(GUEST_COOKIE, "")
    if guest_token:
        guest = verify_guest_token(guest_token)
        if guest:
            return guest
        raise HTTPException(status_code=401, detail="invalid or expired guest identity")

    if settings.allow_legacy_user_id and legacy_user_id.strip():
        return Actor(legacy_user_id.strip(), "legacy")
    raise HTTPException(status_code=401, detail="identity required")


async def resolve_public_actor(
    request: Request,
    authorization: str = Header(default=""),
    x_guest_token: str = Header(default="", alias="X-Guest-Token"),
    legacy_user_id: str = Query(default="", alias="user_id"),
) -> Actor:
    """Resolve an actor for public browse/chat endpoints.

    Credential-free callers receive an isolated request-scoped guest. A supplied
    ``user_id`` remains untrusted, while invalid explicit credentials fail closed.
    """
    has_explicit_identity = bool(
        authorization.strip()
        or x_guest_token.strip()
        or request.cookies.get(SESSION_COOKIE)
        or request.cookies.get(GUEST_COOKIE)
    )
    try:
        return await resolve_actor(request, authorization, x_guest_token, legacy_user_id)
    except HTTPException:
        if has_explicit_identity:
            raise
        return Actor(user_id=f"guest_anon_{secrets.token_hex(12)}", kind="guest")


def require_user(actor: Actor) -> Actor:
    if not actor.is_authenticated:
        raise HTTPException(status_code=401, detail="login required")
    return actor


def actor_or_legacy(actor: object, legacy_user_id: str, *, protected: bool = False) -> Actor:
    """Compatibility helper for tests that call route functions directly."""
    if isinstance(actor, Actor):
        return require_user(actor) if protected else actor
    uid = (legacy_user_id or "").strip()
    if uid:
        # Direct function calls in legacy unit tests never pass through FastAPI's
        # dependency injection. HTTP requests always receive a real Actor above.
        return Actor(uid, "legacy")
    raise HTTPException(status_code=401, detail="identity required")
