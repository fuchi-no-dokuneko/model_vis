from __future__ import annotations

import subprocess
import threading
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

from test.e2e.browser import set_exact_viewport


ROOT = Path(__file__).parents[2]
BUILD = ROOT / "build"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture(scope="session")
def viewer_url() -> Iterator[str]:
    subprocess.run(
        ["npm", "run", "build-ui", "--", "--model-code", "model_code", "--out", "build"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    handler = partial(QuietHandler, directory=BUILD)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture(scope="session")
def driver(tmp_path_factory: pytest.TempPathFactory) -> Iterator[webdriver.Chrome]:
    options = Options()
    options.binary_location = "/snap/chromium/current/usr/lib/chromium-browser/chrome"
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--remote-debugging-pipe")
    options.add_argument("--hide-scrollbars")
    options.add_argument("--force-device-scale-factor=1")
    options.add_argument(f"--user-data-dir={tmp_path_factory.mktemp('chromium-profile')}")
    browser = webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
    browser.set_page_load_timeout(20)
    try:
        yield browser
    finally:
        browser.quit()


@pytest.fixture
def loaded_viewer(driver: webdriver.Chrome, viewer_url: str) -> webdriver.Chrome:
    set_exact_viewport(driver, 1440, 900)
    driver.get(viewer_url)
    wait = WebDriverWait(driver, 15)
    wait.until(lambda current: len(current.find_elements("css selector", ".model-item")) > 0)
    wait.until(lambda current: len(current.find_elements("css selector", ".graph-node")) > 0)
    return driver
