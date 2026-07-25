#!/usr/bin/env python3
"""Create the Telegram user session used by the VPS harvester."""

import asyncio
import os
from pathlib import Path

import qrcode
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()


async def main() -> None:
    session = os.getenv("TELEGRAM_SESSION", "data/telegram-harvester")
    Path(session).parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(
        session,
        int(os.environ["TELEGRAM_API_ID"]),
        os.environ["TELEGRAM_API_HASH"],
    )
    await client.connect()
    if await client.is_user_authorized():
        print("TELEGRAM_AUTHORIZED", flush=True)
        await client.disconnect()
        return
    login = await client.qr_login()
    qrcode.make(login.url).save("/tmp/telegram-login.png")
    print("TELEGRAM_QR_READY", flush=True)
    await login.wait(timeout=180)
    print("TELEGRAM_AUTHORIZED", flush=True)
    await client.disconnect()


asyncio.run(main())
