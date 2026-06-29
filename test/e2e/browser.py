from __future__ import annotations

from selenium.webdriver.remote.webdriver import WebDriver


def set_exact_viewport(driver: WebDriver, width: int, height: int) -> None:
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
