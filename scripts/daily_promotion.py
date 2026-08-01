#!/usr/bin/env python3
"""Publish one compliant, non-duplicate guide promotion per day.

The script uses only official APIs and Python's standard library. It is
designed to be scheduled by n8n, but can also be run directly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree


SITE_URL = "https://panss.dpdns.org"
STATE_PATH = "~/.local/state/pansou/daily-promotion.json"
USER_AGENT = "PanSouDailyPromotion/1.0 (+https://panss.dpdns.org/about)"

ANGLES = {
    "public-cloud-link-safety-checklist": [
        "公开链接能打开，不代表内容安全或具备转载授权。打开前先按这份清单核对。",
        "收到陌生网盘链接，先别急着下载：来源、授权和文件类型都值得检查。",
        "分享链接是否失效只是第一关。这份清单还覆盖来源与安全边界。",
        "今天的实用提醒：先检查公开分享链接，再决定是否访问或下载。",
        "把风险检查放在搜索之前，能减少误点和不必要的下载。",
        "公开可见不等于可以随意转载。这里整理了一份打开链接前的检查步骤。",
        "如果你经常接收网盘链接，可以保存这份简明安全检查清单。",
    ],
    "cloud-search-keyword-guide": [
        "搜不到资料时，先补全名称、年份和常见别名，通常比堆很多关键词更清楚。",
        "同名作品很多？把年份、季数或作者加入搜索词，结果更容易核对。",
        "网盘搜索不是关键词越多越好。先写完整名称，再补一个区分信息。",
        "今天分享一个搜索小技巧：完整名称 + 年份 + 别名，分步尝试。",
        "搜索结果太杂时，先检查关键词是否包含可验证的名称和年份。",
        "片名、书名或课程名有别名时，分别搜索往往比一次塞进所有词更实用。",
        "这份指南整理了网盘资源搜索词的写法和常见误区。",
    ],
    "shared-files-organization-guide": [
        "分享资料前，清楚的命名、目录、说明和更新时间，比一串模糊文件名更有用。",
        "让接收者快速判断内容：文件名写清主题，目录保持一致，再补更新时间。",
        "资料分享体验常被命名细节拖累。这份指南给出可直接照做的整理方法。",
        "今天整理一份分享前检查：名称、目录、说明、更新时间。",
        "公开分享资料时，先把内容说明和使用边界写清楚。",
        "如果一个文件夹需要别人反复询问“这是什么”，说明命名还可以改进。",
        "这份指南适合在创建公开分享链接之前快速过一遍。",
    ],
    "how-to-search-public-cloud-resources-legally": [
        "公开可见不等于获得下载、转载或再分发授权。搜索时先确认使用边界。",
        "使用公开索引时，来源、授权和用途都需要由使用者自行核对。",
        "合规搜索的重点不是绕过限制，而是只使用公开、合法且有权访问的内容。",
        "今天分享一份公开网盘资料搜索的合规使用说明。",
        "找到链接只是开始：访问和使用前仍要确认版权、隐私与平台规则。",
        "搜索工具只提供公开索引，不托管文件，也不能替代授权判断。",
        "这份指南说明了公开资料搜索可以做什么，以及不应该做什么。",
    ],
}


class MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.description = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() == "meta":
            name = (values.get("name") or values.get("property") or "").lower()
            if name in {"description", "og:description"} and not self.description:
                self.description = (values.get("content") or "").strip()

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    merged = {"User-Agent": USER_AGENT, **(headers or {})}
    if body is not None:
        merged.setdefault("Content-Type", "application/json")
    request = Request(url, data=body, headers=merged, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"request failed for {url}: {exc.reason}") from exc


def request_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=20) as response:
            return response.read().decode(errors="replace")
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"unable to fetch {url}: {exc}") from exc


def guide_urls(site_url: str) -> list[str]:
    root = ElementTree.fromstring(request_text(f"{site_url.rstrip('/')}/sitemap.xml"))
    urls = []
    for element in root.findall(".//{*}loc"):
        url = (element.text or "").strip()
        path = urlparse(url).path.rstrip("/")
        if path.startswith("/guides/") and path.count("/") == 2:
            urls.append(url)
    if not urls:
        raise RuntimeError("sitemap contains no promotable guide pages")
    return urls


def page_meta(url: str) -> dict[str, str]:
    parser = MetaParser()
    parser.feed(request_text(url))
    title = " ".join(parser.title.split()).removesuffix(" | 盘搜").strip()
    if not title:
        title = urlparse(url).path.rsplit("/", 1)[-1].replace("-", " ")
    return {"url": url, "title": title, "description": " ".join(parser.description.split())}


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"delivered": {}}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid promotion state file {path}: {exc}") from exc
    data.setdefault("delivered", {})
    return data


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def configured_channels() -> list[str]:
    channels = []
    if os.getenv("BLUESKY_HANDLE") and os.getenv("BLUESKY_APP_PASSWORD"):
        channels.append("bluesky")
    if os.getenv("MASTODON_BASE_URL") and os.getenv("MASTODON_ACCESS_TOKEN"):
        channels.append("mastodon")
    if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHANNEL_ID"):
        channels.append("telegram")
    if os.getenv("DISCORD_WEBHOOK_URL"):
        channels.append("discord")
    return channels


def campaigns(urls: list[str]) -> list[dict[str, str]]:
    result = []
    for url in urls:
        slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
        angles = ANGLES.get(slug, ["今天分享一份可核对来源与使用边界的实用指南。"])
        for index, angle in enumerate(angles, start=1):
            result.append({"id": f"{slug}:{index}", "url": url, "angle": angle})
    return result


def choose_campaign(
    available: list[dict[str, str]], state: dict[str, Any], channels: list[str]
) -> tuple[dict[str, str], list[str]]:
    delivered = state["delivered"]
    for campaign in available:
        sent = delivered.get(campaign["id"], {})
        missing = [channel for channel in channels if channel not in sent]
        if missing:
            return campaign, missing

    def oldest(campaign: dict[str, str]) -> str:
        sent = delivered.get(campaign["id"], {})
        return min((entry["sent_at"] for entry in sent.values()), default="")

    campaign = min(available, key=oldest)
    return campaign, channels


def tracking_url(url: str, channel: str) -> str:
    parsed = urlparse(url)
    query = dict(item.split("=", 1) for item in parsed.query.split("&") if "=" in item)
    query.update(
        {
            "utm_source": channel,
            "utm_medium": "social",
            "utm_campaign": "daily_guide",
        }
    )
    return urlunparse(parsed._replace(query=urlencode(query)))


def message(meta: dict[str, str], angle: str, url: str, limit: int) -> str:
    suffix = f"\n\n{meta['title']}\n{url}\n#网盘搜索 #资料整理"
    room = max(0, limit - len(suffix))
    intro = angle if len(angle) <= room else angle[: max(0, room - 1)] + "…"
    return f"{intro}{suffix}"


def post_bluesky(text: str, link: str) -> str:
    service = os.getenv("BLUESKY_SERVICE", "https://bsky.social").rstrip("/")
    session = request_json(
        f"{service}/xrpc/com.atproto.server.createSession",
        method="POST",
        payload={
            "identifier": os.environ["BLUESKY_HANDLE"],
            "password": os.environ["BLUESKY_APP_PASSWORD"],
        },
    )
    start = text.index(link)
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "langs": ["zh"],
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "facets": [
            {
                "index": {
                    "byteStart": len(text[:start].encode()),
                    "byteEnd": len(text[: start + len(link)].encode()),
                },
                "features": [{"$type": "app.bsky.richtext.facet#link", "uri": link}],
            }
        ],
    }
    result = request_json(
        f"{service}/xrpc/com.atproto.repo.createRecord",
        method="POST",
        headers={"Authorization": f"Bearer {session['accessJwt']}"},
        payload={
            "repo": session["did"],
            "collection": "app.bsky.feed.post",
            "record": record,
        },
    )
    rkey = result["uri"].rsplit("/", 1)[-1]
    return f"https://bsky.app/profile/{session['handle']}/post/{rkey}"


def post_mastodon(text: str, campaign_id: str) -> str:
    base_url = os.environ["MASTODON_BASE_URL"].rstrip("/")
    payload = urlencode({"status": text, "visibility": "public", "language": "zh"}).encode()
    request = Request(
        f"{base_url}/api/v1/statuses",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {os.environ['MASTODON_ACCESS_TOKEN']}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Idempotency-Key": hashlib.sha256(campaign_id.encode()).hexdigest(),
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode())["url"]
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"Mastodon HTTP {exc.code}: {detail}") from exc


def post_telegram(text: str) -> str | None:
    result = request_json(
        f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
        method="POST",
        payload={
            "chat_id": os.environ["TELEGRAM_CHANNEL_ID"],
            "text": text,
            "link_preview_options": {"is_disabled": False},
        },
    )
    if not result.get("ok"):
        raise RuntimeError(f"Telegram rejected message: {result}")
    chat_id = os.environ["TELEGRAM_CHANNEL_ID"]
    if chat_id.startswith("@"):
        return f"https://t.me/{chat_id[1:]}/{result['result']['message_id']}"
    return None


def post_discord(text: str) -> str | None:
    separator = "&" if "?" in os.environ["DISCORD_WEBHOOK_URL"] else "?"
    result = request_json(
        f"{os.environ['DISCORD_WEBHOOK_URL']}{separator}wait=true",
        method="POST",
        payload={"content": text, "allowed_mentions": {"parse": []}},
    )
    if result.get("guild_id") and result.get("channel_id") and result.get("id"):
        return (
            f"https://discord.com/channels/{result['guild_id']}/"
            f"{result['channel_id']}/{result['id']}"
        )
    return None


POSTERS = {
    "bluesky": lambda text, link, campaign_id: post_bluesky(text, link),
    "mastodon": lambda text, link, campaign_id: post_mastodon(text, campaign_id),
    "telegram": lambda text, link, campaign_id: post_telegram(text),
    "discord": lambda text, link, campaign_id: post_discord(text),
}


def run(args: argparse.Namespace) -> dict[str, Any]:
    site_url = os.getenv("PROMOTION_SITE_URL", SITE_URL).rstrip("/")
    state_path = Path(args.state or os.getenv("PROMOTION_STATE_PATH", STATE_PATH)).expanduser()
    channels = configured_channels()
    dry_run = not args.live
    selection_channels = channels or (["bluesky", "mastodon", "telegram"] if dry_run else [])
    if not selection_channels:
        raise RuntimeError("no channel credentials configured; refusing a live run")

    state = load_state(state_path)
    campaign, targets = choose_campaign(campaigns(guide_urls(site_url)), state, selection_channels)
    meta = page_meta(campaign["url"])
    results = []
    for channel in targets:
        link = tracking_url(meta["url"], channel)
        limit = 300 if channel == "bluesky" else 480
        text = message(meta, campaign["angle"], link, limit)
        if dry_run or channel not in channels:
            results.append(
                {"channel": channel, "status": "preview", "text": text, "public_url": None}
            )
            continue
        try:
            public_url = POSTERS[channel](text, link, campaign["id"])
            sent_at = datetime.now(timezone.utc).isoformat()
            state["delivered"].setdefault(campaign["id"], {})[channel] = {
                "sent_at": sent_at,
                "public_url": public_url,
                "target_url": link,
            }
            results.append(
                {"channel": channel, "status": "published", "public_url": public_url}
            )
        except Exception as exc:  # keep other owned channels running
            results.append({"channel": channel, "status": "failed", "error": str(exc)})

    if not dry_run:
        save_state(state_path, state)
    return {
        "mode": "dry-run" if dry_run else "live",
        "campaign_id": campaign["id"],
        "source_url": meta["url"],
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="publish through configured APIs")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument("--state", help="override the state file path")
    args = parser.parse_args()
    try:
        result = run(args)
    except Exception as exc:
        result = {"status": "failed", "error": str(exc)}
        print(json.dumps(result, ensure_ascii=False) if args.json else result["error"], file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
    return 1 if any(item["status"] == "failed" for item in result["results"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
