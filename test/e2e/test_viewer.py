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
            node = elements[0] if "graph-node" in elements[0].get_attribute("class").split() else elements[0].find_element(By.XPATH, "ancestor::*[contains(@class, 'graph-node')]")
            selected_id = node.get_attribute("data-id")
            before = (float(node.value_of_css_property("left")[:-2]), float(node.value_of_css_property("top")[:-2]))
            viewport = current.find_element(By.ID, "graph-viewport").rect
            handle = elements[0].rect
            actual_x = x if handle["x"] + handle["width"] / 2 + x < viewport["x"] + viewport["width"] - 4 else -x
            actual_y = y if handle["y"] + handle["height"] / 2 + y < viewport["y"] + viewport["height"] - 4 else -y
            ActionChains(current).drag_and_drop_by_offset(elements[0], actual_x, actual_y).perform()
            after = (float(node.value_of_css_property("left")[:-2]), float(node.value_of_css_property("top")[:-2]))
            assert abs(after[0] - before[0]) > abs(actual_x) * 0.5
            assert abs(after[1] - before[1]) > abs(actual_y) * 0.5
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
    node_id = drag_first(driver, ".node-drag-handle", 140, 90)
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


def test_amendment_controls_configs_paths_blocks_and_partial_warning(loaded_viewer) -> None:
    driver = loaded_viewer
    wait = WebDriverWait(driver, 15)

    assert driver.find_element(By.ID, "graph-legend").is_displayed()
    assert driver.find_elements(By.CSS_SELECTOR, "#structural-summary .summary-metric")
    assert not driver.find_element(By.ID, "model-warning").is_displayed()

    click_mode(driver, "blocks")
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind^="block_"]'))
    assert driver.find_elements(By.CSS_SELECTOR, ".edges path")

    click_mode(driver, "module")
    graph_search = driver.find_element(By.ID, "graph-search")
    graph_search.send_keys("rmsnorm")
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, ".graph-node.search-match"))
    graph_search.clear()

    click_first(driver, ".graph-node")
    assert len(driver.find_elements(By.CSS_SELECTOR, ".graph-node.selected .node-action")) == 3
    assert driver.find_element(By.CSS_SELECTOR, '[data-path-mode="downstream"]').is_enabled()
    driver.find_element(By.CSS_SELECTOR, '[data-path-mode="downstream"]').click()
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, ".graph-node.path-active"))

    port = driver.find_elements(By.CSS_SELECTOR, ".graph-node .node-port[data-port-id]")[0]
    driver.execute_script("arguments[0].click()", port)
    wait.until(lambda current: "tensor_route" in current.find_element(By.ID, "metadata").text.lower())
    assert driver.find_elements(By.CSS_SELECTOR, ".node-port.selected")

    driver.find_element(By.CSS_SELECTOR, '[data-panel="config"]').click()
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, "#config-view .config-provenance"))
    assert "huggingface.co" in driver.find_element(By.ID, "official-config-link").get_attribute("href")
    driver.find_element(By.CSS_SELECTOR, '[data-config-mode="trace"]').click()
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, "#config-view .config-row"))
    driver.find_element(By.CSS_SELECTOR, '[data-config-mode="diff"]').click()
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, "#config-view .config-row.changed"))

    for _ in range(4):
        driver.find_element(By.ID, "zoom-out").click()
    assert driver.find_element(By.ID, "graph-viewport").get_attribute("data-zoom-level") == "low"

    click_mode(driver, "operation")
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, ".continuation-marker"))

    driver.find_element(By.CSS_SELECTOR, '[data-navigator="catalog"]').click()
    model_search = driver.find_element(By.ID, "search")
    model_search.clear()
    model_search.send_keys("DINOv3")
    wait.until(lambda current: current.find_element(By.ID, "result-count").text.startswith("1 model"))
    assert driver.find_elements(By.CSS_SELECTOR, ".model-warning-badge")
    driver.find_element(By.CSS_SELECTOR, ".model-open").click()
    wait.until(lambda current: current.find_element(By.ID, "model-warning").is_displayed())
    assert "official config" in driver.find_element(By.ID, "model-warning").text.lower()


