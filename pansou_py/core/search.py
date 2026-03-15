import asyncio
from typing import List, Dict, Optional, Any
from pansou_py.models.schemas import SearchResult
from pansou_py.core.cache import cache_service
from pansou_py.plugins import plugin_manager
from pansou_py.core.tg_searcher import telegram_searcher
from pansou_py.core.config import settings
from pansou_py.models.database import async_session, Resource, SearchRequest
from pansou_py.utils.normalization import normalize_keyword
from pansou_py.core.quark import quark_service
from pansou_py.utils.validator import link_validator
from sqlalchemy.future import select
from sqlalchemy import delete
from datetime import datetime

class SearchService:
    def __init__(self):
        self.plugin_manager = plugin_manager

    def _merge_results(self, tg: List[SearchResult], plugin: List[SearchResult]) -> List[SearchResult]:
        seen = {}
        for r in tg + plugin:
            key = f"{r.channel}_{r.message_id}"
            if key not in seen:
                seen[key] = r
        merged = list(seen.values())
        merged.sort(key=lambda x: x.datetime, reverse=True)
        return merged

    async def search_plugins(self, keyword: str, plugins_filter: Optional[List[str]], max_pages: int = 5) -> List[SearchResult]:
        plugins = self.plugin_manager.get_plugins()
        if plugins_filter:
            plugins = [p for p in plugins if p.name in plugins_filter]
        # Note: We assume plugins also support max_pages if they use it
        results_list = await asyncio.gather(*[p.search(keyword) for p in plugins], return_exceptions=True)
        return [r for res in results_list if isinstance(res, list) for r in res]

    async def search(
        self,
        keyword: str,
        channels: Optional[List[str]] = None,
        force_refresh: bool = False,
        res_type: str = "merge",
        src: str = "all",
        plugins: Optional[List[str]] = None,
        cloud_types: Optional[List[str]] = None,
        max_pages: int = 5,
        max_results: Optional[int] = None
    ) -> dict:
        keyword = normalize_keyword(keyword)
        if not keyword:
            return {"total": 0, "results": [], "merged_by_type": {}}

        cache_key = f"search_{keyword}_{src}_{plugins}"
        if not force_refresh:
            cached = cache_service.get(cache_key)
            if cached:
                return cached

        # 1. Search local resource database
        db_resources = await self._search_local_db(keyword, cloud_types)
        all_results = []
        if db_resources:
            now = datetime.utcnow()
            stale_resources = []
            fresh_results = []
            
            # 12 hours threshold for re-validation
            threshold = 12 * 3600
            
            for r in db_resources:
                is_stale = True
                if r.last_validated:
                    delta = (now - r.last_validated).total_seconds()
                    if delta < threshold:
                        is_stale = False
                
                if is_stale or force_refresh:
                    stale_resources.append(r)
                else:
                    fresh_results.extend(self._convert_db_to_search_results([r]))

            if stale_resources:
                print(f"🏠 [Search] Found {len(db_resources)} results in DB. Validating {len(stale_resources)} stale links...")
                validated_stale = await self._validate_and_cleanup_db_resources(stale_resources)
                all_results = fresh_results + validated_stale
            else:
                print(f"🏠 [Search] Found {len(db_resources)} results in DB. All are fresh, skipping validation.")
                all_results = fresh_results
            
            print(f"🏠 [Search] Total {len(all_results)} DB results ready.")

        # 2. Search external if needed
        if not all_results or force_refresh:
            tg_results: List[SearchResult] = []
            plugin_results: List[SearchResult] = []
            
            channels_to_search = channels if channels else settings.default_channels
            
            if src in ["all", "tg"]:
                print(f"📡 [Search] Searching Telegram channels: {channels_to_search} (timeout: 4.0s)")
                tasks = [asyncio.create_task(telegram_searcher.search(ch, keyword, max_pages=max_pages)) for ch in channels_to_search]
                try:
                    done, _ = await asyncio.wait(tasks, timeout=4.0)
                    for task in done:
                        try:
                            res = await task
                            if isinstance(res, list): tg_results.extend(res)
                        except: pass
                    for t in tasks:
                        if not t.done(): t.cancel()
                except: pass

            if src in ["all", "plugin"]:
                print(f"🔌 [Search] Searching plugins for '{keyword}'")
                plugin_results = await self.search_plugins(keyword, plugins)

            # Combine and merge new findings
            new_external_results = self._merge_results(tg_results, plugin_results)
            
            # Limit external results if requested (e.g. for quick WeChat reply)
            if max_results and len(new_external_results) > max_results:
                new_external_results = new_external_results[:max_results]
            
            if new_external_results:
                print(f"🛡️ [Search] Validating {len(new_external_results)} new external results...")
                # Validate external results BEFORE saving
                validated_external = await self._validate_all_results_deep(new_external_results)
                print(f"✅ [Search] {len(validated_external)}/{len(new_external_results)} external results are valid")
                
                if validated_external:
                    # Save ONLY valid results to DB
                    await self._save_results_to_db(keyword, validated_external)
                    # Trigger Quark transfer
                    if settings.QUARK_AUTO_TRANSFER:
                        asyncio.create_task(self._trigger_quark_transfer(validated_external))
                    # Merge with existing
                    all_results = self._merge_results(all_results, validated_external)

        # 3. Build merged view for response
        merged_by_type: Dict = {}
        seen_urls: Dict[str, Dict[str, Dict]] = {}

        for r in all_results:
            for link in r.links:
                if cloud_types and link.type not in cloud_types:
                    continue
                
                type_dict = seen_urls.setdefault(link.type, {})
                existing = type_dict.get(link.url)
                
                new_item = {
                    "url": link.url,
                    "password": link.password,
                    "note": r.title,
                    "datetime": r.datetime,
                    "source": f"tg:{r.channel}",
                    "images": r.images
                }

                if not existing or (bool(new_item.get("password")) and not existing.get("password")) or \
                   (bool(existing.get("password")) == bool(new_item.get("password")) and new_item.get("datetime", "") > existing.get("datetime", "")):
                    type_dict[link.url] = new_item

        for c_type, url_map in seen_urls.items():
            merged_by_type[c_type] = list(url_map.values())

        if not all_results:
            await self._record_missing_request(keyword)
        else:
            await self._update_request_status(keyword, "found")

        response = {
            "total": sum(len(links) for links in merged_by_type.values()),
            **({"results": [r.model_dump() for r in all_results]} if res_type in ["all", "results"] else {}),
            **({"merged_by_type": merged_by_type} if res_type in ["all", "merge"] else {}),
        }
        
        cache_service.set(cache_key, response)
        return response

    async def _search_local_db(self, keyword: str, cloud_types: Optional[List[str]]) -> List[Resource]:
        async with async_session() as session:
            from sqlalchemy import or_
            # Full text search in keyword, title AND description
            query = select(Resource).where(
                or_(
                    Resource.keyword.like(f"%{keyword}%"),
                    Resource.title.like(f"%{keyword}%"),
                    Resource.description.like(f"%{keyword}%")
                )
            )
            if cloud_types:
                query = query.where(Resource.disk_type.in_(cloud_types))
            result = await session.execute(query)
            return result.scalars().all()

    def _convert_db_to_search_results(self, db_results: List[Resource]) -> List[SearchResult]:
        from pansou_py.models.schemas import Link as SchemaLink
        results = []
        for r in db_results:
            results.append(SearchResult(
                message_id=str(r.id),
                unique_id=f"db_{r.id}",
                channel=r.source,
                datetime=r.datetime.isoformat() if r.datetime else "",
                title=r.title,
                description=r.description,
                links=[SchemaLink(type=r.disk_type, url=r.url, password=r.password or "")],
                images=r.images
            ))
        return results

    async def _record_missing_request(self, keyword: str):
        async with async_session() as session:
            async with session.begin():
                query = select(SearchRequest).where(SearchRequest.keyword == keyword)
                result = await session.execute(query)
                req = result.scalar_one_or_none()
                if req:
                    req.count += 1
                    req.last_search = datetime.utcnow()
                else:
                    session.add(SearchRequest(keyword=keyword))

    async def _update_request_status(self, keyword: str, status: str):
        async with async_session() as session:
            async with session.begin():
                query = select(SearchRequest).where(SearchRequest.keyword == keyword)
                result = await session.execute(query)
                req = result.scalar_one_or_none()
                if req:
                    req.status = status

    async def _save_results_to_db(self, keyword: str, results: List[SearchResult]):
        async with async_session() as session:
            async with session.begin():
                for r in results:
                    for link in r.links:
                        # Check if URL already exists
                        query = select(Resource).where(Resource.url == link.url)
                        existing = (await session.execute(query)).scalar_one_or_none()
                        if not existing:
                            session.add(Resource(
                                keyword=keyword,
                                title=r.title,
                                description=r.description,
                                url=link.url,
                                password=link.password,
                                disk_type=link.type,
                                source=f"tg:{r.channel}",
                                datetime=datetime.fromisoformat(r.datetime.replace("Z", "+00:00")),
                                images=r.images,
                                last_validated=datetime.utcnow()
                            ))

    async def _trigger_quark_transfer(self, results: List[SearchResult]):
        for r in results:
            for link in r.links:
                if link.type == "quark":
                    new_link = await quark_service.auto_transfer_flow(link.url, link.password)
                    if new_link:
                        print(f"✅ [Quark] Auto-transfer success: {new_link}")
                        # Update DB with new link would go here

    async def _update_validation_time(self, urls: List[str]):
        """Update last_validated timestamp for valid URLs."""
        if not urls:
            return
        try:
            async with async_session() as session:
                async with session.begin():
                    from sqlalchemy import update
                    stmt = update(Resource).where(Resource.url.in_(urls)).values(last_validated=datetime.utcnow())
                    await session.execute(stmt)
        except Exception as e:
            print(f"❌ [DB] Error updating validation time: {e}")

    async def _validate_and_cleanup_db_resources(self, resources: List[Resource]) -> List[SearchResult]:
        """Validate Resource objects from DB and remove invalid ones."""
        if not settings.VALIDATE_LINKS or not resources:
            return self._convert_db_to_search_results(resources)
        
        urls_to_check = [{"url": r.url, "type": r.disk_type} for r in resources]
        valid_links = await link_validator.filter_links(urls_to_check, timeout=settings.VALIDATE_TIMEOUT)
        valid_urls = {l['url'] for l in valid_links}
        invalid_urls = {l['url'] for l in urls_to_check if l['url'] not in valid_urls}
        
        if invalid_urls:
            print(f"🗑️ [DB] Found {len(invalid_urls)} invalid links in DB cleanup.")
            await self._delete_invalid_resources(list(invalid_urls))
            
        if valid_urls:
            await self._update_validation_time(list(valid_urls))
            
        filtered_resources = [r for r in resources if r.url in valid_urls]
        return self._convert_db_to_search_results(filtered_resources)

    async def _validate_all_results_deep(self, results: List[SearchResult]) -> List[SearchResult]:
        """Filter a list of results, returning only those with at least one valid link."""
        if not settings.VALIDATE_LINKS or not results:
            return results
            
        all_links = [{"url": l.url, "type": l.type} for r in results for l in r.links]
        valid_links = await link_validator.filter_links(all_links, timeout=settings.VALIDATE_TIMEOUT)
        valid_urls = {l['url'] for l in valid_links}
        
        for i in range(len(results) - 1, -1, -1):
            res = results[i]
            res.links = [l for l in res.links if l.url in valid_urls]
            if not res.links:
                results.pop(i)
        return results

    async def _delete_invalid_resources(self, urls: List[str]):
        """Remove invalid URLs from the database."""
        if not urls:
            return
        try:
            async with async_session() as session:
                async with session.begin():
                    statement = delete(Resource).where(Resource.url.in_(urls))
                    result = await session.execute(statement)
                    print(f"🗑️ [DB] Removed {result.rowcount} invalid links")
        except Exception as e:
            print(f"❌ [DB] Error cleaning dead links: {e}")

search_service = SearchService()
