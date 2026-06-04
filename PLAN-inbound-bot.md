# Plan: Add Persistent Telegram Bot with `/tugas` Command

## Problem
The current project is a one-shot CLI script — it only sends outgoing Telegram messages. It never reads incoming messages, so typing `/tugas` in Telegram does nothing.

## Approach
Add a new `bot` Typer subcommand that starts a long-running polling loop. Keep the existing `sync` command untouched. Reuse existing `httpx2`, `playwright`, `brone.py`, `telegram.py`, and `models.py` — no new dependencies.

---

## What Changes

### 1. `src/brone_tugas_bot/bot.py` — **New file** (the persistent bot)

Core polling loop using `httpx2` (no new deps):
- **Long-poll `getUpdates`** with `offset` tracking to avoid reprocessing
- **Parse message text** for commands:
  - `/start` → welcome message
  - `/tugas` → call `discover_assignments()` from `brone.py`, format via `format_assignments_message()`, reply via `sendMessage`
  - `/help` → list commands
  - unknown → hint to use `/help`
- **Create Playwright browser context once** at startup, reuse across `/tugas` calls, close on shutdown
- **Only reply to `TELEGRAM_CHAT_ID`** from `.env` — unknown chats ignored silently
- **Graceful shutdown** — trap SIGINT/SIGTERM, close browser + client
- **Error resilience** — per-scrape failures return error message to chat but don't crash the loop

### 2. `src/brone_tugas_bot/telegram.py` — **Modify**

Add a generic `send_telegram_message(text: str, config: TelegramConfig) -> None` function, extracted from the existing `send_assignments_to_telegram()`. The bot needs this for `/start`/`/help`/error replies that aren't assignment lists.

### 3. `src/brone_tugas_bot/cli.py` — **Modify**

Add a `bot` Typer subcommand:
```
brone-tugas bot [--poll-interval 5] [--manual-login] [--headless]
```
Existing `sync` command untouched.

---

## Data Flow

```
cli.py `bot` subcommand
  └─ bot.py `run_bot()`
       ├─ Creates Playwright context (once)
       ├─ Creates httpx2 Telegram client (once)
       ├─ Loop:
       │    ├─ GET getUpdates(offset=last_update_id+1)
       │    ├─ For each message with /tugas from authorized chat:
       │    │    ├─ discover_assignments()  (reuses brone.py)
       │    │    ├─ format_assignments_message() (reuses telegram.py)
       │    │    └─ sendMessage back
       │    └─ Sleep(poll_interval)
       └─ On signal: close context, close client
```

## Edge Cases Covered

- **Browser session persists** — Playwright persistent context means credentials stay cached across `/tugas` calls (one browser at a time)
- **Only authorized chat** — messages from unknown chats silently dropped
- **Scrape failure** — error msg sent back to chat, loop continues
- **Ctrl+C** — clean shutdown, no orphaned browser processes
- **Existing sync users** — zero impact, additive change only

## Files Changed

| File | Action |
|---|---|
| `src/brone_tugas_bot/bot.py` | **Create** — polling loop, command routing, Playwright lifecycle |
| `src/brone_tugas_bot/cli.py` | **Edit** — add `bot` subcommand |
| `src/brone_tugas_bot/telegram.py` | **Edit** — add `send_telegram_message()` helper |
