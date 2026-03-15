from bs4 import BeautifulSoup
import aiohttp
import asyncio
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
import re
import urllib.parse
from pansou_py.core.config import settings
from pansou_py.models.schemas import SearchResult, Link
from pansou_py.utils.link_parser import (
    extract_netdisk_links, get_link_type, extract_password, clean_url, normalize_url
)

# Patterns to detect a line that looks like a display name / sender, not a title
_SENDER_NAME_RE = re.compile(r'^[\u4e00-\u9fff\u3040-\u30ff]{1,6}$')  # Short CJK-only names ≤6 chars
_HANDLE_RE = re.compile(r'^@\w+')
_EMOJI_ONLY_RE = re.compile(r'^[\U0001F300-\U0001FFFF\s]+$')

# Lines that contain these keywords are likely the resource title
_TITLE_KEYWORDS_RE = re.compile(
    r'(\d{4}[\s\u5e74])|'          # year like 2024 or 2024年
    r'\d+[kKpP\u9ad8\u753b\u4e2a]|'  # resolution / quality
    r'(\u96c6|\u66f4\u65b0|\u5b8c\u7ed3)|'  # 集, 更新, 完结
    r'(HDR|DV|4K|1080p|720p|HEVC|AVC|AAC|DTS)',
    re.I
)

def _normalize_keyword(kw: str) -> str:
    """Strip common metadata prefixes users might copy-paste, e.g. '名称: 逐玉' → '逐玉'"""
    kw = kw.strip()
    # Strip patterns like '名称:', '名字：', '名称: ' etc.
    kw = re.sub(r'^[\u540d\u79f0\u5c0f\u8d44\u6e90\u6807\u9898][\uff1a:\s]+', '', kw).strip()
    return kw

def _extract_title(lines: list, keyword: str = "") -> str:
    """Pick the best title line from a Telegram message's text lines.
    
    Strategy:
    0. If any line contains the search keyword, prefer that line first
    1. Skip lines that look like a sender name (@handle, short CJK name, emoji-only)
    2. Prefer lines with year/resolution/episode indicators
    3. Fall back to first non-sender line, then to first line.
    """
    keyword = _normalize_keyword(keyword)
    keyword_lower = keyword.lower() if keyword else ""
    keyword_matches = []
    candidates = []
    first_non_sender = None
    
    for line in lines:
        # Skip @handle lines
        if _HANDLE_RE.match(line):
            continue
        # Skip emoji-only lines
        if _EMOJI_ONLY_RE.match(line):
            continue
        # Skip very short CJK-only names (sender names like "北方谦三")
        if _SENDER_NAME_RE.match(line):
            continue
        # Skip lines that look like a URL
        if line.startswith('http') or line.startswith('magnet:'):
            continue
        # Skip lines that are clearly labels/metadata prefixes like 简介：, 描述：
        if re.match(r'^[名称简介描述日期源大小][：:]', line):
            # e.g. 名称：xxx  — strip the prefix and use remainder as title
            remainder = re.sub(r'^[^：:]+[：:] *', '', line).strip()
            if remainder:
                # If the remainder contains the keyword, this is the best candidate
                if keyword_lower and keyword_lower in remainder.lower():
                    return remainder
                # Otherwise queue it as a titled candidate
                if _TITLE_KEYWORDS_RE.search(remainder) or not candidates:
                    candidates.insert(0, remainder)
            continue
        
        if first_non_sender is None:
            first_non_sender = line
        
        # Highest priority: line contains the search keyword
        if keyword_lower and keyword_lower in line.lower():
            keyword_matches.append(line)
        # Second priority: line has resolution/year/episode markers
        elif _TITLE_KEYWORDS_RE.search(line):
            candidates.append(line)
    
    if keyword_matches:
        return keyword_matches[0]
    if candidates:
        return candidates[0]
    if first_non_sender:
        return first_non_sender
    return lines[0] if lines else "Unknown"

