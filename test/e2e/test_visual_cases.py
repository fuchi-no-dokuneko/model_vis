from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from test.e2e.test_visual import (
    _assert_continuation_geometry,
    _contrast,
    _intersects,
    _open,
    _rect,
    _wait_for_graph_render,
)


def _normal_zoom(driver) -> None:
    while driver.find_element(By.ID, "graph-viewport").get_attribute("data-zoom-tier") != "normal":
        driver.find_element(By.ID, "zoom-in").click()
    _wait_for_graph_render(driver)


def test_bug_01_operations_fit_uses_readable_overview(driver, viewer_url: str) -> None:
    _open(driver, viewer_url, "/version/apertus/view/operation/detail/trace/labels/source", "light", (1366, 768))
    driver.find_element(By.ID, "fit-button").click()
    _wait_for_graph_render(driver)
    assert driver.find_element(By.ID, "graph-viewport").get_attribute("data-zoom-tier") == "overview"
    assert not any(item.is_displayed() for item in driver.find_elements(By.CSS_SELECTOR, ".node-ports, .node-actions"))
    sizes = driver.execute_script(
        "return [...document.querySelectorAll('.overview-title,.overview-io')].filter(e=>e.getClientRects().length).map(e=>parseFloat(getComputedStyle(e).fontSize)*e.getBoundingClientRect().width/e.offsetWidth)"
    )
    assert sizes and min(sizes) >= 9.95


def test_bug_02_continuation_markers_do_not_collide(driver, viewer_url: str) -> None:
    _open(driver, viewer_url, "/version/apertus/view/operation/detail/trace/labels/source", "light", (1366, 768))
    _normal_zoom(driver)
    minimap = driver.find_element(By.ID, "minimap")
    rect = _rect(driver, minimap)
    driver.execute_script(
        "arguments[0].dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:arguments[1],clientY:arguments[2]}))",
        minimap,
        rect["x"] + 2,
        rect["y"] + 2,
    )
    _wait_for_graph_render(driver)
    assert _assert_continuation_geometry(driver) > 0


def test_bug_03_fit_reserves_legend_and_minimap(driver, viewer_url: str) -> None:
    _open(driver, viewer_url, "/version/apertus/view/architecture/detail/standard/labels/both", "dark", (1440, 900))
    for name in ("legend", "minimap"):
        toggle = driver.find_element(By.ID, f"{name}-toggle")
        if toggle.get_attribute("aria-expanded") == "false":
            toggle.click()
    driver.find_element(By.ID, "fit-button").click()
    _wait_for_graph_render(driver)
    overlays = [driver.find_element(By.ID, "graph-legend"), driver.find_element(By.ID, "minimap-panel")]
    for node in driver.find_elements(By.CSS_SELECTOR, ".graph-node"):
        if node.is_displayed():
            assert all(not _intersects(_rect(driver, node), _rect(driver, overlay), gap=1) for overlay in overlays)


def test_bug_04_arrowheads_keep_state_colors(driver, viewer_url: str) -> None:
    _open(driver, viewer_url, "/version/bert/view/operation/detail/trace/labels/source", "dark", (1440, 900))
    result = driver.execute_script(
        """
        return {
          paths: [...document.querySelectorAll('.edges > path.edge-path')].map(e => getComputedStyle(e).markerEnd),
          arrows: [...document.querySelectorAll('.edge-arrow-shape')].map(e => getComputedStyle(e).fill)
        };
        """
    )
    assert result["paths"] and all(value != "none" for value in result["paths"])
    assert len(result["arrows"]) >= 6
    assert all(value not in {"none", "rgba(0, 0, 0, 0)"} for value in result["arrows"])


def test_bug_05_deep_breadcrumb_keeps_root_and_final(driver, viewer_url: str) -> None:
    _open(driver, viewer_url, "/version/bert/view/module/module/encoder.layer.0.attention.self/detail/trace/labels/source", "light", (1366, 768))
    crumbs = driver.find_elements(By.CSS_SELECTOR, "#breadcrumbs .breadcrumb")
    assert len(crumbs) >= 3
    for crumb in (crumbs[0], crumbs[-1]):
        assert crumb.text
        assert driver.execute_script("return arguments[0].scrollWidth <= arguments[0].clientWidth + 1", crumb)
    assert not _intersects(_rect(driver, driver.find_element(By.ID, "breadcrumbs")), _rect(driver, driver.find_element(By.CSS_SELECTOR, ".canvas-tools")))


