"""手动测试上传 API（需要后端运行中）"""
import httpx

c = httpx.Client(timeout=10, trust_env=False)
BASE = "http://127.0.0.1:8006"

# 最小有效 PNG
png = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
    b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

# 1. 上传
r = c.post(f"{BASE}/api/upload", files={"file": ("test.png", png, "image/png")})
print(f"Upload: {r.status_code}")
d = r.json()
print(f"  file_id: {d['file_id']}")
print(f"  url: {d['image_url']}")

# 2. 访问图片
r2 = c.get(f"{BASE}{d['image_url']}")
print(f"Image access: {r2.status_code} ({len(r2.content)} bytes)")

# 3. 拒绝文本文件
r3 = c.post(f"{BASE}/api/upload", files={"file": ("x.txt", b"hi", "text/plain")})
print(f"Text rejected: {r3.status_code}")

# 4. 拒绝超大文件 (11MB)
big = b"x" * (11 * 1024 * 1024)
r4 = c.post(f"{BASE}/api/upload", files={"file": ("big.png", big, "image/png")})
print(f"Oversize rejected: {r4.status_code}")

print("\nAll checks complete.")
