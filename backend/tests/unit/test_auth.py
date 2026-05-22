"""Auth API 单元测试。"""
import pytest
from app.repositories.user_repo import MemUserRepository, _hash_password, _verify_password


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "test1234"
        h = _hash_password(pw)
        assert h.startswith("pbkdf2:sha256:")
        assert _verify_password(pw, h)
        assert not _verify_password("wrong", h)

    def test_different_salts(self):
        h1 = _hash_password("test")
        h2 = _hash_password("test")
        assert h1 != h2  # 不同盐值


class TestMemUserRepo:
    def setup_method(self):
        self.repo = MemUserRepository()

    def test_register_success(self):
        r = self.repo.register("alice", "pass1234", "a@b.com", "13800001111")
        assert r is not None
        assert r["username"] == "alice"
        assert r["user_id"].startswith("user_")
        assert len(r["token"]) == 64

    def test_register_duplicate(self):
        self.repo.register("alice", "pass1234")
        r2 = self.repo.register("alice", "other")
        assert r2 is None

    def test_login_success(self):
        self.repo.register("bob", "secret")
        r = self.repo.login("bob", "secret")
        assert r is not None
        assert r["username"] == "bob"
        assert len(r["token"]) == 64

    def test_login_wrong_password(self):
        self.repo.register("bob", "secret")
        assert self.repo.login("bob", "wrong") is None

    def test_login_nonexistent(self):
        assert self.repo.login("nobody", "pw") is None

    def test_get_by_token(self):
        r = self.repo.register("carol", "pw")
        token = r["token"]
        u = self.repo.get_by_token(token)
        assert u is not None
        assert u["username"] == "carol"

    def test_get_by_token_invalid(self):
        assert self.repo.get_by_token("bad_token") is None

    def test_get_by_id(self):
        r = self.repo.register("dave", "pw")
        u = self.repo.get_by_id(r["user_id"])
        assert u is not None
        assert u["username"] == "dave"

    def test_token_refresh_on_login(self):
        r1 = self.repo.register("eve", "pw")
        old_token = r1["token"]
        r2 = self.repo.login("eve", "pw")
        assert r2["token"] != old_token
        # 旧 token 失效
        assert self.repo.get_by_token(old_token) is None
        # 新 token 有效
        assert self.repo.get_by_token(r2["token"]) is not None

    def test_register_empty_email_phone(self):
        r = self.repo.register("frank", "pw")
        assert r["email"] == ""
        assert r["phone"] == ""