def test_bug_06_sidebar_metadata_keeps_numeric_values(driver, viewer_url: str) -> None:
    _open(driver, viewer_url, "/version/apertus/view/architecture/detail/standard/labels/both", "light", (1366, 768))
    driver.execute_script("document.querySelector('.workspace').style.gridTemplateColumns='260px minmax(430px,1fr) 370px'")
    sidebar = driver.find_element(By.ID, "sidebar")
    assert _rect(driver, sidebar)["width"] <= 261
    row = driver.find_element(By.CSS_SELECTOR, ".model-item.active")
    values = row.find_elements(By.CSS_SELECTOR, ".model-meta > span")
    assert len(values) == 4 and all(len(value.text) > 1 for value in values)
    assert all(
        driver.execute_script("return arguments[0].scrollWidth <= arguments[0].clientWidth + 1", value)
        for value in row.find_elements(By.CSS_SELECTOR, ".meta-value")
    )
    assert "Trace parameters" in row.find_element(By.CSS_SELECTOR, ".model-open").get_attribute("aria-label")


def test_bug_07_selection_states_compose_visually(driver, viewer_url: str) -> None:
    _open(driver, viewer_url, "/version/bert/view/operation/detail/trace/labels/source", "light", (1440, 900))
    _normal_zoom(driver)
    wait = WebDriverWait(driver, 15)
    nodes = driver.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="aten_op"]')
    second_id = nodes[1].get_attribute("data-id")
    label = nodes[0].text.splitlines()[0]
    driver.execute_script("arguments[0].click()", nodes[0])
    second = wait.until(lambda current: current.find_element(By.CSS_SELECTOR, f'.graph-node[data-id="{second_id}"]'))
    driver.execute_script("arguments[0].dispatchEvent(new MouseEvent('click',{bubbles:true,ctrlKey:true}))", second)
    driver.find_element(By.ID, "graph-search").send_keys(label)
    driver.find_element(By.CSS_SELECTOR, '[data-path-mode="downstream"]').click()
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, ".graph-node.path-active"))
    for state in ("selected", "multi-selected", "path-active", "search-match"):
        assert driver.find_elements(By.CSS_SELECTOR, f".graph-node.{state}")


def test_bug_08_source_reference_preserves_file_and_line(driver, viewer_url: str) -> None:
    _open(driver, viewer_url, "/version/apertus/view/operation/detail/trace/labels/source", "light", (1440, 900))
    _normal_zoom(driver)
    driver.execute_script("arguments[0].click()", driver.find_element(By.CSS_SELECTOR, '.graph-node[data-kind="aten_op"]'))
    driver.find_element(By.CSS_SELECTOR, '[data-panel="source"]').click()
    wait = WebDriverWait(driver, 15)
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, "#source-reference .source-basename"))
    basename = driver.find_element(By.CSS_SELECTOR, "#source-reference .source-basename")
    line = driver.find_element(By.CSS_SELECTOR, "#source-reference .source-line")
    reference = driver.find_element(By.ID, "source-reference")
    assert basename.text.endswith(".py") and line.text.startswith(":")
    assert basename.text in reference.get_attribute("aria-label")
    assert reference.get_attribute("data-tooltip")


def test_bug_09_warning_badge_meets_dark_contrast(driver, viewer_url: str) -> None:
    _open(driver, viewer_url, "/version/apertus/view/architecture/detail/standard/labels/both", "dark", (1440, 900))
    driver.find_element(By.ID, "search").send_keys("dinov3")
    WebDriverWait(driver, 15).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".model-warning-badge"))
    assert _contrast(driver, ".model-warning-badge") >= 4.5


def test_bug_10_port_metadata_is_readable_or_hidden(driver, viewer_url: str) -> None:
    _open(driver, viewer_url, "/version/bert/view/operation/detail/trace/labels/source", "dark", (1920, 1080))
    _normal_zoom(driver)
    metadata = [item for item in driver.find_elements(By.CSS_SELECTOR, ".port-meta") if item.is_displayed()]
    assert metadata
    sizes = driver.execute_script(
        "const z=Number(getComputedStyle(document.querySelector('#graph-viewport')).getPropertyValue('--graph-zoom')); return [...document.querySelectorAll('.port-meta')].filter(e=>e.getClientRects().length).map(e=>parseFloat(getComputedStyle(e).fontSize)*z)"
    )
    assert min(sizes) >= 9.95
    assert _contrast(driver, ".port-meta") >= 4.5
    driver.find_element(By.ID, "fit-button").click()
    _wait_for_graph_render(driver)
    assert not any(item.is_displayed() for item in driver.find_elements(By.CSS_SELECTOR, ".port-meta"))
