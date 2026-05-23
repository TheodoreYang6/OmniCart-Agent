"""可观测性 API — 查看 LLM 调用追踪和聚合统计"""

from fastapi import APIRouter, Query

from app.observability.collector import get_collector

router = APIRouter(prefix="/api/observability", tags=["observability"])


@router.get("/traces")
async def list_traces(
    limit: int = Query(50, ge=1, le=500),
    name: str = Query("", description="按调用类型筛选: qwen.chat / qwen.vision / qwen.embed / qwen.rerank"),
    status: str = Query("", description="按状态筛选: success / error / mock / fallback"),
):
    """获取最近 LLM 调用追踪列表"""
    collector = get_collector()
    traces = await collector.query(limit=limit, name=name, status=status)
    return {"total": len(traces), "traces": traces}


@router.get("/traces/{span_id}")
async def get_trace(span_id: str):
    """获取单条 LLM 调用完整追踪"""
    collector = get_collector()
    span = await collector.get_span(span_id)
    if span is None:
        return {"error": "span not found"}
    return span


@router.get("/stats")
async def observability_stats(
    hours: int = Query(24, ge=1, le=720, description="统计窗口（小时），默认 24h"),
):
    """LLM 调用聚合统计：次数、token、延迟分布、错误率"""
    collector = get_collector()
    return await collector.stats(hours=hours)


@router.delete("/traces")
async def clear_traces(
    before: str = Query("", description="清除此时间之前的 trace（ISO 格式），不传则全清"),
):
    """清除追踪数据"""
    collector = get_collector()
    deleted = await collector.clear(before=before)
    return {"deleted": deleted, "message": f"Cleared {deleted} trace records"}
