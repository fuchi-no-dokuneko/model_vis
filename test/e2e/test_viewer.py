from __future__ import annotations

import json
from pathlib import Path

from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.common.exceptions import ElementClickInterceptedException, ElementNotInteractableException, StaleElementReferenceException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select, WebDriverWait

from test.e2e.browser import set_exact_viewport


ROOT = Path(__file__).parents[2]
ALPHABETICAL_VERSIONS = sorted(
    json.loads((ROOT / "model_code" / "manifest.v2.json").read_text())["versions"]
)


def wait_for_graph_render(driver) -> None:
    driver.execute_async_script(
        "const done = arguments[0]; requestAnimationFrame(() => requestAnimationFrame(done));"
    )


def selected_graph_id(driver) -> str:
    return WebDriverWait(driver, 10).until(
        lambda current: current.execute_script(
            "return document.querySelector('.graph-node.selected')?.dataset.id || null"
        )
    )


def touch_tap(driver, element) -> None:
    rect = element.rect
    x = rect["x"] + rect["width"] / 2
    y = rect["y"] + rect["height"] / 2
    driver.execute_cdp_cmd("Input.dispatchTouchEvent", {
        "type": "touchStart",
        "touchPoints": [{"x": x, "y": y}],
    })
    driver.execute_cdp_cmd("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


def click_mode(driver, mode: str) -> None:
    driver.find_element(By.CSS_SELECTOR, f'[data-mode="{mode}"]').click()
    WebDriverWait(driver, 10).until(lambda current: current.find_element(By.CSS_SELECTOR, f'[data-mode="{mode}"]').get_attribute("class").find("active") >= 0)
    WebDriverWait(driver, 10).until(lambda current: len(current.find_elements(By.CSS_SELECTOR, ".graph-node")) > 0)
    WebDriverWait(driver, 10).until(lambda current: f"/view/{mode}" in current.find_element(By.ID, "uri-input").get_attribute("value"))


def zoom_to_detail(driver) -> None:
    wait_for_graph_render(driver)
    while driver.find_element(By.ID, "graph-viewport").get_attribute("data-zoom-tier") != "normal":
        driver.find_element(By.ID, "zoom-in").click()
    wait_for_graph_render(driver)


def click_first(driver, selector: str) -> None:
    def attempt(current) -> bool:
        try:
            elements = current.find_elements(By.CSS_SELECTOR, selector)
            if not elements:
                return False
            elements[0].click()
            return True
        except ElementClickInterceptedException:
            current.execute_script("arguments[0].click()", elements[0])
            return True
        except (ElementNotInteractableException, StaleElementReferenceException):
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
    assert "101 models" in driver.find_element(By.ID, "result-count").text
    assert not driver.find_element(By.ID, "empty-state").is_displayed()

    click_mode(driver, "module")
    zoom_to_detail(driver)
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
    source_reference = driver.find_element(By.ID, "source-reference")
    assert source_reference.find_element(By.CSS_SELECTOR, ".source-basename").is_displayed()
    assert source_reference.find_element(By.CSS_SELECTOR, ".source-line").text.startswith(":")
    assert "/" in source_reference.get_attribute("aria-label")
    assert source_reference.get_attribute("data-tooltip") in source_reference.get_attribute("aria-label")
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
    expected_count = sum("falcon" in version_id for version_id in ALPHABETICAL_VERSIONS)
    WebDriverWait(driver, 10).until(lambda current: current.find_element(By.ID, "result-count").text == f"{expected_count} models")
    names = driver.find_elements(By.CSS_SELECTOR, ".model-name")
    assert len(names) == expected_count and all("Falcon" in name.text for name in names)

    search.clear()
    Select(driver.find_element(By.ID, "sort")).select_by_value("sources")
    WebDriverWait(driver, 10).until(lambda current: len(current.find_elements(By.CSS_SELECTOR, ".model-item")) > 1)
    for _ in range(2):
        click_first(driver, ".compare-check input:not(:checked)")
    driver.find_element(By.ID, "compare-button").click()
    WebDriverWait(driver, 10).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".compare-table"))
    driver.find_element(By.ID, "close-compare").click()

    click_mode(driver, "module")
    zoom_to_detail(driver)
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
        "module/encoder.layer.0.attention.attention/detail/trace/labels/source"
    )
    address.submit()
    wait = WebDriverWait(driver, 15)
    wait.until(lambda current: "data2vec-3" in current.find_element(By.ID, "uri-input").get_attribute("value"))
    wait.until(lambda current: len(current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="aten_op"]')) > 5)
    zoom_to_detail(driver)

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


def test_semantic_architecture_explain_journey_modes_and_deep_routes(loaded_viewer) -> None:
    driver = loaded_viewer
    wait = WebDriverWait(driver, 15)
    address = driver.find_element(By.ID, "uri-input")
    address.clear()
    address.send_keys("modelvis:/version/dinov3/view/architecture/detail/beginner/labels/semantic")
    address.submit()

    stages = wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="semantic_stage"]'))
    assert len(stages) >= 4
    assert driver.find_elements(By.CSS_SELECTOR, ".stage-stats")
    click_first(driver, '.graph-node[data-kind="semantic_stage"]')
    selected_stage = selected_graph_id(driver)
    driver.find_element(By.CSS_SELECTOR, '[data-panel="explain"]').click()
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, ".explain-card"))
    assert driver.find_elements(By.CSS_SELECTOR, ".semantic-tag")
    assert driver.find_elements(By.CSS_SELECTOR, ".journey-step")
    assert driver.find_elements(By.CSS_SELECTOR, ".distribution-segment")

    for labels in ("both", "source", "semantic"):
        Select(driver.find_element(By.ID, "label-mode")).select_by_value(labels)
        wait.until(lambda current: current.find_element(By.ID, "label-mode").get_attribute("value") == labels)
        wait_for_graph_render(driver)
        assert selected_graph_id(driver) == selected_stage

    driver.find_elements(By.CSS_SELECTOR, ".journey-step")[1].click()
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, ".graph-node.selected"))
    selected_stage = selected_graph_id(driver)
    assert "/stage/" in driver.find_element(By.ID, "uri-input").get_attribute("value")

    Select(driver.find_element(By.ID, "detail-mode")).select_by_value("standard")
    wait.until(lambda current: current.find_element(By.ID, "label-mode").get_attribute("value") == "both")
    wait_for_graph_render(driver)
    assert selected_graph_id(driver) == selected_stage
    Select(driver.find_element(By.ID, "detail-mode")).select_by_value("trace")
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="aten_op"]'))
    saved_stage = driver.execute_script("return JSON.parse(localStorage.getItem('model-vis-view-state')).selectedStageId")
    assert saved_stage == selected_stage
    Select(driver.find_element(By.ID, "detail-mode")).select_by_value("beginner")
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="semantic_stage"]'))
    def selected_stage_restored(current) -> bool:
        return current.execute_script(
            "return document.querySelector('.graph-node.selected')?.dataset.id || null"
        ) == selected_stage

    wait.until(selected_stage_restored)

    deep_uri = driver.find_element(By.ID, "uri-input").get_attribute("value")
    driver.refresh()
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="semantic_stage"].selected'))
    assert driver.find_element(By.ID, "uri-input").get_attribute("value") == deep_uri

    driver.execute_script("localStorage.setItem('model-vis-theme', 'dark')")
    driver.refresh()
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="semantic_stage"]'))
    assert driver.find_element(By.CSS_SELECTOR, ".explain-card")


