from __future__ import annotations

import subprocess
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from browser import set_exact_viewport


ROOT = Path(__file__).parents[2]
BASELINES = ROOT / "test" / "visual" / "baselines"
VIEWPORTS = {
    "desktop-1440x900": (1440, 900),
    "laptop-1280x720": (1280, 720),
    "tablet-768x1024": (768, 1024),
    "phone-390x844": (390, 844),
}


def main() -> None:
    subprocess.run(
        ["npm", "run", "build-ui", "--", "--model-code", "model_code", "--out", "build"],
        cwd=ROOT,
        check=True,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=ROOT / "build"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    options = Options()
    options.binary_location = "/snap/chromium/current/usr/lib/chromium-browser/chrome"
    profile = tempfile.TemporaryDirectory(prefix="model-vis-chromium-")
    for option in (
        "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
        "--remote-debugging-pipe", "--hide-scrollbars", "--force-device-scale-factor=1",
        f"--user-data-dir={profile.name}",
    ):
        options.add_argument(option)
    browser = webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
    BASELINES.mkdir(parents=True, exist_ok=True)
    try:
        url = f"http://127.0.0.1:{server.server_port}/"
        for name, size in VIEWPORTS.items():
            set_exact_viewport(browser, *size)
            browser.get(url)
            WebDriverWait(browser, 15).until(lambda current: len(current.find_elements(By.CSS_SELECTOR, ".graph-node")) > 0)
            browser.save_screenshot(BASELINES / f"{name}.png")
    finally:
        browser.quit()
        profile.cleanup()
        server.shutdown()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
