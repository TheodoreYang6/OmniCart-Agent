"""Auth API — 用户登录/注册/个人信息。"""

from fastapi import APIRouter, Header, HTTPException

from app.schemas.auth import RegisterRequest, LoginRequest, AuthResponse, UserProfile
from app.repositories.user_repo import get_user_repo

router = APIRouter()


@router.post("/api/auth/register")
async def register(req: RegisterRequest):
    repo = get_user_repo()
    result = repo.register(req.username, req.password, req.email, req.phone)
    if result is None:
        raise HTTPException(status_code=409, detail="username already exists")
    return result


@router.post("/api/auth/login")
async def login(req: LoginRequest):
    repo = get_user_repo()
    result = repo.login(req.username, req.password)
    if result is None:
        raise HTTPException(status_code=401, detail="invalid username or password")
    return result


@router.get("/api/auth/profile")
async def profile(authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    if not token:
        raise HTTPException(status_code=401, detail="missing token")
    repo = get_user_repo()
    user = repo.get_by_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid token")
    return user
