"""3-turn conversation trace test."""
import urllib.request
import json
import asyncio
from sqlalchemy import text
from app.core.database import get_session_sync

def send(query, cid=""):
    body = json.dumps({
        "user_query": query, "session_id": "demo",
        "user_id": "u1", "conversation_id": cid,
    }).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8006/api/recommend/v2",
        data=body, headers={"Content-Type": "application/json"},
    )
    r = json.loads(urllib.request.urlopen(req).read())
    return r["conversation_id"], len(r["products"]), r["answer"][:80]

# ---- 3-turn conversation ----
print("=== 3-Turn Conversation ===")
cid1, p1, a1 = send("推荐一个蓝牙耳机")
print(f"Turn1: cid={cid1[:20]} products={p1}")

cid2, p2, a2 = send("第二个怎么样？", cid1)
print(f"Turn2: cid={cid2[:20]} same_cid={cid2==cid1} products={p2}")

cid3, p3, a3 = send("能不能便宜点", cid1)
print(f"Turn3: cid={cid3[:20]} same_cid={cid3==cid1} products={p3}")

# ---- DB Dump ----
async def dump():
    factory = get_session_sync()
    async with factory() as session:
        print("\n=== conversations ===")
        r = await session.execute(text(
            "SELECT conversation_id, user_id, session_id, status, "
            "substring(last_message,1,40) FROM conversations ORDER BY created_at"
        ))
        for row in r:
            print(f"  {row[0]} user={row[1]} sess={row[2]} last_msg={row[4]}")

        print(f"\n=== messages for {cid1[:20]} ===")
        r = await session.execute(text(
            f"SELECT role, substring(content,1,60) FROM conversation_messages "
            f"WHERE conversation_id='{cid1}' ORDER BY created_at"
        ))
        for row in r:
            print(f"  [{row[0]:9s}] {row[1]}")

        print("\n=== behavior_events ===")
        r = await session.execute(text(
            "SELECT event_type, substring(conversation_id,1,20), substring(query,1,30) "
            "FROM behavior_events ORDER BY created_at"
        ))
        for row in r:
            print(f"  {row[0]:10s} conv={row[1]} query={row[2]}")

        print("\n=== context_snapshot ===")
        r = await session.execute(text(
            f"SELECT context_snapshot FROM conversations WHERE conversation_id='{cid1}'"
        ))
        snap = r.scalar()
        for k, v in (snap or {}).items():
            print(f"  {k}: {str(v)[:80]}")

asyncio.run(dump())
