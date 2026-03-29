import aiohttp
import asyncio
from typing import List, Dict, Any, Optional
import re
import json

# Platform-specific dead message patterns (for Baidu and others)
PATTERNS = {
    "baidu": ["分享人已取消分享", "啊哦，来晚了", "你所访问的页面不存在了", "链接不存在", "分享的文件已被取消", "分享链接已失效", "给出的链接无效", "已经过期", "侵权"],
    "aliyun": ["该分享已过期", "分享已取消", "链接不存在", "已被取消分享", "已失效"],
    "common": ["失效", "不存在", "取消", "删除", "过期", "404", "无效"]
}

class LinkValidator:
    def __init__(self, proxy: str = None):
        self.proxy = proxy
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://pan.quark.cn/",
        }

    async def _check_quark(self, session: aiohttp.ClientSession, url: str, timeout: int = 3) -> bool:
        """Special check for Quark using their internal API.
        
        Returns:
            True  = link is valid OR we cannot determine (timeout/network error)
            False = Quark API explicitly confirmed the link is dead
        """
        try:
            # Extract pwd_id from URL: https://pan.quark.cn/s/a500126895e7
            match = re.search(r"/s/([a-zA-Z0-9]+)", url)
            if not match:
                return False
            pwd_id = match.group(1)
            
            api_url = f"https://drive-h.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc"
            payload = {
                "pwd_id": pwd_id,
                "passcode": "",
                "support_visit_limit_private_share": True
            }
            
            ct = aiohttp.ClientTimeout(total=timeout)
            async with session.post(api_url, json=payload, headers=self.headers, proxy=self.proxy, timeout=ct) as resp:
                if resp.status in [403, 429]:
                    # Rate limited — can't verify, assume valid
                    return True
                if resp.status == 404:
                    # Quark explicitly says: link does not exist
                    return False
                if resp.status != 200:
                    # Unexpected HTTP status — can't determine, assume valid
                    return True
                
                data = await resp.json()
                # Status 200 and code 0 means confirmed valid
                if data.get("status") == 200 and data.get("code") == 0:
                    return True
                # Quark API explicitly says this share is invalid/expired
                return False
        except (asyncio.TimeoutError, aiohttp.ServerTimeoutError):
            # Timeout ≠ invalid! On overseas servers, Quark API is slow.
            # Cannot determine validity, so assume valid.
            return True
        except (aiohttp.ClientError, OSError):
            # Network error — can't reach Quark API, assume valid
            return True
        except Exception:
            # Unexpected error — err on the side of showing the link
            return True

    async def check_link(self, session: aiohttp.ClientSession, url: str, timeout: int = 3) -> bool:
        """Return True if link is likely valid, False if dead. Focused on Quark."""
        try:
            # Detect platform
            if "pan.quark.cn" in url:
                return await self._check_quark(session, url, timeout=timeout)
            
            # Reject other platforms to save time and focus on Quark
            # print(f"🛡️ [Validator] Skipping non-Quark link: {url}")
            return False
            
        except Exception:
            return False

    async def filter_links(self, links: List[Dict[str, Any]], timeout: int = 3) -> List[Dict[str, Any]]:
        """Validate a list of links concurrently and return only valid ones."""
        if not links:
            return []
        
        semaphore = asyncio.Semaphore(30)
        
        async def sem_check(session, link):
            async with semaphore:
                # print(f"DEBUG: Checking {link['url']}...")
                res = await self.check_link(session, link['url'], timeout=timeout)
                # if not res: print(f"DEBUG: DEAD -> {link['url']}")
                return res

        async with aiohttp.ClientSession() as session:
            tasks = [sem_check(session, l) for l in links]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
        valid_indices = [i for i, ok in enumerate(results) if ok is True]
        print(f"🛡️ [Validator] {len(valid_indices)}/{len(links)} links passed validation")
        return [links[i] for i in valid_indices]

link_validator = LinkValidator()