def test_viewport_controls_support_pointer_touch_enter_and_space(driver, viewer_url: str) -> None:
    set_exact_viewport(driver, 1440, 900)
    driver.get(f"{viewer_url}#/version/apertus/view/operation/detail/trace/labels/source")
    wait = WebDriverWait(driver, 15)
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="aten_op"]'))
    wait_for_graph_render(driver)

    for control_id in ("legend-toggle", "minimap-toggle"):
        control = driver.find_element(By.ID, control_id)
        for activate in (
            lambda value: value.click(),
            lambda value: touch_tap(driver, value),
            lambda value: value.send_keys(Keys.ENTER),
            lambda value: value.send_keys(Keys.SPACE),
        ):
            before = control.get_attribute("aria-expanded")
            activate(control)
            wait.until(lambda current: current.find_element(By.ID, control_id).get_attribute("aria-expanded") != before)
            wait_for_graph_render(driver)
            control = driver.find_element(By.ID, control_id)

    driver.find_element(By.ID, "legend-toggle").click()
    wait.until(lambda current: current.find_element(By.ID, "legend-toggle").get_attribute("aria-expanded") == "false")
    stored = driver.execute_script("return JSON.parse(localStorage.getItem('model-vis-overlays'))")
    assert stored["legend"] is False
    driver.refresh()
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="aten_op"]'))
    assert driver.find_element(By.ID, "legend-toggle").get_attribute("aria-expanded") == "false"

    while driver.find_element(By.ID, "graph-viewport").get_attribute("data-zoom-tier") != "normal":
        driver.find_element(By.ID, "zoom-in").click()
    wait_for_graph_render(driver)
    selected = driver.find_element(By.CSS_SELECTOR, ".graph-node")
    driver.execute_script("arguments[0].click()", selected)
    selected_id = selected_graph_id(driver)

    def prepare_marker(corner: int):
        for offset in range(4):
            minimap = driver.find_element(By.ID, "minimap")
            rect = minimap.rect
            coordinates = (
                (rect["x"] + 2, rect["y"] + 2),
                (rect["x"] + rect["width"] - 2, rect["y"] + 2),
                (rect["x"] + 2, rect["y"] + rect["height"] - 2),
                (rect["x"] + rect["width"] - 2, rect["y"] + rect["height"] - 2),
            )[(corner + offset) % 4]
            driver.execute_script(
                "arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true, clientX:arguments[1], clientY:arguments[2]}))",
                minimap,
                *coordinates,
            )
            wait_for_graph_render(driver)
            markers = driver.find_elements(By.CSS_SELECTOR, ".continuation-marker")
            if markers:
                return markers[0]
        raise AssertionError("No continuation marker appeared at any minimap extreme")

    activations = (
        lambda value: value.click(),
        lambda value: touch_tap(driver, value),
        lambda value: value.send_keys(Keys.ENTER),
        lambda value: value.send_keys(Keys.SPACE),
    )
    for index, activate in enumerate(activations):
        marker = prepare_marker(index)
        target_id = marker.get_attribute("data-target-id")
        before_transform = driver.find_element(By.ID, "graph-canvas").get_attribute("style")
        driver.execute_script(
            "window.__markerActivations=0; arguments[0].addEventListener('click', () => window.__markerActivations += 1)",
            marker,
        )
        activate(marker)
        wait.until(lambda current: current.find_element(By.ID, "graph-canvas").get_attribute("style") != before_transform)
        wait_for_graph_render(driver)
        assert driver.execute_script("return window.__markerActivations") == 1
        assert selected_graph_id(driver) == selected_id
        target = wait.until(lambda current: current.find_element(By.CSS_SELECTOR, f'.graph-node[data-id="{target_id}"]'))
        assert target.is_displayed()
        target_rect = target.rect
        viewport_rect = driver.find_element(By.ID, "graph-viewport").rect
        assert target_rect["x"] >= viewport_rect["x"]
        assert target_rect["y"] >= viewport_rect["y"]
        assert target_rect["x"] + target_rect["width"] <= viewport_rect["x"] + viewport_rect["width"]
        assert target_rect["y"] + target_rect["height"] <= viewport_rect["y"] + viewport_rect["height"]

    before_zoom = driver.find_element(By.ID, "zoom-value").text
    driver.execute_script(
        """
        const viewport = arguments[0];
        const rect = viewport.getBoundingClientRect();
        viewport.dispatchEvent(new WheelEvent('wheel', {
          bubbles: true, cancelable: true, deltaY: -120,
          clientX: rect.left + rect.width / 2,
          clientY: rect.top + rect.height / 2,
        }));
        """,
        driver.find_element(By.ID, "graph-viewport"),
    )
    wait.until(lambda current: current.find_element(By.ID, "zoom-value").text != before_zoom)


