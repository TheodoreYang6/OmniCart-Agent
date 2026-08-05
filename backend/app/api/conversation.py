"""Conversation REST API — 对话历史管理。"""

from fastapi import APIRouter, Depends, Query, HTTPException

from app.schemas.conversation import ConversationOut, MessageOut
from app.repositories.conversation_repo import get_conversation_repo
from app.core.identity import Actor, resolve_actor

router = APIRouter()


@router.get("/api/conversations")
async def list_conversations(
    user_id: str = Query(default="", description="按用户ID查询"),
    limit: int = Query(default=20, ge=1, le=100),
    actor: Actor = Depends(resolve_actor),
):
    user_id = actor.user_id
    repo = get_conversation_repo()
    convs = repo.list_by_user(user_id, limit)
    return {
        "user_id": user_id,
        "count": len(convs),
        "conversations": [
            ConversationOut(
                conversation_id=c.conversation_id,
                user_id=c.user_id,
                session_id=c.session_id,
                title=c.title,
                status=c.status,
                summary=c.summary,
                last_message=getattr(c, 'last_message', '') or '',
                context_snapshot=getattr(c, 'context_snapshot', {}) or {},
                created_at=c.created_at,
                updated_at=c.updated_at,
            ).model_dump()
            for c in convs
        ],
    }


@router.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, actor: Actor = Depends(resolve_actor)):
    repo = get_conversation_repo()
    conv = repo.get(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.user_id != actor.user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationOut(
        conversation_id=conv.conversation_id,
        user_id=conv.user_id,
        session_id=conv.session_id,
        title=conv.title,
        status=conv.status,
        summary=conv.summary,
        last_message=getattr(conv, 'last_message', '') or '',
        context_snapshot=getattr(conv, 'context_snapshot', {}) or {},
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    ).model_dump()


@router.get("/api/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    actor: Actor = Depends(resolve_actor),
):
    repo = get_conversation_repo()
    conv = repo.get(conversation_id)
    if not conv or conv.user_id != actor.user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    msgs = repo.list_messages(conversation_id, limit)
    # 收集所有被引用的商品ID，批量查产品信息供前端渲染卡片
    products_map = {}
    all_pids = set()
    for m in msgs:
        refs = getattr(m, 'product_refs', None) or []
        if isinstance(refs, list):
            all_pids.update(refs)
    if all_pids:
        try:
            from app.repositories.product_repo import get_product_repo
            prod_repo = get_product_repo()
            for pid in all_pids:
                p = prod_repo.get_by_id(pid)
                if p:
                    products_map[pid] = {
                        "product_id": p.product_id, "title": p.title,
                        "brand": p.brand, "price": p.base_price,
                        "category": p.category,
                        "image_urls": [prod_repo.resolve_image_url(pid)] if p.image_path else [],
                    }
        except Exception:
            pass
    return {
        "conversation_id": conversation_id,
        "count": len(msgs),
        "products": products_map,
        "messages": [
            MessageOut(
                message_id=m.message_id,
                conversation_id=m.conversation_id,
                user_id=m.user_id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                image_url=m.image_url,
                product_refs=m.product_refs or [],
                evidence_refs=m.evidence_refs or [],
                memory_refs=m.memory_refs or [],
                created_at=m.created_at,
                metadata=m.extra_data or {},
            ).model_dump()
            for m in msgs
        ],
    }


@router.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, actor: Actor = Depends(resolve_actor)):
    repo = get_conversation_repo()
    conv = repo.get(conversation_id)
    if not conv or conv.user_id != actor.user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    ok = repo.delete(conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found or delete failed")
    return {"ok": True, "conversation_id": conversation_id}
