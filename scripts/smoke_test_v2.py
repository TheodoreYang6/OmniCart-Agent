import httpx, asyncio

async def test():
    async with httpx.AsyncClient() as c:
        # Health
        r = await c.get('http://127.0.0.1:8006/api/health')
        print(f'Health: {r.status_code}')

        # V2 Workflow
        r2 = await c.post('http://127.0.0.1:8006/api/recommend/v2',
                         json={'user_query': '蓝牙耳机推荐', 'session_id': 'test'}, timeout=30)
        d = r2.json()
        print(f'V2: {r2.status_code} products={len(d.get("products",[]))} traces={len(d.get("trace_steps",[]))}')

        # V0 endpoint (uses shared rules)
        r3 = await c.post('http://127.0.0.1:8006/api/recommend',
                         json={'user_query': '保湿精华推荐'}, timeout=30)
        d3 = r3.json()
        print(f'V0: {r3.status_code} products={len(d3.get("products",[]))}')

        # Upload with magic byte validation
        png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
        r4 = await c.post('http://127.0.0.1:8006/api/upload',
                         files={'file': ('test.png', png, 'image/png')}, timeout=10)
        print(f'Upload PNG: {r4.status_code} {r4.json().get("filename","?")}')

        # Upload fake image (should be rejected)
        r5 = await c.post('http://127.0.0.1:8006/api/upload',
                         files={'file': ('hack.exe', b'not an image!!', 'image/png')}, timeout=10)
        print(f'Upload fake (rejected): {r5.status_code}')

asyncio.run(test())
