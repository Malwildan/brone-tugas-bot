from typing import Final
import asyncio
import signal
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx2
from playwright.async_api import async_playwright

from brone_tugas_bot.brone import LoginFailedError, discover_assignments
from brone_tugas_bot.settings import Settings
from brone_tugas_bot.telegram import (
    TelegramConfig,
    TelegramConfigError,
    format_assignments_message,
    send_telegram_message,
)


class BotError(RuntimeError):
    pass


WIB: Final = ZoneInfo("Asia/Jakarta")
BRONE_OFFLINE_START_HOUR: Final = 0
BRONE_OFFLINE_END_HOUR: Final = 7

def _is_brone_offline(now: datetime) -> bool:
    return BRONE_OFFLINE_START_HOUR <= now.hour < BRONE_OFFLINE_END_HOUR

def _next_online_at(now: datetime) -> datetime:
    target_day = now.date() if now.hour < BRONE_OFFLINE_END_HOUR else now.date() + timedelta(days=1)
    return datetime.combine(target_day, time(BRONE_OFFLINE_END_HOUR), tzinfo=WIB)

async def _wait_until_online(shutdown_event: asyncio.Event) -> None:
    while not shutdown_event.is_set():
        now = datetime.now(WIB)
        if not _is_brone_offline(now):
            return
        wake_at = _next_online_at(now)
        sleep_for = max(60.0, (wake_at - now).total_seconds())
        print(f"[brone] offline until {wake_at.isoformat()}; sleeping {int(sleep_for)}s.", flush=True)
        await asyncio.sleep(sleep_for)


def run_bot(
    *,
    poll_interval: int = 5,
    manual_login: bool = False,
    headless: bool = False,
) -> None:
    settings = Settings()
    try:
        config = TelegramConfig.from_settings(
            token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )
    except TelegramConfigError as error:
        raise BotError(str(error)) from error

    settings.browser_state_dir.mkdir(parents=True, exist_ok=True)

    poll_client = httpx2.Client(
        base_url=f"https://api.telegram.org/bot{settings.telegram_bot_token}",
        timeout=httpx2.Timeout(
            connect=5.0,
            read=float(poll_interval + 10),
            write=10.0,
            pool=10.0,
        ),
        follow_redirects=True,
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            _run_async(
                poll_client=poll_client,
                poll_interval=poll_interval,
                config=config,
                settings=settings,
                manual_login=manual_login,
                headless=headless,
            )
        )
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        poll_client.close()


async def _run_async(
    *,
    poll_client: httpx2.Client,
    poll_interval: int,
    config: TelegramConfig,
    settings: Settings,
    manual_login: bool,
    headless: bool,
) -> None:
    shutdown_event = asyncio.Event()

    def request_shutdown(*args):
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGINT, request_shutdown)
        loop.add_signal_handler(signal.SIGTERM, request_shutdown)

    browser_context = None
    page = None

    await _wait_until_online(shutdown_event)
    async with async_playwright() as playwright:
        browser_context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(settings.browser_state_dir),
            headless=headless,
        )
        page = browser_context.pages[0] if browser_context.pages else await browser_context.new_page()
        await _ensure_logged_in(page, settings=settings, manual_login=manual_login)

        update_id: int | None = None

        while not shutdown_event.is_set():
            offset_param = {"offset": update_id + 1} if update_id is not None else {}
            try:
                response = poll_client.get("/getUpdates", params=offset_param)
                response.raise_for_status()
            except httpx2.HTTPError:
                await asyncio.sleep(poll_interval)
                continue

            data: dict = response.json()
            if not data.get("ok"):
                await asyncio.sleep(poll_interval)
                continue

            for update in data.get("result", []):
                if shutdown_event.is_set():
                    break
                update_id = update["update_id"]
                message: dict = update.get("message", {})
                if not message:
                    continue
                text = message.get("text", "").strip()
                if not text:
                    continue
                chat_id = str(message.get("chat", {}).get("id", ""))
                if chat_id != config.chat_id:
                    continue
                await _handle_message(text, page, config, settings, manual_login=manual_login)

    if browser_context is not None:
        await browser_context.close()


async def _ensure_logged_in(page, *, settings: Settings, manual_login: bool) -> None:
    await page.goto(settings.brone_url, wait_until="domcontentloaded")
    if await page.locator("#username").count() == 0:
        return
    if manual_login:
        await page.wait_for_url(lambda url: "brone.ub.ac.id" in url, timeout=300_000)
        return
    await page.locator("#username").fill(settings.brone_username)
    await page.locator("#password").fill(settings.brone_password)
    await page.locator("#kc-login").click()
    await page.wait_for_load_state("domcontentloaded")
    if await page.locator("#username").count() > 0:
        raise BotError("Login still shows UB Auth. Use --manual-login or check credentials.")


async def _handle_message(
    text: str,
    page,
    config: TelegramConfig,
    settings: Settings,
    *,
    manual_login: bool,
    headless: bool,
) -> None:
    command = text.split()[0].lower()

    if command == "/start":
        await _send_telegram_async(
            "Welcome! I'm your BRONE assignment bot.\n"
            "Use /tugas to check for pending assignments.\n"
            "Use /help to see all commands.",
            config,
        )
        return

    if command == "/help":
        await _send_telegram_async(
            "Available commands:\n"
            "/start - Welcome message\n"
            "/tugas - Check pending assignments\n"
            "/help - Show this message",
            config,
        )
        return

    if command == "/tugas":
        if _is_brone_offline(datetime.now(WIB)):
            wake_at = _next_online_at(datetime.now(WIB))
            await _send_telegram_async(
                f"BRONE is offline until {wake_at.strftime('%H:%M WIB')}.",
                config,
            )
            return
        try:
            # Run sync playwright code in thread pool to avoid asyncio loop conflict
            assignments = await asyncio.to_thread(
                discover_assignments,
                settings,
                now=datetime.now(ZoneInfo("Asia/Jakarta")),
                lookahead_days=60,
                manual_login=manual_login,
                headless=headless,
            )
            await _send_telegram_async(format_assignments_message(assignments), config)
        except LoginFailedError as error:
            await _send_telegram_async(f"Login failed: {error}", config)
        except Exception as error:
            await _send_telegram_async(f"Error fetching assignments: {error}", config)
        return

    await _send_telegram_async(
        "Unknown command. Use /help to see available commands.",
        config,
    )


async def _send_telegram_async(text: str, config: TelegramConfig) -> None:
    payload = {
        "chat_id": config.chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    async with httpx2.AsyncClient(
        base_url=f"https://api.telegram.org/bot{config.bot_token}",
        timeout=httpx2.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0),
        follow_redirects=True,
    ) as client:
        response = await client.post("/sendMessage", json=payload)
        response.raise_for_status()