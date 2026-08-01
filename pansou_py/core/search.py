import asyncio
import re
from typing import List, Dict, Optional, Any
from pansou_py.models.schemas import SearchResult
from pansou_py.core.cache import cache_service
from pansou_py.plugins import plugin_manager
from pansou_py.core.tg_searcher import telegram_searcher
from pansou_py.core.config import settings
from pansou_py.models.database import async_session, Resource, SearchRequest
from pansou_py.utils.normalization import normalize_keyword
from pansou_py.utils.validator import link_validator
from sqlalchemy.future import select
from sqlalchemy import delete
from datetime import datetime
from sqlalchemy.exc import IntegrityError

_search_locks: Dict[str, asyncio.Lock] = {}
_locks_access = asyncio.Lock()

async def get_keyword_lock(keyword: str) -> asyncio.Lock:
    async with _locks_access:
        if keyword not in _search_locks:
            _search_locks[keyword] = asyncio.Lock()
        return _search_locks[keyword]

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
        max_results: Optional[int] = None,
        tg_timeout: float = 3.0
    ) -> dict:
        keyword = normalize_keyword(keyword)
        if not keyword:
            return {"total": 0, "results": [], "merged_by_type": {}}

        cache_key = f"search_{keyword}_{src}_{plugins}_{cloud_types}_{max_pages}_{max_results}_{settings.QUARK_CLICK_TRANSFER}"
        if not force_refresh:
            cached = cache_service.get(cache_key)
            if cached:
                return cached

        # Use per-keyword lock to avoid duplicate parallel searches
        lock = await get_keyword_lock(keyword)
        
        # If this is a foreground request and the keyword is already being searched by a background task, 
        # return early to let user know it's in progress instead of waiting and timing out.
        if lock.locked() and not force_refresh:
            return {
                "total": 0,
                "results": [],
                "merged_by_type": {},
                "status": "searching",
                "progress": 20,
                "message": "后台正在搜索，请稍后自动刷新。",
            }

        async with lock:
            # Re-check cache inside lock in case another task just finished it
            if not force_refresh:
                cached = cache_service.get(cache_key)
                if cached: return cached

        # 1. Search local resource database FIRST (without locking)
        db_resources = await self._search_local_db(keyword, cloud_types or ["quark"])
        fresh_db_results = []
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
                fresh_db_results = fresh_results + validated_stale
            else:
                print(f"🏠 [Search] Found {len(db_resources)} results in DB. All are fresh, skipping validation.")
                fresh_db_results = fresh_results

            fresh_db_results = self._rank_and_filter_results(keyword, fresh_db_results)
            
            print(f"🏠 [Search] Total {len(fresh_db_results)} DB results ready for '{keyword}'.")

        # 2. Search external if needed, wrapped in a lock to avoid duplicate fetching
        all_results = fresh_db_results
        
        if not all_results or force_refresh:
            lock = await get_keyword_lock(keyword)
            
            # Non-blocking check for foreground queries: if already searching, don't wait 4s
            if lock.locked() and not force_refresh:
                 # We return what we have from DB (which might have just been updated)
                 # and let the background task continue.
                 pass
            else:
                async with lock:
                    # Check cache again inside lock
                    if not force_refresh:
                        cached = cache_service.get(cache_key)
                        if cached: return cached
                    
                    tg_results: List[SearchResult] = []
                    plugin_results: List[SearchResult] = []
                    
                    channels_to_search = channels if channels else settings.default_channels
                    
                    if src in ["all", "tg"]:
                        # TG search logic...
                        print(f"📡 [Search] Searching Telegram channels: {channels_to_search} (timeout: {tg_timeout}s)")
                        tasks = [asyncio.create_task(telegram_searcher.search(ch, keyword, max_pages=max_pages)) for ch in channels_to_search]
                        try:
                            done, _ = await asyncio.wait(tasks, timeout=tg_timeout)
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
                    new_external_results = self._rank_and_filter_results(keyword, new_external_results)
                    
                    # Filter by cloud types BEFORE validation to save time
                    target_types = cloud_types if cloud_types else ["quark"]
                    new_external_results = [
                        res for res in new_external_results 
                        if any(l.type in target_types for l in res.links)
                    ]
                    # Filter individual links within results
                    for res in new_external_results:
                        res.links = [l for l in res.links if l.type in target_types]
                    
                    # Limit candidates to reduce validation time (especially important for WeChat path)
                    val_limit = (max_results * 2) if max_results else 12
                    if len(new_external_results) > val_limit:
                        new_external_results = new_external_results[:val_limit]
                    
                    if new_external_results:
                        print(f"🛡️ [Search] Validating {len(new_external_results)} candidates for '{keyword}'...")
                        validated_external = await self._validate_all_results_deep(new_external_results)
                        validated_external = self._rank_and_filter_results(keyword, validated_external)
                        
                        if max_results and len(validated_external) > max_results:
                            validated_external = validated_external[:max_results]
                            
                        print(f"✅ [Search] {len(validated_external)} valid results found for '{keyword}'")
                        
                        if validated_external:
                            # Save ONLY valid results to DB
                            saved_count = await self._save_results_to_db(keyword, validated_external)
                            print(f"💾 [Search] Saved {saved_count} new links to DB for '{keyword}'")
                            # Merge with existing
                            all_results = self._rank_and_filter_results(keyword, self._merge_results(all_results, validated_external))

        all_results = self._rank_and_filter_results(keyword, all_results)
        await self._enrich_results_with_resource_meta(all_results)

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
                    "images": r.images,
                    "resource_id": link.resource_id,
                    "open_url": link.open_url,
                    "transfer_status": link.transfer_status,
                }

                if not existing or (bool(new_item.get("password")) and not existing.get("password")) or \
                   (bool(existing.get("password")) == bool(new_item.get("password")) and new_item.get("datetime", "") > existing.get("datetime", "")):
                    type_dict[link.url] = new_item

        for c_type, url_map in seen_urls.items():
            merged_by_type[c_type] = list(url_map.values())

        missing_status = None
        if not all_results:
            missing_status = await self._record_missing_request(keyword)
        else:
            await self._update_request_status(keyword, "found")

        response = {
            "total": sum(len(links) for links in merged_by_type.values()),
            **({"results": [r.model_dump() for r in all_results]} if res_type in ["all", "results"] else {}),
            **({"merged_by_type": merged_by_type} if res_type in ["all", "merge"] else {}),
        }
        if not all_results:
            if missing_status == "failed":
                response["status"] = "failed"
                response["progress"] = 100
                response["message"] = "暂未找到可用资源，可以换完整名称、年份或清晰度再试。"
            else:
                response["status"] = "searching"
                response["progress"] = 35
                response["message"] = "后台仍在搜索，找到后会自动刷新。"
            cache_service.delete(cache_key)
        else:
            response["status"] = "found"
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

    def _rank_and_filter_results(self, keyword: str, results: List[SearchResult]) -> List[SearchResult]:
        if not results:
            return []

        scored = []
        for index, result in enumerate(results):
            score = self._relevance_score(keyword, result)
            if score > 0:
                scored.append((score, index, result))

        scored.sort(key=lambda item: (item[0], item[2].datetime), reverse=True)
        return [result for _, _, result in scored]

    def _relevance_score(self, keyword: str, result: SearchResult) -> int:
        exact = re.sub(r"\s+", "", keyword).lower()
        terms = self._keyword_terms(keyword)
        title = self._compact_text(result.title)
        description = self._compact_text(result.description or "")
        link_titles = self._compact_text(" ".join(link.work_title or "" for link in result.links))
        channel = self._compact_text(result.channel or "")

        score = 0
        if exact:
            if exact in title:
                score += 90
            if exact in link_titles:
                score += 45
            if exact in description:
                score += 30
            if exact in channel:
                score += 8

        for term in terms:
            if not term or term == exact:
                continue
            if term in title:
                score += 30
            if term in link_titles:
                score += 18
            if term in description:
                score += 10

        if result.channel == "web_fallback" and score < 30:
            return 0
        return score

    def _keyword_terms(self, keyword: str) -> List[str]:
        compact = re.sub(r"\s+", "", keyword).lower()
        terms = [compact] if compact else []
        for term in re.findall(r"[\w\u4e00-\u9fff]{2,}", keyword):
            term = term.lower()
            if term not in terms:
                terms.append(term)
        return terms

    def _compact_text(self, value: str) -> str:
        return re.sub(r"\s+", "", value or "").lower()

    def _convert_db_to_search_results(self, db_results: List[Resource]) -> List[SearchResult]:
        from pansou_py.models.schemas import Link as SchemaLink
        results = []
        for r in db_results:
            open_url = self._resource_open_url(r.id)
            results.append(SearchResult(
                message_id=str(r.id),
                unique_id=f"db_{r.id}",
                channel=r.source,
                datetime=r.datetime.isoformat() if r.datetime else "",
                title=r.title,
                description=r.description,
                links=[SchemaLink(
                    type=r.disk_type,
                    url=r.url,
                    password=r.password or "",
                    resource_id=r.id,
                    open_url=open_url,
                    transfer_status=r.transfer_status or "none",
                )],
                images=r.images
            ))
        return results

    def _resource_open_url(self, resource_id: int) -> str:
        path = f"/r/{resource_id}"
        if settings.PUBLIC_BASE_URL:
            return settings.PUBLIC_BASE_URL.rstrip("/") + path
        return path

    async def _enrich_results_with_resource_meta(self, results: List[SearchResult]) -> None:
        urls = [link.url for r in results for link in r.links if not link.resource_id]
        if not urls:
            return

        async with async_session() as session:
            query = select(Resource).where(Resource.url.in_(urls))
            rows = (await session.execute(query)).scalars().all()

        by_url = {row.url: row for row in rows}
        for r in results:
            for link in r.links:
                resource = by_url.get(link.url)
                if not resource:
                    continue
                open_url = self._resource_open_url(resource.id)
                link.resource_id = resource.id
                link.open_url = open_url
                link.transfer_status = resource.transfer_status or "none"

    async def _record_missing_request(self, keyword: str) -> str:
        async with async_session() as session:
            async with session.begin():
                query = select(SearchRequest).where(SearchRequest.keyword == keyword)
                result = await session.execute(query)
                req = result.scalar_one_or_none()
                if req:
                    req.count += 1
                    req.last_search = datetime.utcnow()
                    if req.count >= settings.SEARCH_MAX_RETRIES:
                        req.status = "failed"
                    elif req.status != "failed":
                        req.status = "pending"
                else:
                    req = SearchRequest(keyword=keyword, status="pending")
                    session.add(req)
                return req.status

    async def _update_request_status(self, keyword: str, status: str):
        async with async_session() as session:
            async with session.begin():
                query = select(SearchRequest).where(SearchRequest.keyword == keyword)
                result = await session.execute(query)
                req = result.scalar_one_or_none()
                if req:
                    req.status = status

    async def _save_results_to_db(self, keyword: str, results: List[SearchResult]) -> int:
        count = 0
        async with async_session() as session:
            try:
                # One transaction for the whole batch is MUCH faster in SQLite
                async with session.begin():
                    for r in results:
                        for link in r.links:
                            # Check if URL already exists locally
                            query = select(Resource.id).where(Resource.url == link.url)
                            existing = (await session.execute(query)).first()
                            
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
                                count += 1
            except IntegrityError:
                # Should not happen with pre-check but handle just in case
                pass
            except Exception as e:
                print(f"❌ [DB] Error batch saving resources: {e}")
        return count

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

        owner_shared_resources = [r for r in resources if r.owner_share_url]
        resources_to_validate = [r for r in resources if not r.owner_share_url]
        if not resources_to_validate:
            return self._convert_db_to_search_results(owner_shared_resources)
        
        urls_to_check = [{"url": r.url, "type": r.disk_type} for r in resources_to_validate]
        valid_links = await link_validator.filter_links(urls_to_check, timeout=settings.VALIDATE_TIMEOUT)
        valid_urls = {l['url'] for l in valid_links}
        invalid_urls = {l['url'] for l in urls_to_check if l['url'] not in valid_urls}
        
        if invalid_urls:
            print(f"🗑️ [DB] Found {len(invalid_urls)} invalid links in DB cleanup.")
            await self._delete_invalid_resources(list(invalid_urls))
            
        if valid_urls:
            await self._update_validation_time(list(valid_urls))
            
        filtered_resources = owner_shared_resources + [r for r in resources_to_validate if r.url in valid_urls]
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
