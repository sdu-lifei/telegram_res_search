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

    async def _check_quark(self, session: aiohttp.ClientSession, url: str, timeout: int = 6) -> bool:
        """Special check for Quark using their internal API."""
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
            
            async with session.post(api_url, json=payload, headers=self.headers, proxy=self.proxy, timeout=timeout) as resp:
                if resp.status in [403, 429]:
                    print(f"🛡️ [Validator] Quark API rate limited ({resp.status}). Assuming valid for {url}")
                    return True
                if resp.status != 200:
                    # 404 is common for dead links in this API
                    return False
                
                data = await resp.json()
                # Status 200 and code 0 means valid
                if data.get("status") == 200 and data.get("code") == 0:
                    return True
                return False
        except Exception:
            return False

    async def _check_aliyun(self, session: aiohttp.ClientSession, url: str, timeout: int = 6) -> bool:
        """Robust check for Aliyun using their anonymous share API."""
        try:
            # Extract share_id
            match = re.search(r"/s/([a-zA-Z0-9]+)", url)
            if not match:
                return False
            share_id = match.group(1)
            
            api_url = f"https://api.aliyundrive.com/adrive/v3/share_link/get_share_by_anonymous?share_id={share_id}"
            payload = {"share_id": share_id}
            
            async with session.post(api_url, json=payload, headers=self.headers, proxy=self.proxy, timeout=timeout) as resp:
                if resp.status == 404:
                    return False
                if resp.status in [403, 429]:
                    # Rate limited or IP blocked. Don't mark as dead, assume valid to be safe.
                    print(f"🛡️ [Validator] Aliyun API rate limited ({resp.status}). Assuming valid for {url}")
                    return True
                if resp.status != 200:
                    return False
                
                data = await resp.json()
                if data.get("code") == "NotFound.ShareLink":
                    return False
                # If we have a file_id or other share info, it's definitely valid
                if data.get("share_name") or data.get("creator_id"):
                    return True
                return False
        except Exception as e:
            # print(f"DEBUG: Aliyun API Error: {e}")
            return False # Strict Fail-Close for other errors

    async def check_link(self, session: aiohttp.ClientSession, url: str, timeout: int = 6) -> bool:
        """Return True if link is likely valid, False if dead."""
        is_valid = False
        try:
            # Detect platform
            if "pan.quark.cn" in url:
                is_valid = await self._check_quark(session, url, timeout=timeout)
            
            elif "aliyundrive.com" in url or "alipan.com" in url:
                is_valid = await self._check_aliyun(session, url, timeout=timeout)
            
            else:
                # For Baidu and others, use HTML pattern matching
                platform = "common"
                referer = "https://www.google.com"
                if "pan.baidu.com" in url:
                    platform = "baidu"
                    referer = "https://pan.baidu.com/"

                headers = self.headers.copy()
                headers["Referer"] = referer

                async with session.get(url, headers=headers, proxy=self.proxy, timeout=timeout) as response:
                    if response.status == 404:
                        is_valid = False
                    elif response.status >= 400 and platform != "baidu":
                        is_valid = False
                    else:
                        text = await response.text()
                        is_valid = True
                        for p in PATTERNS.get(platform, PATTERNS["common"]):
                            if p in text:
                                is_valid = False
                                break
            
            if not is_valid:
                print(f"🛡️ [Validator] DEAD -> {url}")
            return is_valid
        except Exception as e:
            # print(f"🛡️ [Validator] ERR checking {url}: {e}")
            return False

    async def filter_links(self, links: List[Dict[str, Any]], timeout: int = 6) -> List[Dict[str, Any]]:
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
