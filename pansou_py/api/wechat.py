import hashlib
import time
import asyncio
import xml.etree.ElementTree as ET
from typing import Optional
from fastapi import APIRouter, Request, BackgroundTasks, Query, Response
from pansou_py.core.config import settings
from pansou_py.core.cache import cache_service
from pansou_py.core.search import search_service
from pansou_py.utils.validator import link_validator

# Configure validator with proxy if available
link_validator.proxy = settings.PROXY

router = APIRouter()

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _verify_signature(signature: str, timestamp: str, nonce: str) -> bool:
    """Verify WeChat webhook signature."""
    items = sorted([settings.WECHAT_TOKEN, timestamp, nonce])
    sha1 = hashlib.sha1("".join(items).encode()).hexdigest()
    return sha1 == signature


def _parse_xml(body: bytes) -> dict:
    """Parse WeChat XML message into dict."""
    root = ET.fromstring(body)
    return {child.tag: (child.text or "") for child in root}


def _build_text_reply(to_user: str, from_user: str, content: str) -> str:
    """Build WeChat text reply XML."""
    ts = int(time.time())
    return (
        f"<xml>"
        f"<ToUserName><![CDATA[{to_user}]]></ToUserName>"
        f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
        f"<CreateTime>{ts}</CreateTime>"
        f"<MsgType><![CDATA[text]]></MsgType>"
        f"<Content><![CDATA[{content}]]></Content>"
        f"</xml>"
    )


def _format_results(results_data: dict, keyword: str) -> str:
    """Format search results into WeChat-friendly text."""
    merged = results_data.get("merged_by_type", {})
    total = results_data.get("total", 0)

    if total == 0 or not merged:
        return f"😔 未找到「{keyword}」相关资源\n\n💡 试试：完整名称、英文名或年份"

    lines = [f"🔍「{keyword}」找到 {total} 条结果\n"]
    count = 0

    for disk_type, links in merged.items():
        for item in links:
            if count >= 10:
                break
            count += 1
            note = item.get("note", "")
            url = item.get("url", "")
            pwd = item.get("password", "")
            icon = {
                "baidu": "🔵", "quark": "🟠", "aliyun": "🟢",
                "uc": "🟣", "xunlei": "⚡", "123": "🔴",
            }.get(disk_type, "📦")

            lines.append(f"{count}. {note}")
            lines.append(f"  {icon} {disk_type}网盘: {url}")
            if pwd:
                lines.append(f"  🔑 密码: {pwd}")
            lines.append("")

    if total > 10:
        lines.append(f"注：仅显示验证有效的最近 10 条结果")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Background search task (Silent caching)
# ──────────────────────────────────────────────────────────────────────────────

async def _do_search_and_cache(keyword: str):
    """Background task to fetch more results and enrich the local DB."""
    try:
        # Deep search: 5 pages
        # This will automatically validate and save results to the local database
        await search_service.search(keyword=keyword, max_pages=5)
    except:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/wechat")
async def wechat_verify(
    signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
):
    if not settings.WECHAT_TOKEN:
        return Response(content="Missing Config")
    if _verify_signature(signature, timestamp, nonce):
        return Response(content=echostr, media_type="text/plain")
    return Response(content="Forbidden", status_code=403)


@router.post("/wechat")
async def wechat_message(request: Request, background_tasks: BackgroundTasks):
    """Handle WeChat messages synchronously with high priority."""
    if not settings.WECHAT_TOKEN: return Response(content="")

    body = await request.body()
    params = dict(request.query_params)
    if not _verify_signature(params.get("signature", ""), params.get("timestamp", ""), params.get("nonce", "")):
        return Response(content="", status_code=403)

    try:
        msg = _parse_xml(body)
    except:
        return Response(content="")

    msg_type = msg.get("MsgType", "")
    openid = msg.get("FromUserName", "")
    gh_id = msg.get("ToUserName", "")

    if msg_type != "text":
        reply = "📢 请发送资源名称进行搜索，例如：庆余年"
        return Response(content=_build_text_reply(openid, gh_id, reply), media_type="application/xml")

    content = msg.get("Content", "").strip()
    
    # ── Search Handling (Synchronous Priority) ────────────────────────────────
    keyword = content
    # Note: SearchService already handles Database-First logic and re-validation caching.
    
    async def get_results():
        # Fast search (1 page, 5 results max for quick response)
        return await search_service.search(keyword=keyword, max_pages=1, max_results=5)

    try:
        # Wait up to 4.75 seconds to catch the WeChat deadline
        results_data = await asyncio.wait_for(get_results(), timeout=4.75)
        
        if results_data.get("total", 0) > 0:
            reply = _format_results(results_data, keyword)
            # Enrich DB in background if it was just a fast search
            background_tasks.add_task(_do_search_and_cache, keyword)
        else:
            # Reached here but no results found in time
            reply = f"😔 暂时未搜到「{keyword}」，后台已记录并开始深度搜寻...\n\n👉 请过几个小时后再发送「{keyword}」重试。"
            background_tasks.add_task(_do_search_and_cache, keyword)
            
    except asyncio.TimeoutError:
        # Search timed out, notify user to try same keyword later
        reply = f"⏳ 资源「{keyword}」搜寻中，由于请求较多，请过几个小时后再次发送相同关键词获取结果。"
        background_tasks.add_task(_do_search_and_cache, keyword)
    except Exception as e:
        reply = f"⚠️ 搜「{keyword}」时出错了，请稍后再试。"

    return Response(content=_build_text_reply(openid, gh_id, reply), media_type="application/xml")
