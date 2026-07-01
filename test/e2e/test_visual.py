from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageChops
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from test.e2e.browser import set_exact_viewport


BASELINES = Path(__file__).parents[1] / "visual" / "baselines"
ACTUAL = Path(__file__).parents[1] / "visual" / "actual"
VIEWPORTS = {
    "desktop-1440x900": (1440, 900),
    "laptop-1280x720": (1280, 720),
    "tablet-768x1024": (768, 1024),
    "phone-390x844": (390, 844),
}
PIXEL_CHANNEL_TOLERANCE = 8
MAX_DIFFERENT_PIXEL_RATIO = 0.005


def test_required_viewport_screenshots(driver, viewer_url: str) -> None:
    ACTUAL.mkdir(parents=True, exist_ok=True)
    for name, size in VIEWPORTS.items():
        set_exact_viewport(driver, *size)
        driver.get(viewer_url)
        WebDriverWait(driver, 15).until(lambda current: len(current.find_elements(By.CSS_SELECTOR, ".graph-node")) > 0)
        actual_bytes = driver.get_screenshot_as_png()
        actual_path = ACTUAL / f"{name}.png"
        actual_path.write_bytes(actual_bytes)
        expected_path = BASELINES / f"{name}.png"
        assert expected_path.is_file(), f"missing visual baseline: {expected_path}"

        actual = Image.open(io.BytesIO(actual_bytes)).convert("RGB")
        expected = Image.open(expected_path).convert("RGB")
        assert actual.size == expected.size
        difference = ImageChops.difference(actual, expected)
        pixels = difference.get_flattened_data()
        changed = sum(1 for pixel in pixels if max(pixel) > PIXEL_CHANNEL_TOLERANCE)
        ratio = changed / (actual.width * actual.height)
        diff_path = ACTUAL / f"{name}.diff.png"
        if ratio > MAX_DIFFERENT_PIXEL_RATIO:
            difference.save(diff_path)
        else:
            diff_path.unlink(missing_ok=True)
        assert ratio <= MAX_DIFFERENT_PIXEL_RATIO, f"{name} visual difference {ratio:.3%} exceeds {MAX_DIFFERENT_PIXEL_RATIO:.3%}"
