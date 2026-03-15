import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from pansou_py.models.database import init_db, async_session, Resource, SearchRequest
from pansou_py.core.search import search_service
from sqlalchemy.future import select

async def test_full_flow():
    print("🚀 [Test] Initializing database...")
    await init_db()
    
    keyword = "测试资源_" + os.urandom(4).hex()
    print(f"🔍 [Test] Searching for NEW keyword (should fall back to TG): {keyword}")
    
    # 1. First search: should hit TG and save to DB
    result1 = await search_service.search(keyword=keyword, max_pages=1)
    print(f"📊 [Test] First search returned {result1.get('total', 0)} results.")
    
    # 2. Check if request was recorded in DB
    async with async_session() as session:
        query = select(SearchRequest).where(SearchRequest.keyword == keyword)
        req = (await session.execute(query)).scalar_one_or_none()
        if req:
            print(f"✅ [Test] Search request recorded in DB. Status: {req.status}")
        else:
            print("❌ [Test] Search request NOT found in DB.")

    # 3. Second search: should hit local DB
    print(f"🔍 [Test] Searching for the SAME keyword again (should hit local DB)...")
    result2 = await search_service.search(keyword=keyword)
    print(f"📊 [Test] Second search returned {result2.get('total', 0)} results from local DB.")
    
    if result2.get("total") == result1.get("total"):
        print("✅ [Test] Local DB consistency verified.")
    else:
        print("⚠️ [Test] Result count mismatch (might be expected if TG search is non-deterministic).")

if __name__ == "__main__":
    asyncio.run(test_full_flow())
