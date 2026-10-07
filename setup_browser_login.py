from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from notebooklm import NotebookLMClient
from playwright.async_api import async_playwright


REQUIRED_COOKIES = {"SID", "__Secure-1PSIDTS"}
LOGIN_TIMEOUT_SECONDS = 900


async def verify_storage(path: Path) -> int:
    client = await NotebookLMClient.from_storage(str(path))
    async with client:
        notebooks = await client.notebooks.list()
    return len(notebooks)


async def complete_login(storage_path: Path) -> int:
    storage_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    browser_profile = storage_path.parent / "browser_profile"
    shutil.rmtree(browser_profile, ignore_errors=True)

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(browser_profile),
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--password-store=basic",
            ],
            ignore_default_args=["--enable-automation"],
        )
        os.chmod(browser_profile, 0o700)
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto("https://accounts.google.com/", wait_until="domcontentloaded", timeout=60_000)
            print("Complete Google sign-in in the browser. Waiting for the session cookies.", flush=True)

            deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                names = {cookie["name"] for cookie in await context.cookies()}
                if REQUIRED_COOKIES <= names:
                    break
                await asyncio.sleep(1)
            else:
                raise TimeoutError("Google sign-in did not produce the required session cookies")

            await page.goto("https://notebook.google.com/", wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(5_000)
            state = await context.storage_state()
            captured_names = {cookie["name"] for cookie in state.get("cookies", [])}
            if not REQUIRED_COOKIES <= captured_names:
                raise RuntimeError("Session cookies were missing after opening NotebookLM")

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=storage_path.parent,
                prefix=".storage_state-",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                os.chmod(temporary_path, 0o600)
                json.dump(state, temporary)

            try:
                notebook_count = await verify_storage(temporary_path)
                os.replace(temporary_path, storage_path)
                os.chmod(storage_path, 0o600)
            finally:
                temporary_path.unlink(missing_ok=True)

            print(f"NotebookLM session verified ({notebook_count} notebooks).", flush=True)
            return notebook_count
        finally:
            await context.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage", type=Path, required=True)
    args = parser.parse_args()
    try:
        asyncio.run(complete_login(args.storage))
    except Exception as error:
        print(f"Google sign-in failed: {type(error).__name__}", flush=True)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
