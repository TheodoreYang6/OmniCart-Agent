import os
import uuid
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, HTTPException

from app.core.config import DEMO_DATA_DIR

router = APIRouter()

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent.parent / DEMO_DATA_DIR / "uploads"
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_SIZE_MB = 10
MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024


@router.post("/api/upload", response_model=None)
async def upload(file: UploadFile = File(...)):
    if file.content_type and file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {file.content_type}。仅支持 JPEG / PNG / WebP / GIF",
        )

    contents = await file.read()

    if len(contents) > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大: {len(contents) / 1024 / 1024:.1f}MB。最大允许 {MAX_SIZE_MB}MB",
        )

    # 生成唯一文件名，保留原始扩展名
    ext = _get_ext(file.filename or "image.png")
    file_id = f"{uuid.uuid4().hex[:12]}"
    filename = f"{file_id}{ext}"

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filepath = UPLOAD_DIR / filename
    filepath.write_bytes(contents)

    return {
        "file_id": file_id,
        "filename": filename,
        "image_url": f"/api/uploads/{filename}",
        "size_bytes": len(contents),
        "content_type": file.content_type or "unknown",
    }


def _get_ext(filename: str) -> str:
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        return ext
    return ".png"
