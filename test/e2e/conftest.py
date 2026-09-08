from __future__ import annotations

import subprocess
import threading
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from selenium.webdriver.support.ui import WebDriverWait

from test.e2e.browser import create_chrome_driver, set_exact_viewport
from test.e2e.browser_coverage import BrowserCoverage
from scripts.serve_https import https_server


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
    server = https_server(BUILD, handler=QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(scope="session")
def driver(tmp_path_factory: pytest.TempPathFactory) -> Iterator:
    browser = create_chrome_driver(tmp_path_factory.mktemp("chromium-profile"))
    browser_coverage = BrowserCoverage(browser, ROOT)
    browser_coverage.start()
    browser.model_vis_coverage = browser_coverage
    try:
        yield browser
    finally:
        browser_coverage.write_lcov(ROOT / "coverage" / "browser.lcov")
        browser.quit()


@pytest.fixture(autouse=True)
def capture_browser_coverage(request: pytest.FixtureRequest) -> Iterator[None]:
    yield
    if "driver" in request.fixturenames:
        request.getfixturevalue("driver").model_vis_coverage.capture()


@pytest.fixture
def loaded_viewer(driver, viewer_url: str):
    set_exact_viewport(driver, 1440, 900)
    driver.get(viewer_url)
    wait = WebDriverWait(driver, 15)
    wait.until(lambda current: len(current.find_elements("css selector", ".model-item")) > 0)
    wait.until(lambda current: len(current.find_elements("css selector", ".graph-node")) > 0)
    return driver
