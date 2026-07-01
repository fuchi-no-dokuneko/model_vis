from __future__ import annotations

from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select, WebDriverWait

from test.e2e.browser import set_exact_viewport


def click_mode(driver, mode: str) -> None:
    driver.find_element(By.CSS_SELECTOR, f'[data-mode="{mode}"]').click()
    WebDriverWait(driver, 10).until(lambda current: current.find_element(By.CSS_SELECTOR, f'[data-mode="{mode}"]').get_attribute("class").find("active") >= 0)
    WebDriverWait(driver, 10).until(lambda current: len(current.find_elements(By.CSS_SELECTOR, ".graph-node")) > 0)


def click_first(driver, selector: str) -> None:
    def attempt(current) -> bool:
        try:
            elements = current.find_elements(By.CSS_SELECTOR, selector)
            if not elements:
                return False
            elements[0].click()
            return True
        except StaleElementReferenceException:
            return False

    WebDriverWait(driver, 10).until(attempt)


def double_click_first(driver, selector: str) -> None:
    def attempt(current) -> bool:
        try:
            elements = current.find_elements(By.CSS_SELECTOR, selector)
            if not elements:
                return False
            ActionChains(current).double_click(elements[0]).perform()
            return True
        except StaleElementReferenceException:
            return False

    WebDriverWait(driver, 10).until(attempt)


def drag_first(driver, selector: str, x: int, y: int) -> str:
    selected_id = ""

    def attempt(current) -> bool:
        nonlocal selected_id
        try:
            elements = current.find_elements(By.CSS_SELECTOR, selector)
            if not elements:
                return False
            selected_id = elements[0].get_attribute("data-id")
            ActionChains(current).drag_and_drop_by_offset(elements[0], x, y).perform()
            return True
        except StaleElementReferenceException:
            return False

    WebDriverWait(driver, 10).until(attempt)
    return selected_id


def test_mode_navigation_drilldown_and_source_shapes(loaded_viewer) -> None:
    driver = loaded_viewer
    assert "21 models" in driver.find_element(By.ID, "result-count").text
    assert not driver.find_element(By.ID, "empty-state").is_displayed()

    click_mode(driver, "module")
    assert driver.find_elements(By.CSS_SELECTOR, ".node-ports.inputs")
    assert driver.find_elements(By.CSS_SELECTOR, ".node-ports.outputs")
    click_first(driver, ".graph-node")
    driver.find_element(By.CSS_SELECTOR, '[data-panel="shapes"]').click()
    assert driver.find_elements(By.CSS_SELECTOR, ".shape-record")

    driver.find_element(By.ID, "density-button").click()
    WebDriverWait(driver, 10).until(lambda current: current.find_element(By.ID, "density-button").get_attribute("class").find("active") >= 0)
    WebDriverWait(driver, 10).until(lambda current: current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="aten_op"]'))
    resources = driver.execute_script("return performance.getEntriesByType('resource').map(entry => entry.name)")
    assert any("/graphs/" in url for url in resources)

    driver.find_element(By.CSS_SELECTOR, '[data-navigator="modules"]').click()
    assert driver.find_elements(By.CSS_SELECTOR, "#module-tree .tree-row")
    assert "modelvis:/version/" in driver.find_element(By.ID, "uri-input").get_attribute("value")

    click_first(driver, '.graph-node[data-kind="aten_op"]')
    assert "/call/call-" in driver.find_element(By.ID, "uri-input").get_attribute("value")
    driver.find_element(By.CSS_SELECTOR, '[data-panel="source"]').click()
    WebDriverWait(driver, 10).until(lambda current: ":" in current.find_element(By.ID, "source-reference").text)
    source_lines = WebDriverWait(driver, 10).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".source-code-line"))
    assert len(source_lines) > 100
    assert driver.find_element(By.ID, "source-repository").get_attribute("href").startswith("https://github.com/")
    next(line for line in source_lines if "active" in line.get_attribute("class")).click()
    WebDriverWait(driver, 10).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".graph-node.selected"))
    source_uri = driver.find_element(By.ID, "uri-input").get_attribute("value")
    assert "/source/source.sha256." in source_uri
    assert "/line/" in source_uri
    driver.refresh()
    WebDriverWait(driver, 15).until(lambda current: current.find_element(By.ID, "source-panel").get_attribute("class").find("active") >= 0)
    WebDriverWait(driver, 15).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".source-code-line.active"))
    assert driver.find_element(By.ID, "uri-input").get_attribute("value") == source_uri

    driver.find_element(By.CSS_SELECTOR, '[data-panel="runtime"]').click()
    assert driver.find_elements(By.CSS_SELECTOR, ".runtime-row")


def test_search_sort_compare_and_local_layout(loaded_viewer) -> None:
    driver = loaded_viewer
    search = driver.find_element(By.ID, "search")
    search.clear()
    search.send_keys("Falcon")
    WebDriverWait(driver, 10).until(lambda current: current.find_element(By.ID, "result-count").text.startswith("1 model"))
    assert "Falcon" in driver.find_element(By.CSS_SELECTOR, ".model-name").text

    search.clear()
    Select(driver.find_element(By.ID, "sort")).select_by_value("sources")
    WebDriverWait(driver, 10).until(lambda current: len(current.find_elements(By.CSS_SELECTOR, ".model-item")) > 1)
    for _ in range(2):
        click_first(driver, ".compare-check input:not(:checked)")
    driver.find_element(By.ID, "compare-button").click()
    WebDriverWait(driver, 10).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".compare-table"))
    driver.find_element(By.ID, "close-compare").click()

    click_mode(driver, "module")
    node_id = drag_first(driver, ".graph-node", 40, 25)
    stored = driver.execute_script("return Object.keys(localStorage).filter(key => key.startsWith('model-vis-layout:')).length")
    assert stored > 0
    assert driver.find_element(By.CSS_SELECTOR, f'.graph-node[data-id="{node_id}"]')


