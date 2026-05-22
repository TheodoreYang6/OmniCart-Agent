"""Address API 单元测试。"""
import pytest
from app.repositories.address_repo import MemAddressRepository


class TestMemAddressRepo:
    def setup_method(self):
        self.repo = MemAddressRepository()

    def test_create(self):
        r = self.repo.create("u1", {"name": "张三", "phone": "13800001111",
                                     "province": "北京", "city": "北京",
                                     "district": "朝阳", "detail": "xxx路1号"})
        assert r["address_id"].startswith("addr_")
        assert r["name"] == "张三"
        assert r["is_default"] is False

    def test_list_by_user(self):
        self.repo.create("u1", {"name": "张三", "phone": "138"})
        self.repo.create("u2", {"name": "李四", "phone": "139"})
        assert len(self.repo.list("u1")) == 1
        assert len(self.repo.list("u2")) == 1
        assert len(self.repo.list("u3")) == 0

    def test_update(self):
        r = self.repo.create("u1", {"name": "张三", "phone": "138"})
        u = self.repo.update(r["address_id"], "u1", {"name": "张三改", "phone": "139"})
        assert u["name"] == "张三改"
        assert u["phone"] == "139"

    def test_update_wrong_user(self):
        r = self.repo.create("u1", {"name": "张三", "phone": "138"})
        u = self.repo.update(r["address_id"], "u2", {"name": "hack"})
        assert u is None

    def test_delete(self):
        r = self.repo.create("u1", {"name": "张三", "phone": "138"})
        assert self.repo.delete(r["address_id"], "u1")
        assert len(self.repo.list("u1")) == 0

    def test_delete_wrong_user(self):
        r = self.repo.create("u1", {"name": "张三", "phone": "138"})
        assert not self.repo.delete(r["address_id"], "u2")

    def test_delete_nonexistent(self):
        assert not self.repo.delete("bad_id", "u1")

    def test_set_default_clears_old(self):
        r1 = self.repo.create("u1", {"name": "A", "phone": "1", "is_default": True})
        r2 = self.repo.create("u1", {"name": "B", "phone": "2", "is_default": True})
        a1 = self.repo._store[r1["address_id"]]
        a2 = self.repo._store[r2["address_id"]]
        assert a1["is_default"] is False
        assert a2["is_default"] is True

    def test_update_set_default(self):
        r1 = self.repo.create("u1", {"name": "A", "phone": "1", "is_default": True})
        r2 = self.repo.create("u1", {"name": "B", "phone": "2"})
        self.repo.update(r2["address_id"], "u1", {"is_default": True})
        assert self.repo._store[r1["address_id"]]["is_default"] is False
        assert self.repo._store[r2["address_id"]]["is_default"] is True
