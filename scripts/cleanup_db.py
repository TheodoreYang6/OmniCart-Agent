"""清理 PostgreSQL 所有表内容(TRUNCATE) + Qdrant 所有 collection 重建。"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = "postgresql+asyncpg://omnicart:omnicart@localhost:5432/omnicart"

TABLES = [
    "cart_items", "user_preferences", "addresses",
    "conversation_messages", "conversations", "behavior_events",
    "memory_audit_logs", "memory_usage_traces", "user_memories",
    "products", "users",
]


async def truncate_pg():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        for table in TABLES:
            await conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
            print(f"  [PG] TRUNCATED: {table}")
    await engine.dispose()
    print("[PG] 所有表内容已清空，表结构保留\n")


def cleanup_qdrant():
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(url="http://localhost:6333")
        for coll in ["products", "product_chunks"]:
            try:
                client.delete_collection(coll)
                print(f"  [Qdrant] DELETED: {coll}")
            except Exception:
                print(f"  [Qdrant] SKIP: {coll} (不存在或已删除)")
        client.close()
        print("[Qdrant] 所有 collection 已删除\n")
    except ImportError:
        print("[Qdrant] qdrant-client 未安装，跳过\n")
    except Exception as e:
        print(f"[Qdrant] 连接失败: {e}\n")


async def main():
    print("=== 开始清理数据库内容 ===\n")
    await truncate_pg()
    cleanup_qdrant()
    print("=== 清理完成 ===")


if __name__ == "__main__":
    asyncio.run(main())
