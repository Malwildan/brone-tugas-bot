from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.table import Table

from brone_tugas_bot.bot import BotError, run_bot
from brone_tugas_bot.brone import LoginFailedError, discover_assignments
from brone_tugas_bot.models import Assignment
from brone_tugas_bot.settings import ROOT_DIR, Settings
from brone_tugas_bot.telegram import (
    TelegramConfig,
    TelegramConfigError,
    TelegramSendError,
    send_assignments_to_telegram,
)

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def sync(
    dry_run: bool = typer.Option(
        default=False,
        help="Print discovered assignments without creating events.",
    ),
    manual_login: bool = typer.Option(
        default=False,
        help="Let you log in manually in the browser.",
    ),
    headless: bool = typer.Option(
        default=False,
        help="Run Chromium without a visible window.",
    ),
    lookahead_days: int = typer.Option(60, min=1, max=365),
    telegram: bool = typer.Option(
        default=True,
        help="Send the discovered assignments to Telegram.",
    ),
    debug_dump_dir: Path | None = typer.Option(
        default=None,
        help="Write raw HTML of scraped pages to this directory for debugging.",
    ),
) -> None:
    settings = Settings()
    try:
        assignments = discover_assignments(
            settings,
            now=datetime.now(ZoneInfo("Asia/Jakarta")),
            lookahead_days=lookahead_days,
            manual_login=manual_login,
            headless=headless,
            debug_dump_dir=debug_dump_dir,
        )
    except LoginFailedError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error
    _print_assignments(assignments)
    if telegram:
        _send_telegram(assignments, settings)
    if dry_run:
        console.print("[yellow]Dry run: no Telegram message was sent.[/yellow]")
        return


@app.command()
def bot(
    poll_interval: int = typer.Option(5, min=1, max=120, help="Seconds between poll cycles."),
    manual_login: bool = typer.Option(
        default=False,
        help="Let you log in manually in the browser.",
    ),
    headless: bool = typer.Option(
        default=True,
        help="Run Chromium without a visible window.",
    ),
    debug_dump_dir: Path | None = typer.Option(
        default=ROOT_DIR / "brone-debug",
        help="Write raw HTML of scraped pages to this directory for debugging.",
    ),
) -> None:
    try:
        run_bot(
            poll_interval=poll_interval,
            manual_login=manual_login,
            headless=headless,
            debug_dump_dir=debug_dump_dir,
        )
    except BotError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error


def _send_telegram(assignments: list[Assignment], settings: Settings) -> None:
    try:
        config = TelegramConfig.from_settings(
            token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )
        send_assignments_to_telegram(assignments, config)
    except (TelegramConfigError, TelegramSendError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error
    console.print("[green]Telegram message sent.[/green]")


def _print_assignments(assignments: list[Assignment]) -> None:
    table = Table(title="Discovered BRONE Assignments")
    table.add_column("Due")
    table.add_column("Title")
    table.add_column("Course")
    table.add_column("Status")
    table.add_column("URL")
    for assignment in assignments:
        table.add_row(
            assignment.due_at.strftime("%Y-%m-%d %H:%M"),
            assignment.title,
            assignment.course or "",
            assignment.submission_status or "",
            assignment.url or "",
        )
    console.print(table)
