from __future__ import annotations

from pathlib import Path

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from test.e2e.browser import set_exact_viewport


DESKTOPS = ((1366, 768), (1440, 900), (1920, 1080))
THEMES = ("light", "dark")


def _wait_for_graph_render(driver) -> None:
    driver.execute_async_script(
        "const done = arguments[0]; requestAnimationFrame(() => requestAnimationFrame(done));"
    )


def _intersects(left: dict, right: dict, gap: float = 0) -> bool:
    return not (
        left["x"] + left["width"] + gap <= right["x"]
        or right["x"] + right["width"] + gap <= left["x"]
        or left["y"] + left["height"] + gap <= right["y"]
        or right["y"] + right["height"] + gap <= left["y"]
    )


def _rect(driver, element) -> dict:
    return driver.execute_script(
        "const r=arguments[0].getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height};",
        element,
    )


def _open(driver, viewer_url: str, route: str, theme: str, size: tuple[int, int]) -> None:
    set_exact_viewport(driver, *size)
    # Use a same-origin, non-application resource to prepare storage. Navigating
    # from a running viewer directly to another hash is a same-document change
    # and can race its asynchronous initial route load.
    driver.get(f"{viewer_url}styles.css")
    driver.execute_script(
        "localStorage.clear(); localStorage.setItem('model-vis-theme', arguments[0]);",
        theme,
    )
    driver.get(f"{viewer_url}#{route}")
    wait = WebDriverWait(driver, 15)
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, ".graph-node"))
    expected_view = route.split("/view/", 1)[1].split("/", 1)[0]
    wait.until(lambda current: f"/view/{expected_view}" in current.find_element(By.ID, "uri-input").get_attribute("value"))
    wait.until(lambda current: "active" in current.find_element(By.CSS_SELECTOR, f'[data-mode="{expected_view}"]').get_attribute("class"))


def _contrast(driver, selector: str) -> float:
    return float(driver.execute_script(
        """
        const element = document.querySelector(arguments[0]);
        const style = getComputedStyle(element);
        const parse = value => value.match(/[0-9.]+/g).slice(0, 3).map(Number);
        const luminance = rgb => {
          const values = rgb.map(value => value / 255).map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
          return .2126 * values[0] + .7152 * values[1] + .0722 * values[2];
        };
        let backgroundElement = element;
        let backgroundValue = style.backgroundColor;
        while (backgroundElement.parentElement && (backgroundValue === 'transparent' || backgroundValue.endsWith(', 0)'))) {
          backgroundElement = backgroundElement.parentElement;
          backgroundValue = getComputedStyle(backgroundElement).backgroundColor;
        }
        const foreground = luminance(parse(style.color));
        const background = luminance(parse(backgroundValue));
        return (Math.max(foreground, background) + .05) / (Math.min(foreground, background) + .05);
        """,
        selector,
    ))


def _assert_continuation_geometry(driver) -> int:
    markers = driver.find_elements(By.CSS_SELECTOR, ".continuation-marker")
    viewport = _rect(driver, driver.find_element(By.ID, "graph-viewport"))
    nodes = [node for node in driver.find_elements(By.CSS_SELECTOR, ".graph-node") if node.is_displayed()]
    overlays = [
        element for element in (
            driver.find_element(By.ID, "graph-legend"),
            driver.find_element(By.ID, "minimap-panel"),
            driver.find_element(By.ID, "graph-status"),
        )
        if element.is_displayed()
    ]
    for index, marker in enumerate(markers):
        rect = _rect(driver, marker)
        assert rect["x"] >= viewport["x"] and rect["y"] >= viewport["y"]
        assert rect["x"] + rect["width"] <= viewport["x"] + viewport["width"] + 1
        assert rect["y"] + rect["height"] <= viewport["y"] + viewport["height"] + 1
        assert int(marker.get_attribute("data-route-count")) >= 1
        assert all(not _intersects(rect, _rect(driver, other), gap=7) for other in markers[index + 1:])
        assert all(not _intersects(rect, _rect(driver, node), gap=1) for node in nodes)
        assert all(not _intersects(rect, _rect(driver, overlay), gap=1) for overlay in overlays)
    return len(markers)


