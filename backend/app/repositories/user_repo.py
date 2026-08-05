"""用户仓库 — PostgreSQL 持久化 + 内存降级。"""

import hashlib
import logging
import secrets
import uuid
from typing import Optional

from sqlalchemy import select

from app.core.database import get_session_sync, run_async
from app.models.user import UserModel

logger = logging.getLogger(__name__)


def _hash_password(password: str) -> str:
    """PBKDF2-SHA256 密码哈希（内置库，无外部依赖）。"""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"pbkdf2:sha256:{salt}:{dk.hex()}"


def _verify_password(password: str, hash_str: str) -> bool:
    """验证密码。"""
    try:
        _, _, salt, stored = hash_str.split(":")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
        return dk.hex() == stored
    except (ValueError, AttributeError):
        return False


class PgUserRepository:
    """PostgreSQL 用户仓库。"""


    async def _aget_by_username(self, username: str) -> Optional[UserModel]:
        factory = get_session_sync()
        if factory is None:
            return None
        async with factory() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.username == username).limit(1)
            )
            return result.scalars().first()

    async def _aget_by_token(self, token: str) -> Optional[UserModel]:
        factory = get_session_sync()
        if factory is None:
            return None
        async with factory() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.token == token).limit(1)
            )
            return result.scalars().first()

    async def _acreate(self, username: str, password_hash: str, email: str = "",
                       phone: str = "") -> Optional[dict]:
        factory = get_session_sync()
        if factory is None:
            return None
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        token = secrets.token_hex(32)
        async with factory() as session:
            user = UserModel(
                user_id=user_id,
                username=username,
                password_hash=password_hash,
                email=email,
                phone=phone,
                token=token,
            )
            session.add(user)
            await session.commit()
            return {
                "user_id": user_id, "username": username, "token": token,
                "email": email, "phone": phone, "avatar_url": "",
            }

    # ---- 同步接口 ----

    def register(self, username: str, password: str, email: str = "",
                 phone: str = "") -> Optional[dict]:
        existing = run_async(self._aget_by_username(username))
        if existing:
            return None  # 用户名已存在
        return run_async(self._acreate(username, _hash_password(password), email, phone))

    def login(self, username: str, password: str) -> Optional[dict]:
        user = run_async(self._aget_by_username(username))
        if not user or not _verify_password(password, user.password_hash):
            return None
        # 刷新 token
        new_token = secrets.token_hex(32)
        user.token = new_token
        factory = get_session_sync()

        async def _save_token():
            async with factory() as session:
                u = await session.get(UserModel, user.user_id)
                u.token = new_token
                await session.commit()

        if factory:
            run_async(_save_token())
        return {
            "user_id": user.user_id, "username": user.username, "token": new_token,
            "email": user.email or "", "phone": user.phone or "",
            "avatar_url": user.avatar_url or "",
        }

    def get_by_token(self, token: str) -> Optional[dict]:
        user = run_async(self._aget_by_token(token))
        if not user:
            return None
        return {
            "user_id": user.user_id, "username": user.username,
            "email": user.email or "", "phone": user.phone or "",
            "avatar_url": user.avatar_url or "",
        }

    def revoke_token(self, token: str) -> bool:
        factory = get_session_sync()
        if factory is None or not token:
            return False

        async def _revoke():
            async with factory() as session:
                result = await session.execute(
                    select(UserModel).where(UserModel.token == token).limit(1)
                )
                user = result.scalars().first()
                if not user:
                    return False
                user.token = ""
                await session.commit()
                return True

        return bool(run_async(_revoke()))

    def get_by_id(self, user_id: str) -> Optional[dict]:
        factory = get_session_sync()
        if factory is None:
            return None

        async def _get():
            async with factory() as session:
                u = await session.get(UserModel, user_id)
                return u

        user = run_async(_get())
        if not user:
            return None
        return {
            "user_id": user.user_id, "username": user.username,
            "email": user.email or "", "phone": user.phone or "",
            "avatar_url": user.avatar_url or "",
        }


class MemUserRepository:
    """内存用户仓库 — 降级实现。"""

    def __init__(self):
        self._users: dict[str, dict] = {}   # username → user_dict
        self._by_token: dict[str, str] = {}  # token → username
        self._by_id: dict[str, str] = {}     # user_id → username

    def register(self, username: str, password: str, email: str = "",
                 phone: str = "") -> Optional[dict]:
        if username in self._users:
            return None
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        token = secrets.token_hex(32)
        user = {
            "user_id": user_id, "username": username,
            "password_hash": _hash_password(password),
            "email": email, "phone": phone, "avatar_url": "", "token": token,
        }
        self._users[username] = user
        self._by_token[token] = username
        self._by_id[user_id] = username
        return {
            "user_id": user_id, "username": username, "token": token,
            "email": email, "phone": phone, "avatar_url": "",
        }

    def login(self, username: str, password: str) -> Optional[dict]:
        user = self._users.get(username)
        if not user or not _verify_password(password, user["password_hash"]):
            return None
        new_token = secrets.token_hex(32)
        old_token = user.get("token", "")
        self._by_token.pop(old_token, None)
        user["token"] = new_token
        self._by_token[new_token] = username
        return {
            "user_id": user["user_id"], "username": username, "token": new_token,
            "email": user.get("email", ""), "phone": user.get("phone", ""),
            "avatar_url": user.get("avatar_url", ""),
        }

    def get_by_token(self, token: str) -> Optional[dict]:
        username = self._by_token.get(token)
        if not username:
            return None
        user = self._users.get(username)
        if not user:
            return None
        return {
            "user_id": user["user_id"], "username": username,
            "email": user.get("email", ""), "phone": user.get("phone", ""),
            "avatar_url": user.get("avatar_url", ""),
        }

    def revoke_token(self, token: str) -> bool:
        username = self._by_token.pop(token, None)
        if not username:
            return False
        user = self._users.get(username)
        if user:
            user["token"] = ""
        return True

    def get_by_id(self, user_id: str) -> Optional[dict]:
        username = self._by_id.get(user_id)
        if not username:
            return None
        user = self._users.get(username)
        if not user:
            return None
        return {
            "user_id": user["user_id"], "username": username,
            "email": user.get("email", ""), "phone": user.get("phone", ""),
            "avatar_url": user.get("avatar_url", ""),
        }


# ---- 工厂 ----

_user_repo: PgUserRepository | MemUserRepository | None = None


def get_user_repo() -> PgUserRepository | MemUserRepository:
    global _user_repo
    if _user_repo is None:
        from app.core.config import USE_POSTGRES
        if USE_POSTGRES:
            _user_repo = PgUserRepository()
        else:
            _user_repo = MemUserRepository()
    return _user_repo
