from __future__ import annotations

import os
import shutil
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.webdriver import WebDriver


def _installed_binary(environment_name: str, candidates: tuple[str, ...]) -> str:
    configured = os.environ.get(environment_name)
    if configured and Path(configured).is_file():
        return configured
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise RuntimeError(f"{environment_name} is unavailable; install a local Chromium browser and driver")


def create_chrome_driver(profile: Path) -> webdriver.Chrome:
    options = Options()
    options.binary_location = _installed_binary(
        "CHROME_BIN",
        (
            "/snap/chromium/current/usr/lib/chromium-browser/chrome",
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "google-chrome",
            "chromium",
        ),
    )
    for option in (
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--remote-debugging-pipe",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        f"--user-data-dir={profile}",
    ):
        options.add_argument(option)
    driver_path = _installed_binary(
        "CHROMEDRIVER",
        ("/usr/bin/chromedriver", "/usr/local/bin/chromedriver", "chromedriver"),
    )
    browser = webdriver.Chrome(service=Service(driver_path), options=options)
    browser.set_page_load_timeout(20)
    return browser


def set_exact_viewport(driver: WebDriver, width: int, height: int) -> None:
    try:
        driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": False,
        })
        inner_width, inner_height = driver.execute_script("return [window.innerWidth, window.innerHeight]")
        if (inner_width, inner_height) == (width, height):
            return
    except Exception:
        pass
    driver.set_window_size(width, height)
    for _ in range(3):
        inner_width, inner_height = driver.execute_script("return [window.innerWidth, window.innerHeight]")
        if (inner_width, inner_height) == (width, height):
            return
        driver.set_window_size(
            width + (width - inner_width),
            height + (height - inner_height),
        )
    inner_width, inner_height = driver.execute_script("return [window.innerWidth, window.innerHeight]")
    if (inner_width, inner_height) != (width, height):
        raise RuntimeError(f"unable to set exact viewport {(width, height)}; got {(inner_width, inner_height)}")
