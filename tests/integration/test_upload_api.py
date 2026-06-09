"""Integration tests for POST /api/upload.

Run with: pytest tests/integration/test_upload_api.py -v
Requires backend running on 127.0.0.1:8006
"""

from pathlib import Path

import httpx
import pytest

BASE = "http://127.0.0.1:8006"


@pytest.fixture
def client():
    return httpx.Client(timeout=30.0, trust_env=False)


def test_upload_png(client):
    # 创建一个 1x1 像素的 PNG
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
        b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    resp = client.post(
        f"{BASE}/api/upload",
        files={"file": ("test.png", png_bytes, "image/png")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "file_id" in data
    assert "image_url" in data
    assert data["image_url"].startswith("/api/uploads/")
    assert data["content_type"] == "image/png"
    assert data["size_bytes"] == len(png_bytes)


def test_upload_rejects_text_file(client):
    resp = client.post(
        f"{BASE}/api/upload",
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400


def test_upload_too_large(client):
    # 超过 10MB
    big = b"x" * (11 * 1024 * 1024)
    resp = client.post(
        f"{BASE}/api/upload",
        files={"file": ("big.png", big, "image/png")},
    )
    assert resp.status_code in (400, 413)  # FastAPI/Starlette varies by version


def test_uploaded_image_accessible(client):
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
        b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    resp = client.post(
        f"{BASE}/api/upload",
        files={"file": ("test.png", png_bytes, "image/png")},
    )
    data = resp.json()
    # 验证上传后的图片可以通过静态文件服务访问
    img_resp = client.get(f"{BASE}{data['image_url']}")
    assert img_resp.status_code == 200
    assert len(img_resp.content) == len(png_bytes)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
