import asyncio
import html
import re
from datetime import datetime
from typing import List
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import aiohttp
from bs4 import BeautifulSoup

from pansou_py.models.schemas import Link, SearchResult
from pansou_py.plugins import plugin_manager
from pansou_py.plugins.base import BasePlugin
from pansou_py.utils.link_parser import clean_url, extract_netdisk_links, extract_password, get_link_type


class WebFallbackPlugin(BasePlugin):
    @property
    def name(self) -> str:
        return "web_fallback"

    @property
    def priority(self) -> int:
        return 4

    async def search(self, keyword: str, **kwargs) -> List[SearchResult]:
        urls = await self._search_candidate_pages(keyword)
        if not urls:
            return []

        timeout = aiohttp.ClientTimeout(total=8)
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            tasks = [self._extract_page_result(session, keyword, url) for url in urls[:6]]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        return [result for result in results if isinstance(result, SearchResult) and result.links]

    async def _search_candidate_pages(self, keyword: str) -> List[str]:
        queries = [
            f"{keyword} 夸克网盘",
            f"{keyword} pan.quark.cn/s",
            f"{keyword} 夸克 资源",
        ]
        urls = []
        seen = set()

        timeout = aiohttp.ClientTimeout(total=8)
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            for query in queries:
                search_url = "https://duckduckgo.com/html/?q=" + quote_plus(query)
                try:
                    async with session.get(search_url) as response:
                        if response.status != 200:
                            continue
                        html_text = await response.text()
                except Exception:
                    continue

                for url in self._parse_search_result_urls(html_text):
                    if url not in seen:
                        seen.add(url)
                        urls.append(url)
                    if len(urls) >= 8:
                        return urls

        return urls

    def _parse_search_result_urls(self, html_text: str) -> List[str]:
        soup = BeautifulSoup(html_text, "lxml")
        urls = []
        for anchor in soup.select(".result__a"):
            href = anchor.get("href") or ""
            url = self._unwrap_duckduckgo_url(href)
            if self._is_candidate_url(url):
                urls.append(url)
        return urls

    def _unwrap_duckduckgo_url(self, href: str) -> str:
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlparse(href)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            uddg = parse_qs(parsed.query).get("uddg")
            if uddg:
                return unquote(uddg[0])
        return href

    def _is_candidate_url(self, url: str) -> bool:
        if not url.startswith(("http://", "https://")):
            return False
        blocked = ("pan.quark.cn", "baidu.com", "google.com", "bing.com", "duckduckgo.com")
        return not any(domain in url for domain in blocked)

    async def _extract_page_result(self, session: aiohttp.ClientSession, keyword: str, url: str):
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                body = await response.text(errors="ignore")
        except Exception:
            return None

        title = self._extract_title(body, keyword)
        soup = BeautifulSoup(body, "lxml")
        page_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
        links = self._extract_relevant_links(keyword, body, title, page_text)

        if not links:
            return None

        return SearchResult(
            message_id=str(abs(hash(url))),
            unique_id=f"web_fallback_{abs(hash(url))}",
            channel="web_fallback",
            datetime=datetime.utcnow().isoformat(),
            title=title,
            description=page_text[:1000],
            links=links,
            images=[],
        )

    def _extract_relevant_links(self, keyword: str, body: str, title: str, page_text: str) -> List[Link]:
        text = html.unescape(body)
        raw_urls = [raw_url for raw_url in extract_netdisk_links(text) if get_link_type(raw_url) == "quark"]
        page_has_keyword = self._contains_keyword(keyword, f"{title} {page_text[:2000]}")
        links: List[Link] = []
        seen = set()

        for raw_url in raw_urls:
            link_type = get_link_type(raw_url)
            clean = clean_url(raw_url, link_type)
            if clean in seen:
                continue
            if not self._is_link_relevant(keyword, text, clean, raw_url, page_has_keyword, len(raw_urls)):
                continue
            seen.add(clean)
            links.append(Link(
                type=link_type,
                url=clean,
                password=extract_password(text, clean) or extract_password(page_text, clean),
                work_title=keyword,
            ))
        return links

    def _is_link_relevant(
        self,
        keyword: str,
        text: str,
        clean_url_value: str,
        raw_url: str,
        page_has_keyword: bool,
        quark_link_count: int,
    ) -> bool:
        context = self._link_context(text, raw_url) or self._link_context(text, clean_url_value)
        if context and self._contains_keyword(keyword, context):
            return True

        # Single-link pages are usually dedicated resource pages; allow page-level
        # relevance there, but do not trust generic index pages with many links.
        return quark_link_count == 1 and page_has_keyword

    def _link_context(self, text: str, needle: str, radius: int = 80) -> str:
        idx = text.find(needle)
        if idx < 0:
            return ""
        tag_start = text.rfind(">", 0, idx)
        tag_end = text.find("<", idx + len(needle))
        if tag_start >= 0 and tag_end > idx:
            return text[tag_start + 1:tag_end]
        start = max(idx - radius, 0)
        end = min(idx + len(needle) + radius, len(text))
        return text[start:end]

    def _contains_keyword(self, keyword: str, text: str) -> bool:
        normalized_text = re.sub(r"\s+", "", html.unescape(text)).lower()
        for term in self._keyword_terms(keyword):
            if term and term in normalized_text:
                return True
        return False

    def _keyword_terms(self, keyword: str) -> List[str]:
        compact = re.sub(r"\s+", "", keyword).lower()
        terms = [compact] if compact else []
        terms.extend(
            term.lower()
            for term in re.findall(r"[\w\u4e00-\u9fff]{2,}", keyword)
            if term.lower() not in terms
        )
        return terms

    def _extract_title(self, body: str, keyword: str) -> str:
        soup = BeautifulSoup(body, "lxml")
        if soup.title and soup.title.string:
            return soup.title.string.strip()[:120]
        return keyword


plugin_manager.register(WebFallbackPlugin())