def test_architecture_actions_have_real_hit_targets_and_breadcrumbs_sync(driver, viewer_url: str) -> None:
    set_exact_viewport(driver, 1440, 900)
    route = "/version/dinov3/view/architecture/detail/standard/labels/both"
    driver.get(f"{viewer_url}#{route}")
    wait = WebDriverWait(driver, 15)
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="semantic_stage"]'))

    stage = wait.until(lambda current: next(
        (
            node for node in current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="semantic_stage"]')
            if len(node.find_elements(By.CSS_SELECTOR, ".node-action:not([disabled])")) == 3
        ),
        False,
    ))
    driver.execute_script("arguments[0].click()", stage)
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, ".graph-node.selected"))
    for minimum_zoom in (70, 100, 125):
        while int(driver.find_element(By.ID, "zoom-value").text.rstrip("%")) < minimum_zoom:
            driver.find_element(By.ID, "zoom-in").click()
        driver.find_element(By.ID, "center-selection").click()
        wait_for_graph_render(driver)
        stage = driver.find_element(By.CSS_SELECTOR, ".graph-node.selected")
        actions = stage.find_elements(By.CSS_SELECTOR, ".node-action:not([disabled])")
        assert len(actions) == 3
        for action_index in range(3):
            def has_real_hit_target(current) -> bool:
                try:
                    current_actions = current.find_elements(
                        By.CSS_SELECTOR,
                        ".graph-node.selected .node-action:not([disabled])",
                    )
                    if len(current_actions) != 3:
                        return False
                    return current.execute_script(
                        """
                        const rect = arguments[0].getBoundingClientRect();
                        const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
                        return hit === arguments[0] || arguments[0].contains(hit);
                        """,
                        current_actions[action_index],
                    )
                except StaleElementReferenceException:
                    return False

            assert wait.until(has_real_hit_target)

    collapse = driver.find_elements(By.CSS_SELECTOR, ".graph-node.selected .node-action:not([disabled])")[2]
    touch_tap(driver, collapse)
    wait.until(lambda current: current.execute_script("return Boolean(document.querySelector('.graph-node.selected.stage-collapsed'))"))
    wait_for_graph_render(driver)
    expand = driver.find_elements(By.CSS_SELECTOR, ".graph-node.selected .node-action:not([disabled])")[2]
    expand.send_keys(Keys.ENTER)
    def expanded(current) -> bool:
        try:
            return "stage-collapsed" not in current.find_element(By.CSS_SELECTOR, ".graph-node.selected").get_attribute("class")
        except StaleElementReferenceException:
            return False

    wait.until(expanded)

    def load_actions(minimum_zoom: int):
        driver.get(f"{viewer_url}#{route}")
        wait.until(
            lambda current: "/version/dinov3/view/architecture/" in current.find_element(By.ID, "uri-input").get_attribute("value")
        )

        def select_actionable_stage(current) -> bool:
            try:
                candidate = next(
                    (
                        node for node in current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="semantic_stage"]')
                        if len(node.find_elements(By.CSS_SELECTOR, ".node-action:not([disabled])")) == 3
                    ),
                    None,
                )
                if candidate is None:
                    return False
                current.execute_script("arguments[0].click()", candidate)
                return True
            except StaleElementReferenceException:
                return False

        wait.until(select_actionable_stage)
        wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, ".graph-node.selected .node-action:not([disabled])"))
        while int(driver.find_element(By.ID, "zoom-value").text.rstrip("%")) < minimum_zoom:
            driver.find_element(By.ID, "zoom-in").click()
        driver.find_element(By.ID, "center-selection").click()
        wait_for_graph_render(driver)

        def selected_actions(current):
            try:
                actions = current.find_elements(By.CSS_SELECTOR, ".graph-node.selected .node-action:not([disabled])")
                return actions if len(actions) == 3 else False
            except StaleElementReferenceException:
                return False

        return wait.until(selected_actions)

    activation_matrix = (
        (70, lambda value: value.click(), lambda value: touch_tap(driver, value), lambda value: value.send_keys(Keys.ENTER)),
        (100, lambda value: touch_tap(driver, value), lambda value: value.send_keys(Keys.ENTER), lambda value: value.click()),
        (125, lambda value: value.send_keys(Keys.ENTER), lambda value: value.click(), lambda value: touch_tap(driver, value)),
    )
    for minimum_zoom, open_modules, show_operations, toggle_card in activation_matrix:
        actions = load_actions(minimum_zoom)
        open_modules(actions[0])
        wait.until(lambda current: "/view/module/" in current.find_element(By.ID, "uri-input").get_attribute("value"))

        actions = load_actions(minimum_zoom)
        show_operations(actions[1])
        wait.until(lambda current: "/view/operation/" in current.find_element(By.ID, "uri-input").get_attribute("value"))

        actions = load_actions(minimum_zoom)
        toggle_card(actions[2])
        def collapsed(current) -> bool:
            try:
                return "stage-collapsed" in current.find_element(By.CSS_SELECTOR, ".graph-node.selected").get_attribute("class")
            except StaleElementReferenceException:
                return False

        wait.until(collapsed)
        wait_for_graph_render(driver)

        def collapsed_toggle(current):
            try:
                actions = current.find_elements(By.CSS_SELECTOR, ".graph-node.selected.stage-collapsed .node-action:not([disabled])")
                return actions[2] if len(actions) == 3 else False
            except StaleElementReferenceException:
                return False

        toggle_card(wait.until(collapsed_toggle))
        wait.until(expanded)

    driver.get(f"{viewer_url}#/version/dinov3/view/module/module/model.layer.0/detail/trace/labels/source")
    wait.until(lambda current: "/view/module/module/model.layer.0" in current.find_element(By.ID, "uri-input").get_attribute("value"))
    Select(driver.find_element(By.ID, "detail-mode")).select_by_value("beginner")
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="semantic_stage"].selected'))
    wait_for_graph_render(driver)
    crumb_text = [item.text for item in driver.find_elements(By.CSS_SELECTOR, "#breadcrumbs .breadcrumb")]
    selected_stage = selected_graph_id(driver)
    assert crumb_text[-2] == "Architecture"
    assert len(crumb_text) == 5
    assert f"/stage/{selected_stage}" in driver.find_element(By.ID, "uri-input").get_attribute("value")
    assert driver.find_element(By.ID, "inspector-title").text == crumb_text[-1]
    driver.refresh()
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="semantic_stage"].selected'))
    assert [item.text for item in driver.find_elements(By.CSS_SELECTOR, "#breadcrumbs .breadcrumb")] == crumb_text


