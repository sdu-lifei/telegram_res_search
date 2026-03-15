import asyncio
from datetime import datetime
from sqlalchemy.future import select
from pansou_py.models.database import async_session, SearchRequest
from pansou_py.core.search import search_service
from pansou_py.core.config import settings

class SearchScheduler:
    def __init__(self, interval_minutes: int = 30):
        self.interval = interval_minutes * 60
        self.running = False

    async def start(self):
        if self.running:
            return
        self.running = True
        print(f"⏰ [Scheduler] Starting search retry scheduler (interval: {settings.SCHEDULE_INTERVAL}m)")
        asyncio.create_task(self._loop())

    async def _loop(self):
        while self.running:
            try:
                await self.retry_pending_searches()
            except Exception as e:
                print(f"❌ [Scheduler] Error in retry loop: {e}")
            await asyncio.sleep(self.interval)

    async def retry_pending_searches(self):
        print("🔍 [Scheduler] Checking for pending search requests...")
        async with async_session() as session:
            query = select(SearchRequest).where(SearchRequest.status == "pending")
            result = await session.execute(query)
            pending_requests = result.scalars().all()

        if not pending_requests:
            print("✅ [Scheduler] No pending requests to retry.")
            return

        print(f"🔄 [Scheduler] Retrying {len(pending_requests)} pending requests...")
        for req in pending_requests:
            print(f"🔎 [Scheduler] Retrying search for: {req.keyword}")
            # Trigger search with force_refresh to ignore local DB (since it was missing)
            await search_service.search(keyword=req.keyword, force_refresh=True, max_pages=3)
            # SearchService.search will update status to 'found' if results are found

    def stop(self):
        self.running = False

scheduler = SearchScheduler(interval_minutes=settings.SCHEDULE_INTERVAL)