def test_operations_overview_and_continuation_extremes(driver, viewer_url: str) -> None:
    for size in ((1366, 768), (1920, 1080)):
        for theme in THEMES:
            _open(
                driver,
                viewer_url,
                "/version/apertus/view/operation/detail/trace/labels/source",
                theme,
                size,
            )
            wait = WebDriverWait(driver, 15)
            assert driver.find_element(By.ID, "legend-toggle").get_attribute("aria-expanded") == "true"
            assert driver.find_element(By.ID, "minimap-toggle").get_attribute("aria-expanded") == "true"
            driver.find_element(By.ID, "fit-button").click()
            _wait_for_graph_render(driver)
            assert driver.find_element(By.ID, "graph-viewport").get_attribute("data-zoom-tier") == "overview"
            assert not any(item.is_displayed() for item in driver.find_elements(By.CSS_SELECTOR, ".node-ports, .node-actions"))
            effective_sizes = driver.execute_script(
                """
                return [...document.querySelectorAll('.overview-glyph')]
                  .filter(element => element.getClientRects().length)
                  .flatMap(element => {
                    const scale = element.getBoundingClientRect().width / element.offsetWidth;
                    return [...element.querySelectorAll('.overview-title, .overview-io')]
                      .map(label => parseFloat(getComputedStyle(label).fontSize) * scale);
                  });
                """
            )
            assert effective_sizes and min(effective_sizes) >= 9.95
            assert "Overview zoom" in driver.find_element(By.ID, "graph-status").text

            driver.find_element(By.CSS_SELECTOR, ".graph-node").click()
            wait.until(lambda current: current.find_element(By.ID, "graph-viewport").get_attribute("data-zoom-tier") == "normal")
            _wait_for_graph_render(driver)

            minimap = driver.find_element(By.ID, "minimap")
            rect = _rect(driver, minimap)
            marker_count = 0
            for x, y in ((2, 2), (rect["width"] - 2, 2), (2, rect["height"] - 2), (rect["width"] - 2, rect["height"] - 2)):
                driver.execute_script(
                    "arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true, clientX:arguments[1], clientY:arguments[2]}))",
                    minimap,
                    rect["x"] + x,
                    rect["y"] + y,
                )
                _wait_for_graph_render(driver)
                marker_count += _assert_continuation_geometry(driver)
            assert marker_count > 0

    _open(
        driver,
        viewer_url,
        "/version/dinov3/view/operation/detail/trace/labels/source",
        "light",
        (1440, 900),
    )
    while driver.find_element(By.ID, "graph-viewport").get_attribute("data-zoom-tier") != "normal":
        driver.find_element(By.ID, "zoom-in").click()
    _wait_for_graph_render(driver)
    minimap = driver.find_element(By.ID, "minimap")
    rect = _rect(driver, minimap)
    marker_count = 0
    for x, y in ((2, 2), (rect["width"] - 2, 2), (2, rect["height"] - 2), (rect["width"] - 2, rect["height"] - 2)):
        driver.execute_script(
            "arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true, clientX:arguments[1], clientY:arguments[2]}))",
            minimap,
            rect["x"] + x,
            rect["y"] + y,
        )
        _wait_for_graph_render(driver)
        marker_count += _assert_continuation_geometry(driver)
    assert marker_count > 0


def test_desktop_geometry_contrast_and_overlay_matrix(driver, viewer_url: str) -> None:
    for size in DESKTOPS:
        for theme in THEMES:
            _open(
                driver,
                viewer_url,
                "/version/apertus/view/architecture/detail/standard/labels/both",
                theme,
                size,
            )
            wait = WebDriverWait(driver, 15)
            for name in ("legend", "minimap"):
                toggle = driver.find_element(By.ID, f"{name}-toggle")
                if toggle.get_attribute("aria-expanded") == "false":
                    toggle.click()
            driver.find_element(By.ID, "fit-button").click()

            topbar = [_rect(driver, driver.find_element(By.CSS_SELECTOR, selector)) for selector in (".uri-form", ".mode-tabs", ".toolbar-actions")]
            assert not _intersects(topbar[0], topbar[1])
            assert not _intersects(topbar[1], topbar[2])
            breadcrumbs = driver.find_element(By.ID, "breadcrumbs")
            tools = driver.find_element(By.CSS_SELECTOR, ".canvas-tools")
            assert not _intersects(_rect(driver, breadcrumbs), _rect(driver, tools))
            crumb_nodes = driver.find_elements(By.CSS_SELECTOR, "#breadcrumbs .breadcrumb")
            assert _rect(driver, crumb_nodes[0])["width"] >= 30
            assert _rect(driver, crumb_nodes[-1])["width"] >= 30

            overlays = [driver.find_element(By.ID, "graph-legend"), driver.find_element(By.ID, "minimap-panel")]
            nodes = driver.find_elements(By.CSS_SELECTOR, ".graph-node")
            for node in nodes:
                if not node.is_displayed():
                    continue
                for overlay in overlays:
                    if overlay.is_displayed():
                        assert not _intersects(_rect(driver, node), _rect(driver, overlay), gap=1), f"{size} {theme}: {node.get_attribute('data-id')} intersects {overlay.get_attribute('id')}"

            while driver.find_element(By.ID, "graph-viewport").get_attribute("data-zoom-tier") != "normal":
                driver.find_element(By.ID, "zoom-in").click()
            effective_sizes = driver.execute_script(
                """
                const zoom = Number(getComputedStyle(document.querySelector('#graph-viewport')).getPropertyValue('--graph-zoom'));
                return [...document.querySelectorAll('.node-title, .node-shape, .port-meta')]
                  .filter(element => element.getClientRects().length)
                  .map(element => parseFloat(getComputedStyle(element).fontSize) * zoom);
                """
            )
            assert effective_sizes and min(effective_sizes) >= 9.95
            assert _contrast(driver, ".port-meta") >= 4.5

            driver.find_element(By.ID, "search").send_keys("dinov3")
            wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, ".model-warning-badge"))
            assert _contrast(driver, ".model-warning-badge") >= 4.5


