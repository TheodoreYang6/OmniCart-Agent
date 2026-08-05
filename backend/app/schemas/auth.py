"""Auth Schemas — 登录/注册/用户信息。"""

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=32)
    password: str = Field(..., min_length=8, max_length=64)
    email: str = ""
    phone: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    user_id: str
    username: str
    token: str
    email: str = ""
    phone: str = ""
    avatar_url: str = ""


class UserProfile(BaseModel):
    user_id: str
    username: str
    email: str = ""
    phone: str = ""
    avatar_url: str = ""
