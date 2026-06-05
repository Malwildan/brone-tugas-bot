# BRONE Tugas Bot

This CLI opens `https://brone.ub.ac.id/my/`, logs in through UB Auth, searches for assignment-like items with deadlines, opens each assignment detail page, and sends the result to Telegram.

## Setup

1. Copy `.env.example` to `.env`, then fill in:
   - `BRONE_USERNAME`
   - `BRONE_PASSWORD`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
2. Install and prepare the browser:

```powershell
uv sync
uv run playwright install chromium
```

## Run

First test without sending a Telegram message:

```powershell
uv run brone-tugas --dry-run
```

Send assignments to Telegram:

```powershell
uv run brone-tugas
```

Useful options:

```powershell
uv run brone-tugas --manual-login --dry-run
uv run brone-tugas --lookahead-days 90
uv run brone-tugas --no-telegram --dry-run
uv run brone-tugas export-profile
```

`--manual-login` opens the browser and lets you complete login yourself. That is useful if UB Auth asks for MFA, captcha, or a one-time prompt. The browser session is stored under `.brone-browser-state/` so later runs can reuse it.

## Notes

BRONE redirects to UB Auth before the dashboard. I verified the login page fields are `#username`, `#password`, and `#kc-login`.

Assignment discovery uses BRONE's Moodle upcoming-events page, then opens each `/mod/assign/view.php` detail page to collect course, opened date, due date, description, submission status, grading status, and time remaining.

If a bot token was pasted into a chat, regenerate it with BotFather and put only the new token in `.env`.

## Railway with a Local Browser Profile

Railway may be blocked by UB IAM / Cloudflare before login. To try the same browser trust state as local, export the local Chromium profile:

```powershell
uv run brone-tugas export-profile
```

This writes `brone-browser-state.tar.gz`, which contains account session material. Keep it private and do not commit it. Upload it somewhere private with a direct download URL, then set this Railway variable:

```text
BRONE_BROWSER_STATE_ARCHIVE_URL=<private direct-download URL>
```

On startup, the bot restores that archive into `.brone-browser-state/` before opening Chromium. This may still fail if UB/Cloudflare binds verification to Railway's IP or runtime fingerprint.
