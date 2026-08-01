import hashlib
import time
import asyncio
import xml.etree.ElementTree as ET
from urllib.parse import quote
from fastapi import APIRouter, Request, BackgroundTasks, Query, Response
from pansou_py.core.config import settings
from pansou_py.core.search import search_service
from pansou_py.models.database import Resource, async_session
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


async def _format_transferred_results(keyword: str, resource_ids: list[int]) -> tuple[str, int]:
    """Format owner-generated Quark shares for WeChat."""
    if not resource_ids:
        return f"😔 未找到「{keyword}」相关资源\n\n可换完整剧名、年份或英文名再试。", 0

    rows = await _load_resources(resource_ids)
    ready = [row for row in rows if row.owner_share_url]
    if not ready:
        return (
            f"🔍「{keyword}」已找到资源。\n\n"
            f"打开搜索页查看全部结果：\n{_search_page_url(keyword)}",
            0,
        )

    row = ready[0]
    title = _short_title(row.title or keyword)
    lines = [f"「{keyword}」资源链接：", "", title, row.owner_share_url]
    if row.owner_share_password:
        lines.append(f"密码：{row.owner_share_password}")

    return "\n".join(lines), 1


def _extract_resource_ids(results_data: dict, limit: int = 3) -> list[int]:
    seen: set[int] = set()
    resource_ids: list[int] = []

    for result in results_data.get("results") or []:
        for link in result.get("links") or []:
            resource_id = link.get("resource_id")
            if isinstance(resource_id, int) and resource_id not in seen:
                seen.add(resource_id)
                resource_ids.append(resource_id)
            if len(resource_ids) >= limit:
                return resource_ids

    for links in (results_data.get("merged_by_type") or {}).values():
        for link in links:
            resource_id = link.get("resource_id")
            if isinstance(resource_id, int) and resource_id not in seen:
                seen.add(resource_id)
                resource_ids.append(resource_id)
            if len(resource_ids) >= limit:
                return resource_ids

    return resource_ids


def _prioritize_wechat_resource_ids(resources: list[Resource], limit: int = 8) -> list[int]:
    def rank(row: Resource) -> tuple[int, int]:
        if row.owner_share_url:
            status_rank = 0
        elif row.transfer_status == "failed":
            status_rank = 2
        else:
            status_rank = 1
        return (status_rank, -(row.id or 0))

    return [row.id for row in sorted(resources, key=rank)[:limit] if row.id]


async def _load_resources(resource_ids: list[int]) -> list[Resource]:
    if not resource_ids:
        return []

    async with async_session() as session:
        rows = []
        for resource_id in resource_ids:
            row = await session.get(Resource, resource_id)
            if row:
                rows.append(row)
        return rows


def _short_title(title: str, max_len: int = 36) -> str:
    title = " ".join(title.split())
    if len(title) <= max_len:
        return title
    return title[:max_len - 1] + "…"


def _search_page_url(keyword: str) -> str:
    path = "/search"
    base = settings.PUBLIC_BASE_URL.rstrip("/") if settings.PUBLIC_BASE_URL else ""
    return f"{base}{path}?kw={quote(keyword)}"


# ──────────────────────────────────────────────────────────────────────────────
# Background search task (Silent caching)
# ──────────────────────────────────────────────────────────────────────────────

async def _do_search_and_cache(keyword: str):
    """Background task to fetch more results and enrich the local DB."""
    try:
        # Deep search: 5 pages
        # This will automatically validate and save results to the local database
        await search_service.search(keyword=keyword, max_pages=5, force_refresh=True)
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
        # Fast search first; deeper search continues after the passive reply.
        return await search_service.search(
            keyword=keyword, max_pages=1, max_results=3,
            cloud_types=["quark"], tg_timeout=1.5
        )

    try:
        results_data = await asyncio.wait_for(get_results(), timeout=3.0)
        
        if results_data.get("total", 0) > 0:
            candidate_resources = await _load_resources(_extract_resource_ids(results_data, limit=8))
            resource_ids = _prioritize_wechat_resource_ids(candidate_resources, limit=8)
            reply, ready_count = await _format_transferred_results(keyword, resource_ids)
            background_tasks.add_task(_do_search_and_cache, keyword)
        else:
            reply = (
                f"😔 暂时未搜到「{keyword}」，后台已开始深度搜寻。\n\n"
                f"打开搜索页查看：\n{_search_page_url(keyword)}\n\n"
                f"也可以换完整名称、年份再试。"
            )
            background_tasks.add_task(_do_search_and_cache, keyword)
            
    except asyncio.TimeoutError:
        # Search timed out, notify user to try same keyword later
        reply = (
            f"⏳「{keyword}」正在搜寻中，后台会继续深度搜索。\n\n"
            f"打开搜索页查看：\n{_search_page_url(keyword)}\n\n"
            f"也可以换完整名称、年份再试。"
        )
        background_tasks.add_task(_do_search_and_cache, keyword)
    except Exception as e:
        reply = f"⚠️ 搜「{keyword}」时出错了，请稍后再试。"

    return Response(content=_build_text_reply(openid, gh_id, reply), media_type="application/xml")