def test_amendment3_ports_controls_gestures_shortcuts_and_theme(loaded_viewer) -> None:
    driver = loaded_viewer
    wait = WebDriverWait(driver, 15)
    address = driver.find_element(By.ID, "uri-input")
    address.clear()
    address.send_keys("modelvis:/version/bert/view/module/module/encoder.layer")
    address.submit()
    first = wait.until(lambda current: current.find_element(By.CSS_SELECTOR, '.graph-node[data-id="group:module-00009"]'))

    input_names = [item.text for item in first.find_elements(By.CSS_SELECTOR, ".node-ports.inputs .port-name")]
    assert input_names == ["hidden_states"]

    for _ in range(8):
        driver.find_element(By.ID, "zoom-in").click()
    wait.until(lambda current: int(current.find_element(By.ID, "zoom-value").text.rstrip("%")) >= 95)
    first = driver.find_element(By.CSS_SELECTOR, '.graph-node[data-id="group:module-00009"]')
    actions = first.find_elements(By.CSS_SELECTOR, ".node-action")
    assert len(actions) == 3
    assert all(action.is_displayed() and action.rect["width"] > 0 for action in actions)
    title = first.find_element(By.CSS_SELECTOR, ".node-title").rect
    action_bar = first.find_element(By.CSS_SELECTOR, ".node-actions").rect
    assert title["x"] + title["width"] <= action_bar["x"] + 1

    before_width = float(first.value_of_css_property("width")[:-2])
    before_height = float(first.value_of_css_property("height")[:-2])
    ActionChains(driver).drag_and_drop_by_offset(first.find_element(By.CSS_SELECTOR, ".node-resize-handle"), 150, 110).perform()
    assert float(first.value_of_css_property("width")[:-2]) > before_width + 80
    assert float(first.value_of_css_property("height")[:-2]) > before_height + 60

    for mode in ["family", "module", "blocks", "operation"]:
        click_mode(driver, mode)
        drag_first(driver, ".node-drag-handle", 120, 70)

    address = driver.find_element(By.ID, "uri-input")
    address.clear()
    address.send_keys("modelvis:/version/bert/view/module/module/encoder.layer")
    address.submit()
    first = wait.until(lambda current: current.find_element(By.CSS_SELECTOR, '.graph-node[data-id="group:module-00009"]'))
    driver.execute_script("arguments[0].click()", first)
    driver.execute_script("window.__copied = []; Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async value => { window.__copied.push(value); } } });")

    for key in ["m", "p", "s"]:
        driver.execute_script("window.dispatchEvent(new KeyboardEvent('keydown', { key: arguments[0], altKey: true, shiftKey: true, bubbles: true }));", key)
    wait.until(lambda current: len(current.execute_script("return window.__copied")) == 3)
    copied = driver.execute_script("return window.__copied")
    assert copied[0] == "BertLayer"
    assert copied[1] == "encoder.layer.0"
    assert "def forward(" in copied[2]
    assert "class BertLayer" not in copied[2]

    viewport = driver.find_element(By.ID, "graph-viewport")
    canvas = driver.find_element(By.ID, "graph-canvas")
    before_transform = canvas.get_attribute("style")
    driver.execute_script("const r=document.createRange(); const t=document.querySelector('.node-title').firstChild; r.selectNodeContents(t); getSelection().removeAllRanges(); getSelection().addRange(r);")
    ActionChains(driver).move_to_element_with_offset(viewport, 20, 20).click_and_hold().move_by_offset(100, 75).release().perform()
    assert canvas.get_attribute("style") != before_transform
    assert driver.execute_script("return String(getSelection())") == ""

    driver.find_element(By.ID, "reset-button").click()
    first = wait.until(lambda current: current.find_element(By.CSS_SELECTOR, '.graph-node[data-id="group:module-00009"]'))
    assert float(first.value_of_css_property("width")[:-2]) == 248
    assert float(first.value_of_css_property("height")[:-2]) == 168

    initial_theme = driver.execute_script("return document.documentElement.dataset.theme")
    driver.find_element(By.ID, "theme-button").click()
    expected_theme = "light" if initial_theme == "dark" else "dark"
    assert driver.execute_script("return document.documentElement.dataset.theme") == expected_theme
    assert driver.execute_script("return localStorage.getItem('model-vis-theme')") == expected_theme
    driver.refresh()
    wait.until(lambda current: current.execute_script("return document.documentElement.dataset.theme") == expected_theme)