def test_moshi_dinov3_normalized_cross_domain_fixture(driver, viewer_url: str) -> None:
    set_exact_viewport(driver, 1440, 900)
    driver.get(
        f"{viewer_url}#/compare/moshi/dinov3/view/architecture/detail/standard/labels/both"
    )
    wait = WebDriverWait(driver, 15)
    content = wait.until(lambda current: current.find_element(By.ID, "compare-content"))
    wait.until(lambda current: len(current.find_elements(By.CSS_SELECTOR, ".compare-table")) >= 3)
    text = content.text

    assert "audio" in text and "vision" in text
    assert "Primary journey" in text and "[" in text
    assert "Semantic stage presence and order" in text
    assert "Exact class/interface tags" in text
    assert "Stage parameter and operation distributions" in text
    assert "transformers.models.moshi.modeling_moshi.MoshiModel · forward(" in text
    assert "transformers.models.dinov3_vit.modeling_dinov3_vit.DINOv3ViTModel · forward(" in text
    assert content.find_elements(By.CSS_SELECTOR, ".relationship-badge")
    assert content.find_elements(By.CSS_SELECTOR, ".compare-table button")


def test_all_101_semantic_models_in_alphabetical_order(driver, viewer_url: str) -> None:
    assert len(ALPHABETICAL_VERSIONS) == 101
    assert ALPHABETICAL_VERSIONS == sorted(ALPHABETICAL_VERSIONS, key=str.casefold)
    wait = WebDriverWait(driver, 15)

    for version_id in ALPHABETICAL_VERSIONS:
        route = f"/version/{version_id}/view/architecture/detail/beginner/labels/semantic"
        driver.get(f"{viewer_url}#{route}")
        wait.until(
            lambda current: f"/version/{version_id}/view/architecture/" in current.find_element(By.ID, "uri-input").get_attribute("value")
        )
        stages = wait.until(
            lambda current: current.find_elements(
                By.CSS_SELECTOR,
                '.graph-node[data-kind="semantic_stage"]',
            )
        )
        assert stages, version_id
        canonical_route = driver.find_element(By.ID, "uri-input").get_attribute("value")
        assert f"/version/{version_id}/view/architecture/stage/" in canonical_route
        assert "/detail/beginner/labels/semantic" in canonical_route
        assert not driver.find_element(By.ID, "empty-state").is_displayed()


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
    address = driver.find_element(By.ID, "uri-input")
    address.clear()
    address.send_keys("modelvis:/version/apertus/view/architecture/detail/beginner/labels/semantic")
    address.submit()
    wait.until(lambda current: "apertus" in current.find_element(By.ID, "uri-input").get_attribute("value"))

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
    driver.find_element(By.CSS_SELECTOR, '[data-panel="details"]').click()
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
    zoom_to_detail(driver)
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
    address.send_keys("modelvis:/version/bert/view/module/module/encoder.layer/detail/trace/labels/source")
    address.submit()
    first = wait.until(lambda current: current.find_element(By.CSS_SELECTOR, '.graph-node[data-id="group:module-00009"]'))
    while driver.find_element(By.ID, "graph-viewport").get_attribute("data-zoom-tier") != "normal":
        driver.find_element(By.ID, "zoom-in").click()
    wait_for_graph_render(driver)
    first = driver.find_element(By.CSS_SELECTOR, '.graph-node[data-id="group:module-00009"]')

    input_names = [item.text for item in first.find_elements(By.CSS_SELECTOR, ".node-ports.inputs .port-name")]
    assert input_names == ["hidden_states"]

    for _ in range(8):
        driver.find_element(By.ID, "zoom-in").click()
    wait.until(lambda current: int(current.find_element(By.ID, "zoom-value").text.rstrip("%")) >= 95)
    click_first(driver, '.graph-node[data-id="group:module-00009"]')
    driver.find_element(By.ID, "center-selection").click()
    def visible_actions(current) -> bool:
        try:
            node = current.find_element(By.CSS_SELECTOR, '.graph-node[data-id="group:module-00009"]')
            actions = node.find_elements(By.CSS_SELECTOR, ".node-action")
            return len(actions) == 3 and all(action.is_displayed() and action.rect["width"] > 0 for action in actions)
        except StaleElementReferenceException:
            return False

    wait.until(visible_actions)
    first = driver.find_element(By.CSS_SELECTOR, '.graph-node[data-id="group:module-00009"]')
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
        driver.find_element(By.ID, "fit-button").click()
        while driver.find_element(By.ID, "graph-viewport").get_attribute("data-zoom-tier") != "normal":
            driver.find_element(By.ID, "zoom-in").click()
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
    point = driver.execute_script("""
      const viewport = document.querySelector('#graph-viewport');
      const rect = viewport.getBoundingClientRect();
      for (let y = rect.top + 20; y < rect.bottom - 20; y += 24) {
        for (let x = rect.left + 20; x < rect.right - 20; x += 24) {
          const target = document.elementFromPoint(x, y);
          if (target && viewport.contains(target) && !target.closest('.graph-node, .graph-legend, .minimap-panel, .continuation-marker')) return {x, y};
        }
      }
      return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};
    """)
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": point["x"], "y": point["y"], "button": "left", "buttons": 1, "clickCount": 1})
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": point["x"] + 100, "y": point["y"] + 75, "button": "left", "buttons": 1})
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": point["x"] + 100, "y": point["y"] + 75, "button": "left", "buttons": 0, "clickCount": 1})
    assert canvas.get_attribute("style") != before_transform
    assert driver.execute_script("return String(getSelection())") == ""

    driver.find_element(By.ID, "reset-button").click()
    def default_size(current) -> bool:
        try:
            node = current.find_element(By.CSS_SELECTOR, '.graph-node[data-id="group:module-00009"]')
            return float(node.value_of_css_property("width")[:-2]) == 248 and float(node.value_of_css_property("height")[:-2]) == 168
        except StaleElementReferenceException:
            return False

    wait.until(default_size)

    initial_theme = driver.execute_script("return document.documentElement.dataset.theme")
    driver.find_element(By.ID, "theme-button").click()
    expected_theme = "light" if initial_theme == "dark" else "dark"
    assert driver.execute_script("return document.documentElement.dataset.theme") == expected_theme
    assert driver.execute_script("return localStorage.getItem('model-vis-theme')") == expected_theme
    driver.refresh()
    wait.until(lambda current: current.execute_script("return document.documentElement.dataset.theme") == expected_theme)