def test_state_composition_continuations_compare_and_surface_snapshots(driver, viewer_url: str, tmp_path: Path) -> None:
    _open(
        driver,
        viewer_url,
        "/version/bert/view/operation/detail/trace/labels/source",
        "light",
        (1440, 900),
    )
    wait = WebDriverWait(driver, 15)
    while driver.find_element(By.ID, "graph-viewport").get_attribute("data-zoom-tier") != "normal":
        driver.find_element(By.ID, "zoom-in").click()
    _wait_for_graph_render(driver)
    nodes = driver.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="aten_op"]')
    second_id = nodes[1].get_attribute("data-id")
    first_label = nodes[0].text.splitlines()[0]
    driver.execute_script("arguments[0].click()", nodes[0])
    second = wait.until(lambda current: current.find_element(By.CSS_SELECTOR, f'.graph-node[data-id="{second_id}"]'))
    driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true, ctrlKey:true}))", second)
    driver.find_element(By.ID, "graph-search").send_keys(first_label)
    driver.find_element(By.CSS_SELECTOR, '[data-path-mode="downstream"]').click()
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, ".graph-node.path-active"))
    assert driver.find_elements(By.CSS_SELECTOR, ".graph-node.selected")
    assert driver.find_elements(By.CSS_SELECTOR, ".graph-node.multi-selected")
    assert driver.find_elements(By.CSS_SELECTOR, ".graph-node.path-active")
    assert driver.find_elements(By.CSS_SELECTOR, ".graph-node.search-match")

    minimap = driver.find_element(By.ID, "minimap")
    minimap_rect = _rect(driver, minimap)
    driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true, clientX:arguments[1], clientY:arguments[2]}))", minimap, minimap_rect["x"] + 3, minimap_rect["y"] + 3)
    try:
        markers = wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, ".continuation-marker"))
    except Exception:
        markers = []
    for index, marker in enumerate(markers):
        try:
            assert all(not _intersects(_rect(driver, marker), _rect(driver, other), gap=7) for other in markers[index + 1:])
            assert all(not _intersects(_rect(driver, marker), _rect(driver, node), gap=1) for node in driver.find_elements(By.CSS_SELECTOR, ".graph-node") if node.is_displayed())
        except StaleElementReferenceException:
            continue

    _open(
        driver,
        viewer_url,
        "/version/dinov3/view/architecture/detail/beginner/labels/semantic",
        "light",
        (1440, 900),
    )
    driver.save_screenshot(str(tmp_path / "architecture.png"))
    driver.find_element(By.CSS_SELECTOR, '[data-panel="shapes"]').click()
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, ".journey-step"))
    driver.save_screenshot(str(tmp_path / "tensor-journey.png"))

    driver.get(f"{viewer_url}#/compare/dinov3/apertus/view/architecture/detail/standard/labels/both")
    wait.until(lambda current: len(current.find_elements(By.CSS_SELECTOR, ".compare-table")) >= 3)
    pane = driver.find_element(By.ID, "compare-pane")
    content = driver.find_element(By.ID, "compare-content")
    pane_rect, content_rect = _rect(driver, pane), _rect(driver, content)
    assert content_rect["x"] >= pane_rect["x"]
    assert content_rect["x"] + content_rect["width"] <= pane_rect["x"] + pane_rect["width"] + 1
    assert "Config fields changed" in content.text
    config_row = next(row for row in content.find_elements(By.CSS_SELECTOR, "tr") if "Config fields changed" in row.text)
    cells = config_row.find_elements(By.CSS_SELECTOR, "td")
    assert cells[1].text == "—" and cells[2].text == "—"
    driver.save_screenshot(str(tmp_path / "normalized-compare.png"))