class TelegramSearcher:
    _session: Optional[aiohttp.ClientSession] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self.proxy = settings.PROXY if settings.PROXY else None

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            async with self._lock:
                if self._session is None or self._session.closed:
                    connector = aiohttp.TCPConnector(
                        limit=100,
                        ttl_dns_cache=300,
                        use_dns_cache=True,
                        force_close=False,
                        enable_cleanup_closed=True
                    )
                    self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def fetch_html(self, url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }
        
        session = await self.get_session()
        try:
            async with session.get(url, headers=headers, proxy=self.proxy, timeout=aiohttp.ClientTimeout(total=20)) as response:
                response.raise_for_status()
                return await response.text()
        except Exception as e:
            # If the session is corrupted or closed unexpectedly, try to reset it
            if isinstance(e, (aiohttp.ClientError, asyncio.TimeoutError)):
                print(f"⚠️ [TG Fetch] Session error: {e}. Resetting session...")
                async with self._lock:
                    if self._session and not self._session.closed:
                        await self._session.close()
                    self._session = None
            raise

    def build_search_url(self, channel: str, keyword: str, next_page_param: str = "") -> str:
        base_url = f"https://t.me/s/{channel}"
        if keyword:
            base_url += f"?q={urllib.parse.quote_plus(keyword)}"
            if next_page_param:
                base_url += f"&{next_page_param}"
        return base_url

    def parse_search_results(self, html: str, channel: str, keyword: str = "") -> Tuple[List[SearchResult], str]:
        soup = BeautifulSoup(html, "lxml")
        results = []
        min_message_id = None

        messages = soup.select(".tgme_widget_message_wrap")
        for message_wrap in messages:
            message_div = message_wrap.select_one(".tgme_widget_message")
            if not message_div: continue

            data_post = message_div.get("data-post")
            if not data_post or "/" not in data_post: continue
            
            message_id = data_post.split("/")[1]
            unique_id = f"{channel}_{message_id}"
            try:
                mid_int = int(message_id)
                if min_message_id is None or mid_int < min_message_id:
                    min_message_id = mid_int
            except ValueError:
                pass

            time_elem = message_div.select_one(".tgme_widget_message_date time")
            if not time_elem or not time_elem.get("datetime"): continue
            
            # Simple fallback to UTC iso parse
            try:
                # e.g. 2025-03-01T12:00:00+00:00
                dt = datetime.fromisoformat(time_elem.get("datetime").replace("Z", "+00:00")).isoformat()
            except Exception:
                dt = datetime.utcnow().isoformat()
            
            text_elem = message_div.select_one(".tgme_widget_message_text")
            if not text_elem: continue
            
            text_content = text_elem.get_text(separator="\n").strip()
            
            # Smart title extraction: skip sender names, @handles, emoji-only lines
            lines = [l.strip() for l in text_content.split("\n") if l.strip()]
            title = _extract_title(lines, keyword)

            links_dict: Dict[str, Link] = {}
            
            # Text based link extraction
            extracted_links = extract_netdisk_links(text_content)
            for raw_url in extracted_links:
                self._safely_add_link(links_dict, raw_url, text_content, title)

            # A-Tag based link extraction
            for a in text_elem.find_all("a"):
                href = a.get("href")
                if href:
                    self._safely_add_link(links_dict, href, text_content, title)

            if not links_dict:
                continue
            
            # Convert to list and filter out empty
            final_links = list(links_dict.values())
            
            # Find images
            images = []
            for img in message_div.find_all("img"):
                src = img.get("src")
                if src and src not in images:
                    images.append(src)
                    
            for photo_wrap in message_div.select(".tgme_widget_message_photo_wrap"):
                style = photo_wrap.get("style", "")
                m = re.search(r"background-image:url\(['\"]?(.*?)['\"]?\)", style)
                if m and m.group(1) not in images:
                    images.append(m.group(1))

            results.append(SearchResult(
                message_id=message_id,
                unique_id=unique_id,
                channel=channel,
                datetime=dt,
                title=title,
                description=text_content,
                links=final_links,
                images=images
            ))

        # next_page cursor: use 'before=<min_id>' so caller can fetch older posts
        next_page = f"before={min_message_id}" if min_message_id else ""
        return results, next_page

    def _safely_add_link(self, links_dict: Dict[str, Link], raw_url: str, text_content: str, default_title: str):
        l_type = get_link_type(raw_url)
        if not l_type: return

        normalized_url = normalize_url(raw_url)
        clean = clean_url(normalized_url, l_type)
        if clean in links_dict: return
        
        pwd = extract_password(text_content, raw_url)
        links_dict[clean] = Link(
            type=l_type,
            url=clean,
            password=pwd,
            work_title=default_title
        )

    MAX_PAGES = 5  # Maximum pages to fetch per channel search

    async def search(self, channel: str, keyword: str, max_pages: int = 5) -> List[SearchResult]:
        keyword = _normalize_keyword(keyword)  # strip '名称:' etc. prefixes
        all_results: List[SearchResult] = []
        seen_ids: set = set()
        next_page_param = ""

        # Limit depth based on max_pages
        for pg in range(min(max_pages, 10)):
            url = self.build_search_url(channel, keyword, next_page_param)
            print(f"🌍 [TG Fetch] Page {pg+1} for '{channel}': {url}")
            try:
                html = await self.fetch_html(url)
            except Exception as e:
                print(f"❌ [TG Fetch] Error fetching {channel} page {pg+1}: {e}")
                break

            results, next_page_param = self.parse_search_results(html, channel, keyword)
            print(f"📄 [TG Fetch] Page {pg+1} returned {len(results)} raw items")

            new_results = [r for r in results if r.unique_id not in seen_ids]
            for r in new_results:
                seen_ids.add(r.unique_id)
            all_results.extend(new_results)

            if not next_page_param or not new_results:
                print(f"🏁 [TG Fetch] No more results for '{channel}' at page {pg+1}")
                break  # No more pages

        return all_results

telegram_searcher = TelegramSearcher()