def test_data2vec_parallel_scope_layer_group_and_uri(loaded_viewer) -> None:
    driver = loaded_viewer
    address = driver.find_element(By.ID, "uri-input")
    address.clear()
    address.send_keys(
        "modelvis:/version/data2vec-3/view/operation/"
        "module/encoder.layer.0.attention.attention"
    )
    address.submit()
    wait = WebDriverWait(driver, 15)
    wait.until(lambda current: "data2vec-3" in current.find_element(By.ID, "uri-input").get_attribute("value"))
    wait.until(lambda current: len(current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="aten_op"]')) > 5)

    node_text = "\n".join(node.text for node in driver.find_elements(By.CSS_SELECTOR, ".graph-node"))
    assert "query" in node_text
    assert "key" in node_text
    assert "value" in node_text
    assert len(driver.find_elements(By.CSS_SELECTOR, ".edges path")) > 5
    assert driver.find_elements(By.CSS_SELECTOR, ".layer-boundary")

    driver.find_element(By.CSS_SELECTOR, '[data-navigator="modules"]').click()
    assert any("attention" in row.text for row in driver.find_elements(By.CSS_SELECTOR, "#module-tree .tree-row"))
    source_module = driver.find_element(
        By.CSS_SELECTOR,
        '#module-tree .tree-row[data-module-path="encoder.layer.0.attention.output"]',
    )
    driver.execute_script("arguments[0].click()", source_module)
    driver.find_element(By.CSS_SELECTOR, '[data-panel="source"]').click()
    wait.until(lambda current: "modeling_data2vec_vision.py" in current.find_element(By.ID, "source-reference").text)
    wait.until(lambda current: len(current.find_elements(By.CSS_SELECTOR, ".source-code-line")) > 1000)
    assert "github.com/huggingface/transformers" in driver.find_element(By.ID, "source-repository").get_attribute("href")

    driver.find_element(By.CSS_SELECTOR, '[data-navigator="files"]').click()
    wait.until(lambda current: len(current.find_elements(By.CSS_SELECTOR, "#source-tree .tree-row")) > 1)

    driver.find_element(By.CSS_SELECTOR, '[data-navigator="modules"]').click()
    root = driver.find_element(By.CSS_SELECTOR, '#module-tree .tree-row[data-module-path="<root>"]')
    driver.execute_script("arguments[0].focus()", root)
    root.send_keys(Keys.END)
    assert driver.switch_to.active_element.get_attribute("data-module-path") != "<root>"
    driver.switch_to.active_element.send_keys(Keys.HOME)
    assert driver.switch_to.active_element.get_attribute("data-module-path") == "<root>"
    driver.switch_to.active_element.send_keys(Keys.ARROW_LEFT)
    root = wait.until(lambda current: current.find_element(By.CSS_SELECTOR, '#module-tree .tree-row[data-module-path="<root>"][aria-expanded="false"]'))
    root.send_keys(Keys.ARROW_RIGHT)
    wait.until(lambda current: current.find_element(By.CSS_SELECTOR, '#module-tree .tree-row[data-module-path="<root>"][aria-expanded="true"]'))


def test_mobile_drawers_and_no_external_runtime_requests(driver, viewer_url: str) -> None:
    set_exact_viewport(driver, 390, 844)
    driver.get(viewer_url)
    wait = WebDriverWait(driver, 15)
    wait.until(lambda current: len(current.find_elements(By.CSS_SELECTOR, ".graph-node")) > 0)
    driver.find_element(By.ID, "menu-button").click()
    assert "open" in driver.find_element(By.ID, "sidebar").get_attribute("class")
    driver.find_element(By.ID, "scrim").click()
    assert "open" not in driver.find_element(By.ID, "sidebar").get_attribute("class")

    viewport = driver.find_element(By.ID, "graph-viewport")
    bounds = viewport.rect
    center_x = bounds["x"] + bounds["width"] / 2
    center_y = bounds["y"] + bounds["height"] / 2
    initial_zoom = driver.find_element(By.ID, "zoom-value").text
    driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 2})
    driver.execute_cdp_cmd("Input.dispatchTouchEvent", {
        "type": "touchStart",
        "touchPoints": [
            {"x": center_x - 25, "y": center_y},
            {"x": center_x + 25, "y": center_y},
        ],
    })
    driver.execute_cdp_cmd("Input.dispatchTouchEvent", {
        "type": "touchMove",
        "touchPoints": [
            {"x": center_x - 65, "y": center_y},
            {"x": center_x + 65, "y": center_y},
        ],
    })
    driver.execute_cdp_cmd("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    WebDriverWait(driver, 10).until(lambda current: current.find_element(By.ID, "zoom-value").text != initial_zoom)

    urls = driver.execute_script("return performance.getEntriesByType('resource').map(entry => entry.name)")
    assert urls
    assert all(url.startswith(viewer_url) for url in urls)
