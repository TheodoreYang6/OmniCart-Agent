"""Authentication API with cookie-based web sessions and Bearer compatibility."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.config import settings
from app.core.identity import (
    Actor,
    GUEST_COOKIE,
    SESSION_COOKIE,
    create_guest_identity,
    resolve_actor,
)
from app.repositories.pg_cart_repo import get_cart_repo
from app.repositories.user_repo import get_user_repo
from app.schemas.auth import LoginRequest, RegisterRequest

router = APIRouter()


def _cookie_options() -> dict:
    return {
        "httponly": True,
        "secure": settings.session_cookie_secure,
        "samesite": "lax",
        "path": "/",
    }


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=settings.guest_ttl_days * 86400, **_cookie_options()
    )
    response.delete_cookie(GUEST_COOKIE, path="/", samesite="lax")


def _set_guest_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        GUEST_COOKIE, token, max_age=settings.guest_ttl_days * 86400, **_cookie_options()
    )


def _finish_login(result: dict, response: Response, guest_actor: Actor | None) -> dict:
    merged_count = 0
    if guest_actor and guest_actor.kind == "guest":
        merged_count = get_cart_repo().merge_cart(guest_actor.user_id, result["user_id"])
    _set_session_cookie(response, result["token"])
    return {**result, "cart_merged_count": merged_count}


@router.post("/api/auth/guest")
async def guest(response: Response):
    actor, token, expires_at = create_guest_identity()
    _set_guest_cookie(response, token)
    return {"guest_id": actor.user_id, "guest_token": token, "expires_at": expires_at}


@router.post("/api/auth/register")
async def register(req: RegisterRequest, response: Response, request: Request):
    repo = get_user_repo()
    result = repo.register(req.username.strip(), req.password, req.email.strip(), req.phone.strip())
    if result is None:
        raise HTTPException(status_code=409, detail="username already exists")
    guest_actor = None
    guest_token = request.cookies.get(GUEST_COOKIE, "")
    if guest_token:
        from app.core.identity import verify_guest_token
        guest_actor = verify_guest_token(guest_token)
    return _finish_login(result, response, guest_actor)


@router.post("/api/auth/login")
async def login(req: LoginRequest, response: Response, request: Request):
    repo = get_user_repo()
    result = repo.login(req.username.strip(), req.password)
    if result is None:
        raise HTTPException(status_code=401, detail="invalid username or password")
    guest_actor = None
    guest_token = request.cookies.get(GUEST_COOKIE, "")
    if guest_token:
        from app.core.identity import verify_guest_token
        guest_actor = verify_guest_token(guest_token)
    return _finish_login(result, response, guest_actor)


@router.post("/api/auth/logout")
async def logout(response: Response, actor: Actor = Depends(resolve_actor)):
    if actor.is_authenticated:
        get_user_repo().revoke_token(actor.token)
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")
    guest_actor, guest_token, expires_at = create_guest_identity()
    _set_guest_cookie(response, guest_token)
    return {
        "ok": True,
        "guest_id": guest_actor.user_id,
        "guest_token": guest_token,
        "expires_at": expires_at,
    }


@router.get("/api/auth/profile")
async def profile(actor: Actor = Depends(resolve_actor)):
    if not actor.is_authenticated:
        raise HTTPException(status_code=401, detail="login required")
    user = get_user_repo().get_by_token(actor.token)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid token")
    return user
