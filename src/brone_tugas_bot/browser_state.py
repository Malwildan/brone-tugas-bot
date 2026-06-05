import base64
import binascii
import io
import json
import shutil
import tarfile
from pathlib import Path
from typing import Final

import httpx2
from playwright.sync_api import sync_playwright

from brone_tugas_bot.settings import ROOT_DIR, Settings

RESTORED_STORAGE_STATE_PATH: Final = ROOT_DIR / ".brone-storage-state.json"
BROWSER_STATE_ARCHIVE_ROOT: Final = ".brone-browser-state"
BROWSER_STATE_RESTORE_MARKER: Final = ".restored-from-archive"


class BrowserStateError(RuntimeError):
    pass


def restore_storage_state_from_env(settings: Settings) -> Path | None:
    if not settings.brone_storage_state_b64:
        return None
    try:
        raw_json = base64.b64decode(settings.brone_storage_state_b64, validate=True).decode("utf-8")
        parsed = json.loads(raw_json)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as error:
        msg = "BRONE_STORAGE_STATE_B64 is not valid base64-encoded Playwright storage JSON."
        raise BrowserStateError(msg) from error
    if not _is_storage_state(parsed):
        msg = "BRONE_STORAGE_STATE_B64 does not look like Playwright storage_state JSON."
        raise BrowserStateError(msg)
    RESTORED_STORAGE_STATE_PATH.write_text(raw_json, encoding="utf-8")
    return RESTORED_STORAGE_STATE_PATH


def restore_browser_profile_archive(settings: Settings) -> bool:
    if _restore_marker(settings).exists():
        return True
    archive = _profile_archive_bytes(settings)
    if archive is None:
        return False
    _reset_browser_state_dir(settings.browser_state_dir)
    _extract_profile_archive(archive)
    _restore_marker(settings).write_text("restored\n", encoding="utf-8")
    return True


def export_browser_profile_archive(settings: Settings, output_path: Path) -> None:
    if not settings.browser_state_dir.exists():
        msg = f"{settings.browser_state_dir} does not exist. Run a local login first."
        raise BrowserStateError(msg)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output_path, mode="w:gz") as archive:
        archive.add(settings.browser_state_dir, arcname=BROWSER_STATE_ARCHIVE_ROOT)


def export_storage_state(settings: Settings, output_path: Path, *, headless: bool) -> None:
    settings.browser_state_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(settings.browser_state_dir),
            headless=headless,
        )
        try:
            context.storage_state(path=str(output_path))
        finally:
            context.close()


def storage_state_to_base64(path: Path) -> str:
    try:
        raw_json = path.read_text(encoding="utf-8")
        parsed = json.loads(raw_json)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        msg = f"{path} is not valid Playwright storage_state JSON."
        raise BrowserStateError(msg) from error
    if not _is_storage_state(parsed):
        msg = f"{path} does not look like Playwright storage_state JSON."
        raise BrowserStateError(msg)
    return base64.b64encode(raw_json.encode("utf-8")).decode("ascii")


def _is_storage_state(value: object) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("cookies"), list)
        and isinstance(value.get("origins"), list)
    )


def _profile_archive_bytes(settings: Settings) -> bytes | None:
    if settings.brone_browser_state_archive_path is not None:
        try:
            return settings.brone_browser_state_archive_path.read_bytes()
        except OSError as error:
            msg = f"Could not read {settings.brone_browser_state_archive_path}."
            raise BrowserStateError(msg) from error
    if not settings.brone_browser_state_archive_url:
        return None
    try:
        timeout = httpx2.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
        with httpx2.Client(timeout=timeout) as client:
            response = client.get(settings.brone_browser_state_archive_url)
            response.raise_for_status()
            return response.content
    except httpx2.HTTPError as error:
        msg = "Could not download BRONE browser state archive."
        raise BrowserStateError(msg) from error


def _extract_profile_archive(payload: bytes) -> None:
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            _assert_safe_archive(archive)
            archive.extractall(ROOT_DIR)  # noqa: S202 - archive paths are validated above.
    except (tarfile.TarError, OSError) as error:
        msg = "BRONE browser state archive is not a valid safe .tar.gz profile archive."
        raise BrowserStateError(msg) from error


def _assert_safe_archive(archive: tarfile.TarFile) -> None:
    root = (ROOT_DIR / BROWSER_STATE_ARCHIVE_ROOT).resolve()
    for member in archive.getmembers():
        member_path = Path(member.name)
        if member_path.is_absolute() or ".." in member_path.parts:
            msg = "BRONE browser state archive contains an unsafe path."
            raise BrowserStateError(msg)
        target = (ROOT_DIR / member.name).resolve()
        if root != target and root not in target.parents:
            msg = "BRONE browser state archive must contain only .brone-browser-state files."
            raise BrowserStateError(msg)


def _reset_browser_state_dir(path: Path) -> None:
    target = path.resolve()
    root = ROOT_DIR.resolve()
    if target == root or root not in target.parents:
        msg = f"Refusing to reset browser state directory outside workspace: {target}"
        raise BrowserStateError(msg)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)


def _restore_marker(settings: Settings) -> Path:
    return settings.browser_state_dir / BROWSER_STATE_RESTORE_MARKER
