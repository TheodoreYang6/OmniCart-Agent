"""一键清空所有表（保留 products）"""
import asyncio
from sqlalchemy import text
from app.core.database import get_session_sync

async def main():
    factory = get_session_sync()
    async with factory() as session:
        tables = [
            'conversation_messages', 'conversations', 'behavior_events',
            'user_memories', 'user_preferences', 'memory_audit_logs', 'memory_usage_traces',
            'cart_items', 'addresses',
        ]
        for t in tables:
            await session.execute(text(f'TRUNCATE TABLE "{t}" CASCADE'))
        await session.commit()
        print('All tables cleared (products kept)')

if __name__ == '__main__':
    asyncio.run(main())
