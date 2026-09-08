from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import ElementNotInteractableException, StaleElementReferenceException
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait

from test.e2e.browser import set_exact_viewport

from .gherkin import bind


def _wait(context):
    return WebDriverWait(context.driver, 15)


def _graph_nodes(context, selector=".graph-node"):
    return _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, selector))


def _open_uri(context, uri: str) -> None:
    address = context.driver.find_element(By.ID, "uri-input")
    address.clear()
    address.send_keys(uri)
    context.driver.execute_script(
        "arguments[0].dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))",
        context.driver.find_element(By.ID, "uri-form"),
    )


def _select(context, element_id: str, value: str) -> None:
    Select(context.driver.find_element(By.ID, element_id)).select_by_value(value)
    _wait(context).until(
        lambda current: current.find_element(By.ID, element_id).get_attribute("value") == value
    )


def _click_first(context, selector: str):
    def attempt(current):
        try:
            elements = current.find_elements(By.CSS_SELECTOR, selector)
            if not elements:
                return False
            current.execute_script("arguments[0].click()", elements[0])
            return True
        except (ElementNotInteractableException, StaleElementReferenceException):
            return False

    _wait(context).until(attempt)


def _node_box(node) -> tuple[float, float, float, float]:
    return tuple(float(node.value_of_css_property(name).removesuffix("px")) for name in ("left", "top", "width", "height"))


def _run_demo_command(variable: str, extra_environment: dict[str, str]) -> bool:
    executable = os.environ.get(variable)
    if not executable:
        return False
    completed = subprocess.run(
        [executable],
        env={**os.environ, **extra_environment},
        check=False,
        timeout=60,
    )
    if completed.returncode:
        raise RuntimeError(f"{variable} exited with status {completed.returncode}")
    return True


def _narrate(language: str, minimum_seconds: int, narration: str) -> None:
    started = time.monotonic()
    invoked = _run_demo_command(
        "DEMO_TTS_COMMAND",
        {
            "DEMO_TTS_LANGUAGE": language,
            "DEMO_TTS_TEXT": narration,
            "DEMO_TTS_MIN_SECONDS": str(minimum_seconds),
        },
    )
    if not invoked:
        print(f"NARRATION [{language}, >={minimum_seconds}s]: {narration}")
    remaining = minimum_seconds - (time.monotonic() - started)
    if remaining > 0:
        time.sleep(remaining)


@bind("the built Model Vis site is running")
def built_site(context) -> None:
    assert context.viewer_url.startswith("https://127.0.0.1:")


@bind("I open the model catalog")
def open_catalog(context) -> None:
    context.driver.get(context.viewer_url)
    _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".model-item"))


@bind("101 generated models are listed")
def catalog_count(context) -> None:
    _wait(context).until(lambda current: current.find_element(By.ID, "result-count").text == "101 models")


@bind("Beginner detail, Semantic labels, and Architecture are selected")
def default_workspace(context) -> None:
    assert context.driver.find_element(By.ID, "detail-mode").get_attribute("value") == "beginner"
    assert context.driver.find_element(By.ID, "label-mode").get_attribute("value") == "semantic"
    assert "active" in context.driver.find_element(By.CSS_SELECTOR, '[data-mode="architecture"]').get_attribute("class")


@bind("a semantic graph, legend, minimap, and inspector are visible")
def default_surfaces(context) -> None:
    assert _graph_nodes(context, '.graph-node[data-kind="semantic_stage"]')
    for selector in ("#graph-legend", "#minimap-panel", "#inspector"):
        assert context.driver.find_element(By.CSS_SELECTOR, selector).is_displayed()


@bind("I search the catalog for Falcon")
def search_falcon(context) -> None:
    search = context.driver.find_element(By.ID, "search")
    search.clear()
    search.send_keys("Falcon")


@bind("all generated Falcon models matching the search are listed")
def matching_falcon_models(context) -> None:
    root = Path(__file__).resolve().parents[1] / "model_code"
    manifest = json.loads((root / "manifest.v2.json").read_text())
    versions = [json.loads((root / "versions" / f"{version_id}.json").read_text()) for version_id in manifest["versions"]]
    expected = [version for version in versions if "falcon" in version["family_name"].lower()]
    assert expected
    count = len(expected)
    _wait(context).until(lambda current: current.find_element(By.ID, "result-count").text == f"{count} model{'s' if count != 1 else ''}")
    names = context.driver.find_elements(By.CSS_SELECTOR, ".model-name")
    assert len(names) == count and all("Falcon" in name.text for name in names)


@bind("I search the catalog for a model that does not exist")
def search_missing(context) -> None:
    context.open_graph_uri = context.driver.find_element(By.ID, "uri-input").get_attribute("value")
    search = context.driver.find_element(By.ID, "search")
    search.clear()
    search.send_keys("no-such-model-uat")


@bind("the catalog reports zero models without changing the open graph")
def empty_search_is_non_destructive(context) -> None:
    _wait(context).until(lambda current: current.find_element(By.ID, "result-count").text == "0 models")
    assert context.driver.find_element(By.ID, "uri-input").get_attribute("value") == context.open_graph_uri
    assert context.driver.find_elements(By.CSS_SELECTOR, ".graph-node")


@bind("I clear the catalog search")
def clear_catalog_search(context) -> None:
    search = context.driver.find_element(By.ID, "search")
    search.clear()
    search.send_keys(" ")
    search.send_keys(Keys.BACKSPACE)
    _wait(context).until(lambda current: current.find_element(By.ID, "result-count").text == "101 models")


@bind("I choose the first model category")
def choose_category(context) -> None:
    category = Select(context.driver.find_element(By.ID, "category"))
    assert len(category.options) > 1
    category.select_by_index(1)
    context.category_value = category.first_selected_option.get_attribute("value")


@bind("the category filter leaves a nonempty catalog subset")
def category_subset(context) -> None:
    count = int(_wait(context).until(lambda current: current.find_element(By.ID, "result-count").text).split()[0])
    assert 0 < count < 101
    assert context.driver.find_element(By.ID, "category").get_attribute("value") == context.category_value


@bind("I sort the catalog by source count")
def sort_by_sources(context) -> None:
    _select(context, "sort", "sources")


@bind("the source-count sort remains selected and models remain available")
def source_sort_selected(context) -> None:
    assert context.driver.find_element(By.ID, "sort").get_attribute("value") == "sources"
    assert context.driver.find_elements(By.CSS_SELECTOR, ".model-item")


@bind("I submit an unknown model URI")
def submit_unknown_uri(context) -> None:
    _open_uri(context, "modelvis:/version/no-such-model/view/architecture/detail/beginner/labels/semantic")
    context.unknown_diagnostic_initial = context.driver.find_element(By.ID, "graph-status").text
    time.sleep(0.25)
    context.unknown_diagnostic_after_read_delay = context.driver.find_element(By.ID, "graph-status").text


@bind("the unknown-model diagnostic remains visible long enough to read")
def unknown_uri_diagnostic(context) -> None:
    assert "Unknown model version" in context.unknown_diagnostic_initial
    assert "Unknown model version" in context.unknown_diagnostic_after_read_delay


@bind("I submit the DINOv3 beginner architecture URI")
def submit_dinov3_uri(context) -> None:
    _open_uri(context, "modelvis:/version/dinov3/view/architecture/detail/beginner/labels/semantic")


@bind("the DINOv3 URI and semantic graph are restored")
def valid_uri_recovers(context) -> None:
    _graph_nodes(context, '.graph-node[data-kind="semantic_stage"]')
    assert "/version/dinov3/view/architecture" in context.driver.find_element(By.ID, "uri-input").get_attribute("value")


@bind("I inspect DINOv3 semantic architecture")
def inspect_architecture(context) -> None:
    context.driver.get(f"{context.viewer_url}#/version/dinov3/view/architecture/detail/beginner/labels/semantic")
    _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="semantic_stage"]'))


@bind("semantic stages and exact tags are shown")
def semantic_stages(context) -> None:
    nodes = context.driver.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="semantic_stage"]')
    assert len(nodes) >= 3
    assert context.driver.find_elements(By.CSS_SELECTOR, ".confidence-label")


@bind("I select Standard detail")
def select_standard(context) -> None:
    context.stage_before_detail = context.driver.find_element(By.CSS_SELECTOR, ".graph-node.selected").get_attribute("data-id")
    _select(context, "detail-mode", "standard")


@bind("Both labels remain selected on the current semantic stage")
def standard_detail(context) -> None:
    assert context.driver.find_element(By.ID, "label-mode").get_attribute("value") == "both"
    assert context.driver.find_element(By.CSS_SELECTOR, ".graph-node.selected").get_attribute("data-id") == context.stage_before_detail


@bind("I select Trace detail")
def select_trace(context) -> None:
    _select(context, "detail-mode", "trace")


@bind("Operations and Source labels are selected with runtime nodes")
def trace_detail(context) -> None:
    _graph_nodes(context, '.graph-node[data-kind="aten_op"]')
    assert context.driver.find_element(By.ID, "label-mode").get_attribute("value") == "source"
    assert "active" in context.driver.find_element(By.CSS_SELECTOR, '[data-mode="operation"]').get_attribute("class")


@bind("I visit Family, Modules, Blocks, and Operations graph modes")
def visit_graph_modes(context) -> None:
    context.mode_counts = {}
    for mode in ("family", "module", "blocks", "operation"):
        context.driver.find_element(By.CSS_SELECTOR, f'[data-mode="{mode}"]').click()
        nodes = _graph_nodes(context)
        _wait(context).until(lambda current: "active" in current.find_element(By.CSS_SELECTOR, f'[data-mode="{mode}"]').get_attribute("class"))
        context.mode_counts[mode] = (len(nodes), len(context.driver.find_elements(By.CSS_SELECTOR, ".edges path")))


@bind("every graph mode renders connected model content")
def all_modes_render(context) -> None:
    assert all(node_count > 0 for node_count, _ in context.mode_counts.values())
    assert all(context.mode_counts[mode][1] > 0 for mode in ("module", "blocks", "operation"))


@bind("I return to Beginner detail")
def return_beginner(context) -> None:
    _select(context, "detail-mode", "beginner")


@bind("Architecture and Semantic labels return with the same stage selected")
def beginner_returns(context) -> None:
    _graph_nodes(context, '.graph-node[data-kind="semantic_stage"]')
    assert context.driver.find_element(By.ID, "label-mode").get_attribute("value") == "semantic"
    assert "active" in context.driver.find_element(By.CSS_SELECTOR, '[data-mode="architecture"]').get_attribute("class")
    assert context.driver.find_element(By.CSS_SELECTOR, ".graph-node.selected").get_attribute("data-id") == context.stage_before_detail


@bind("I open an Apertus module in Trace detail and select a node")
def open_apertus_trace(context) -> None:
    context.driver.get(f"{context.viewer_url}#/version/apertus/view/module/detail/trace/labels/source")
    _wait(context).until(
        lambda current: "/version/apertus/view/module" in current.find_element(By.ID, "uri-input").get_attribute("value")
    )
    _graph_nodes(context)
    _click_first(context, ".graph-node .node-drag-handle")
    _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".graph-node.selected"))
    context.selected_node_id = context.driver.find_element(By.CSS_SELECTOR, ".graph-node.selected").get_attribute("data-id")


@bind("Details shows structural metadata")
def details_metadata(context) -> None:
    context.driver.find_element(By.CSS_SELECTOR, '[data-panel="details"]').click()
    assert context.driver.find_elements(By.CSS_SELECTOR, "#structural-summary .summary-metric")
    assert context.driver.find_element(By.ID, "metadata").text.strip()


@bind("I open the I/O inspector")
def open_io(context) -> None:
    context.driver.find_element(By.CSS_SELECTOR, '[data-panel="shapes"]').click()


@bind("tensor shape records are visible")
def io_records(context) -> None:
    assert _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".shape-record"))


@bind("I open the Source inspector")
def open_source(context) -> None:
    context.driver.find_element(By.CSS_SELECTOR, '[data-panel="source"]').click()


@bind("a source reference, source lines, and official repository link are visible")
def source_evidence(context) -> None:
    _wait(context).until(lambda current: ":" in current.find_element(By.ID, "source-reference").text)
    assert len(_wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".source-code-line"))) > 20
    assert context.driver.find_element(By.ID, "source-repository").get_attribute("href").startswith("https://github.com/")


@bind("I open the Runtime inspector")
def open_runtime(context) -> None:
    context.driver.find_element(By.CSS_SELECTOR, '[data-panel="runtime"]').click()


@bind("runtime rows are visible")
def runtime_rows(context) -> None:
    assert _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".runtime-row"))


@bind("I open Official, Trace, and Differences configuration views")
def open_config_modes(context) -> None:
    context.driver.find_element(By.CSS_SELECTOR, '[data-panel="config"]').click()
    _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, "#config-view .config-provenance"))
    context.saw_config_provenance = True
    context.driver.find_element(By.CSS_SELECTOR, '[data-config-mode="trace"]').click()
    _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, "#config-view .config-row"))
    context.saw_trace_config = True
    context.driver.find_element(By.CSS_SELECTOR, '[data-config-mode="diff"]').click()
    _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, "#config-view .config-row.changed"))
    context.saw_config_differences = True


@bind("configuration provenance and changed fields are visible")
def config_evidence(context) -> None:
    assert context.saw_config_provenance
    assert context.saw_trace_config
    assert context.saw_config_differences


@bind("I search the graph for rmsnorm")
def search_graph(context) -> None:
    search = context.driver.find_element(By.ID, "graph-search")
    search.clear()
    search.send_keys("rmsnorm")


@bind("matching graph nodes are highlighted")
def graph_matches(context) -> None:
    assert _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".graph-node.search-match"))


@bind("I follow the selected node outputs")
def follow_outputs(context) -> None:
    context.driver.find_element(By.ID, "graph-search").clear()
    button = context.driver.find_element(By.CSS_SELECTOR, '[data-path-mode="downstream"]')
    if not button.is_enabled():
        for node in context.driver.find_elements(By.CSS_SELECTOR, ".graph-node"):
            context.driver.execute_script("arguments[0].click()", node)
            if button.is_enabled():
                break
    assert button.is_enabled()
    button.click()


@bind("the downstream tensor route is highlighted")
def output_path(context) -> None:
    assert _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".graph-node.path-active"))
    assert "active" in context.driver.find_element(By.CSS_SELECTOR, '[data-path-mode="downstream"]').get_attribute("class")


@bind("I zoom out and fit the graph")
def zoom_and_fit(context) -> None:
    before = context.driver.find_element(By.ID, "zoom-value").text
    context.driver.find_element(By.ID, "zoom-out").click()
    context.zoom_after_out = _wait(context).until(lambda current: current.find_element(By.ID, "zoom-value").text != before)
    context.driver.find_element(By.ID, "fit-button").click()


@bind("the zoom indicator changes and the graph remains visible")
def zoom_remains_valid(context) -> None:
    assert context.zoom_after_out
    assert context.driver.find_elements(By.CSS_SELECTOR, ".graph-node")
    assert context.driver.find_element(By.ID, "zoom-value").text.endswith("%")


@bind("I toggle full canvas, legend, and minimap")
def toggle_workspace(context) -> None:
    context.driver.find_element(By.ID, "focus-button").click()
    context.driver.find_element(By.ID, "legend-toggle").click()
    context.driver.find_element(By.ID, "minimap-toggle").click()
    context.overlay_values = {
        name: context.driver.find_element(By.ID, f"{name}-toggle").get_attribute("aria-expanded")
        for name in ("legend", "minimap")
    }


@bind("the canvas and both overlay states change")
def workspace_changes(context) -> None:
    assert "focus-canvas" in context.driver.find_element(By.TAG_NAME, "body").get_attribute("class")
    assert set(context.overlay_values.values()) == {"false"}


@bind("I reload the viewer")
def reload_viewer(context) -> None:
    context.driver.refresh()
    _graph_nodes(context)


@bind("the legend and minimap preferences persist")
def overlay_persistence(context) -> None:
    for name, expected in context.overlay_values.items():
        assert context.driver.find_element(By.ID, f"{name}-toggle").get_attribute("aria-expanded") == expected


@bind("I open the BERT module workspace")
def open_bert_workspace(context) -> None:
    context.driver.get(f"{context.viewer_url}#/version/bert/view/module/module/encoder.layer/detail/trace/labels/source")
    _wait(context).until(
        lambda current: "/version/bert/view/module" in current.find_element(By.ID, "uri-input").get_attribute("value")
    )
    context.layout_node_id = "group:module-00009"
    _wait(context).until(lambda current: current.find_element(By.CSS_SELECTOR, f'.graph-node[data-id="{context.layout_node_id}"]'))


@bind("I drag and resize a graph node")
def drag_resize_node(context) -> None:
    for _ in range(12):
        if context.driver.find_element(By.ID, "graph-viewport").get_attribute("data-zoom-tier") == "normal":
            break
        context.driver.find_element(By.ID, "zoom-in").click()
    _wait(context).until(
        lambda current: current.find_element(By.CSS_SELECTOR, f'.graph-node[data-id="{context.layout_node_id}"] .node-drag-handle').is_displayed()
    )
    context.driver.execute_async_script(
        "const done=arguments[0]; requestAnimationFrame(() => requestAnimationFrame(done));"
    )
    node = context.driver.find_element(By.CSS_SELECTOR, f'.graph-node[data-id="{context.layout_node_id}"]')
    context.generated_box = _node_box(node)

    def drag_node(current):
        try:
            current_node = current.find_element(By.CSS_SELECTOR, f'.graph-node[data-id="{context.layout_node_id}"]')
            before = _node_box(current_node)
            ActionChains(current).drag_and_drop_by_offset(
                current_node.find_element(By.CSS_SELECTOR, ".node-drag-handle"), 120, 70
            ).perform()
            after = _node_box(current.find_element(By.CSS_SELECTOR, f'.graph-node[data-id="{context.layout_node_id}"]'))
            return after if abs(after[0] - before[0]) > 40 else False
        except (ElementNotInteractableException, StaleElementReferenceException):
            return False

    _wait(context).until(drag_node)

    def resize_node(current):
        try:
            current_node = current.find_element(By.CSS_SELECTOR, f'.graph-node[data-id="{context.layout_node_id}"]')
            before = _node_box(current_node)
            ActionChains(current).drag_and_drop_by_offset(
                current_node.find_element(By.CSS_SELECTOR, ".node-resize-handle"), 120, 80
            ).perform()
            after = _node_box(current.find_element(By.CSS_SELECTOR, f'.graph-node[data-id="{context.layout_node_id}"]'))
            return after if after[2] > before[2] + 60 else False
        except (ElementNotInteractableException, StaleElementReferenceException):
            return False

    context.custom_box = _wait(context).until(resize_node)
    context.layout_uri = context.driver.current_url


@bind("the custom node layout is stored locally")
def custom_layout_stored(context) -> None:
    assert abs(context.custom_box[0] - context.generated_box[0]) > 40
    assert context.custom_box[2] > context.generated_box[2] + 60
    assert context.driver.execute_script("return Object.keys(localStorage).some(key => key.startsWith('model-vis-layout:'))")


@bind("the custom node position and size are restored")
def custom_layout_restored(context) -> None:
    _wait(context).until(
        lambda current: "/version/bert/view/module" in current.find_element(By.ID, "uri-input").get_attribute("value")
    )
    for _ in range(12):
        if context.driver.find_element(By.ID, "graph-viewport").get_attribute("data-zoom-tier") == "normal":
            break
        context.driver.find_element(By.ID, "zoom-in").click()
    def layout_matches(current):
        # Read one rendered frame atomically; Fit can replace graph elements
        # between individual WebDriver property requests after a reload.
        restored = current.execute_script(
            "const node = document.querySelector(arguments[0]); if (!node) return null; "
            "const style = getComputedStyle(node); "
            "return ['left','top','width','height'].map(name => parseFloat(style[name]));",
            f'.graph-node[data-id="{context.layout_node_id}"]',
        )
        return restored and all(abs(actual - expected) < 3 for actual, expected in zip(restored, context.custom_box))

    assert _wait(context).until(layout_matches)


@bind("I reset the graph layout")
def reset_graph(context) -> None:
    context.driver.find_element(By.ID, "reset-button").click()


@bind("the node returns to its generated position and default size")
def default_layout_restored(context) -> None:
    def is_default(current):
        try:
            node = current.find_element(By.CSS_SELECTOR, f'.graph-node[data-id="{context.layout_node_id}"]')
            box = _node_box(node)
            return abs(box[2] - 248) < 1 and abs(box[3] - 168) < 1 and abs(box[0] - context.custom_box[0]) > 20
        except StaleElementReferenceException:
            return False

    assert _wait(context).until(is_default)


@bind("I select a semantic stage and change theme and labels")
def change_persisted_preferences(context) -> None:
    def select_second_stage(current):
        try:
            nodes = current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="semantic_stage"]')
            if not nodes:
                return False
            target = nodes[min(1, len(nodes) - 1)]
            target_id = target.get_attribute("data-id")
            current.execute_script("arguments[0].click()", target)
            context.persisted_stage = target_id
            return True
        except StaleElementReferenceException:
            return False

    _wait(context).until(select_second_stage)
    _wait(context).until(
        lambda current: current.find_element(By.CSS_SELECTOR, ".graph-node.selected").get_attribute("data-id") == context.persisted_stage
    )
    context.driver.find_element(By.ID, "theme-button").click()
    context.persisted_theme = context.driver.execute_script("return document.documentElement.dataset.theme")
    _select(context, "label-mode", "both")


@bind("the selected stage and explicit choices appear in the URI")
def deep_uri(context) -> None:
    uri = context.driver.find_element(By.ID, "uri-input").get_attribute("value")
    assert "/stage/" in uri
    assert "/detail/beginner/labels/both" in uri


@bind("theme, labels, and semantic stage selection persist")
def persisted_preferences(context) -> None:
    expected = [context.persisted_theme, "both", context.persisted_stage]
    assert _wait(context).until(lambda current: current.execute_script(
        "return [document.documentElement.dataset.theme, "
        "document.querySelector('#label-mode').value, "
        "document.querySelector('.graph-node.selected')?.dataset.id];"
    ) == expected)


@bind("I open comparison without selecting two models")
def open_empty_compare(context) -> None:
    context.driver.find_element(By.ID, "compare-button").click()


@bind("comparison explains that two models are required")
def compare_guidance(context) -> None:
    assert "Select two models" in context.driver.find_element(By.ID, "compare-content").text
    assert not context.driver.find_element(By.ID, "compare-pane").get_attribute("hidden")


@bind("I close comparison and select DINOv3 and Moshi")
def choose_compare_models(context) -> None:
    context.driver.find_element(By.ID, "close-compare").click()
    for query in ("DINOv3", "Moshi"):
        search = context.driver.find_element(By.ID, "search")
        search.clear()
        search.send_keys(query)
        _wait(context).until(lambda current: current.find_element(By.ID, "result-count").text == "1 model")
        checkbox = context.driver.find_element(By.CSS_SELECTOR, ".compare-check input")
        context.driver.execute_script("arguments[0].click()", checkbox)
    assert context.driver.find_element(By.ID, "compare-count").text == "2"


@bind("I open comparison")
def open_selected_compare(context) -> None:
    context.driver.find_element(By.ID, "compare-button").click()
    _wait(context).until(lambda current: len(current.find_elements(By.CSS_SELECTOR, ".compare-table")) >= 4)


@bind("normalized stages, exact tags, distributions, and config results are shown")
def complete_comparison(context) -> None:
    text = context.driver.find_element(By.ID, "compare-content").text
    for expected in (
        "Semantic stage presence and order",
        "Exact class/interface tags",
        "Stage parameter and operation distributions",
        "Config fields changed",
    ):
        assert expected in text


@bind("I close comparison")
def close_comparison(context) -> None:
    context.driver.find_element(By.ID, "close-compare").click()


@bind("the graph workspace is available again")
def graph_after_compare(context) -> None:
    assert context.driver.find_element(By.ID, "compare-pane").get_attribute("hidden")
    assert context.driver.find_elements(By.CSS_SELECTOR, ".graph-node")


@bind("I search for and open the partial DINOv3 record")
def open_partial_record(context) -> None:
    context.driver.get(context.viewer_url)
    _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".model-item"))
    search = context.driver.find_element(By.ID, "search")
    search.clear()
    search.send_keys("DINOv3")
    _wait(context).until(lambda current: current.find_element(By.ID, "result-count").text == "1 model")
    context.partial_badge_text = context.driver.find_element(By.CSS_SELECTOR, ".model-warning-badge").get_attribute("data-tooltip")
    context.driver.find_element(By.CSS_SELECTOR, ".model-open").click()


@bind("the catalog badge and inspector warning explain partial official configuration coverage")
def partial_warning(context) -> None:
    warning = _wait(context).until(lambda current: current.find_element(By.ID, "model-warning"))
    _wait(context).until(lambda current: warning.is_displayed())
    assert "official config" in warning.text.lower()
    assert context.partial_badge_text


@bind("I open the Data2Vec module workspace")
def open_data2vec(context) -> None:
    context.driver.get(
        f"{context.viewer_url}#/version/data2vec-3/view/operation/"
        "module/encoder.layer.0.attention.attention/detail/trace/labels/source"
    )
    _wait(context).until(
        lambda current: "/version/data2vec-3/view/operation" in current.find_element(By.ID, "uri-input").get_attribute("value")
    )
    _graph_nodes(context, '.graph-node[data-kind="aten_op"]')
    _click_first(context, '.graph-node[data-kind="aten_op"]')
    context.driver.find_element(By.CSS_SELECTOR, '[data-panel="source"]').click()
    _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".source-code-line"))
    context.driver.find_element(By.CSS_SELECTOR, '[data-navigator="modules"]').click()


@bind("I search the module tree for attention")
def search_module_tree(context) -> None:
    search = context.driver.find_element(By.ID, "module-search")
    search.clear()
    search.send_keys("attention")


@bind("matching hierarchy rows remain visible")
def hierarchy_matches(context) -> None:
    rows = _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, "#module-tree .tree-row"))
    assert any("attention" in row.text.lower() for row in rows)


@bind("I use Home, End, Left, and Right in the module tree")
def keyboard_tree(context) -> None:
    search = context.driver.find_element(By.ID, "module-search")
    search.clear()
    search.send_keys(" ")
    search.send_keys(Keys.BACKSPACE)
    root = _wait(context).until(lambda current: current.find_element(By.CSS_SELECTOR, '#module-tree .tree-row[data-module-path="<root>"]'))
    context.driver.execute_script("arguments[0].focus()", root)
    root.send_keys(Keys.END)
    context.end_path = context.driver.switch_to.active_element.get_attribute("data-module-path")
    context.driver.switch_to.active_element.send_keys(Keys.HOME)
    root = context.driver.switch_to.active_element
    context.home_path = root.get_attribute("data-module-path")
    root.send_keys(Keys.ARROW_LEFT)
    root = _wait(context).until(lambda current: current.find_element(By.CSS_SELECTOR, '#module-tree .tree-row[data-module-path="<root>"][aria-expanded="false"]'))
    context.collapsed = root.get_attribute("aria-expanded")
    context.driver.execute_script("arguments[0].focus()", root)
    root.send_keys(Keys.ARROW_RIGHT)
    context.expanded = _wait(context).until(lambda current: current.find_element(By.CSS_SELECTOR, '#module-tree .tree-row[data-module-path="<root>"]')).get_attribute("aria-expanded")


@bind("keyboard focus and expansion follow tree navigation rules")
def keyboard_tree_rules(context) -> None:
    assert context.end_path != "<root>"
    assert context.home_path == "<root>"
    assert context.collapsed == "false"
    assert context.expanded == "true"


@bind("I open the source-file navigator")
def source_navigator(context) -> None:
    context.driver.find_element(By.CSS_SELECTOR, '[data-navigator="files"]').click()


@bind("the source file hierarchy and selected source panel are available")
def source_tree(context) -> None:
    assert len(_wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, "#source-tree .tree-row"))) > 1
    assert "active" in context.driver.find_element(By.ID, "source-panel").get_attribute("class")
    assert context.driver.find_elements(By.CSS_SELECTOR, ".source-code-line")


@bind("I open DINOv3 on a mobile viewport")
def open_mobile(context) -> None:
    set_exact_viewport(context.driver, 390, 844)
    inspect_architecture(context)


@bind("I open the catalog drawer")
def open_mobile_catalog(context) -> None:
    context.driver.find_element(By.ID, "menu-button").click()


@bind("the catalog drawer and scrim are visible")
def mobile_catalog_visible(context) -> None:
    assert "open" in context.driver.find_element(By.ID, "sidebar").get_attribute("class")
    assert not context.driver.find_element(By.ID, "scrim").get_attribute("hidden")


@bind("I dismiss the drawer and select a graph stage")
def open_mobile_inspector(context) -> None:
    context.driver.find_element(By.ID, "scrim").click()
    _wait(context).until(lambda current: "open" not in current.find_element(By.ID, "sidebar").get_attribute("class"))
    _click_first(context, '.graph-node[data-kind="semantic_stage"]')


@bind("the mobile inspector drawer opens and can be dismissed")
def mobile_inspector(context) -> None:
    _wait(context).until(lambda current: "open" in current.find_element(By.ID, "inspector").get_attribute("class"))
    context.driver.find_element(By.ID, "scrim").click()
    _wait(context).until(lambda current: "open" not in current.find_element(By.ID, "inspector").get_attribute("class"))
    set_exact_viewport(context.driver, 1440, 900)


@bind("I run the DINOv3 Tensor Journey")
def run_tensor_journey(context) -> None:
    inspect_architecture(context)
    context.driver.find_element(By.CSS_SELECTOR, '[data-panel="shapes"]').click()
    _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".journey-step"))


@bind("journey steps use generated tensors")
def generated_journey(context) -> None:
    steps = context.driver.find_elements(By.CSS_SELECTOR, ".journey-step")
    assert len(steps) >= 2
    assert sum("[" in step.text and "]" in step.text for step in steps) >= 2


@bind("I compare Moshi with DINOv3")
def compare_models(context) -> None:
    context.driver.get(f"{context.viewer_url}#/compare/moshi/dinov3/view/architecture/detail/standard/labels/both")
    _wait(context).until(lambda current: len(current.find_elements(By.CSS_SELECTOR, ".compare-table")) >= 3)


@bind("normalized stages and config results are shown")
def normalized_comparison(context) -> None:
    content = context.driver.find_element(By.ID, "compare-content")
    assert "Semantic stage presence and order" in content.text
    assert "Config fields changed" in content.text


@bind("I inspect DINOv3 parameter and operation distributions")
def inspect_distributions(context) -> None:
    inspect_architecture(context)
    _wait(context).until(lambda current: len(current.find_elements(By.CSS_SELECTOR, ".distribution-section")) == 2)


@bind("both mapped distributions are visible")
def mapped_distributions(context) -> None:
    sections = context.driver.find_elements(By.CSS_SELECTOR, ".distribution-section")
    assert len(sections) == 2
    assert all("mapped" in section.text for section in sections)
    assert all(section.find_elements(By.CSS_SELECTOR, ".distribution-segment") for section in sections)


@bind("I open a semantic stage explanation")
def open_stage_explanation(context) -> None:
    _click_first(context, '.graph-node[data-kind="semantic_stage"]')
    context.driver.find_element(By.CSS_SELECTOR, '[data-panel="explain"]').click()


@bind("the explanation, Tensor Journey, and mapped distributions are visible")
def complete_explanation(context) -> None:
    assert _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".explain-card"))
    assert context.driver.find_elements(By.CSS_SELECTOR, ".journey-step")
    assert len(context.driver.find_elements(By.CSS_SELECTOR, ".distribution-section")) == 2


@bind("I switch the demonstration to Trace source evidence")
def demo_trace_source(context) -> None:
    _select(context, "detail-mode", "trace")
    _click_first(context, '.graph-node[data-kind="aten_op"]')
    context.driver.find_element(By.CSS_SELECTOR, '[data-panel="source"]').click()


@bind("source lines, runtime facts, and configuration choices are available")
def demo_trace_evidence(context) -> None:
    assert _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".source-code-line"))
    context.driver.find_element(By.CSS_SELECTOR, '[data-panel="runtime"]').click()
    assert _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".runtime-row"))
    context.driver.find_element(By.CSS_SELECTOR, '[data-panel="config"]').click()
    assert _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, "#config-view .config-provenance"))


@bind("I begin a recorded demo")
def begin_recording(context) -> None:
    _run_demo_command(
        "DEMO_RECORD_START_COMMAND",
        {"DEMO_SUITE": getattr(context, "suite", "demo"), "DEMO_REPOSITORY": "model_vis"},
    )
    context.demo_recording = True


@bind("I finish the recorded demo")
def finish_recording(context) -> None:
    if not getattr(context, "demo_recording", False):
        return
    _run_demo_command(
        "DEMO_RECORD_STOP_COMMAND",
        {"DEMO_SUITE": getattr(context, "suite", "demo"), "DEMO_REPOSITORY": "model_vis"},
    )
    context.demo_recording = False


NARRATIONS = {
    "I narrate in English for at least 9 seconds: Model Structure Viewer turns generated PyTorch architecture metadata into an offline interactive catalog of one hundred and one models, without downloading weights or running remote model code.": (
        "en-US", 9, "Model Structure Viewer turns generated PyTorch architecture metadata into an offline interactive catalog of one hundred and one models, without downloading weights or running remote model code."
    ),
    "I narrate in English for at least 11 seconds: Beginner view groups technical modules into meaningful stages. Select a stage to read its purpose, follow the generated tensor journey, and compare how parameters and operations are distributed.": (
        "en-US", 11, "Beginner view groups technical modules into meaningful stages. Select a stage to read its purpose, follow the generated tensor journey, and compare how parameters and operations are distributed."
    ),
    "I narrate in English for at least 11 seconds: Trace view exposes modules, operations, runtime facts, redistributed source lines, and the difference between pinned official configuration and the compact trace configuration.": (
        "en-US", 11, "Trace view exposes modules, operations, runtime facts, redistributed source lines, and the difference between pinned official configuration and the compact trace configuration."
    ),
    "I narrate in English for at least 10 seconds: Comparison normalizes two different model families by stage, exact interface tags, trace distributions, and configuration differences, while keeping the original evidence available for inspection.": (
        "en-US", 10, "Comparison normalizes two different model families by stage, exact interface tags, trace distributions, and configuration differences, while keeping the original evidence available for inspection."
    ),
    "I narrate in Cantonese for at least 9 seconds: Model Structure Viewer 將產生好嘅 PyTorch 架構資料整理成離線互動目錄，入面有一百零一個模型，唔需要下載權重，亦唔會執行遠端模型程式碼。": (
        "yue-HK", 9, "Model Structure Viewer 將產生好嘅 PyTorch 架構資料整理成離線互動目錄，入面有一百零一個模型，唔需要下載權重，亦唔會執行遠端模型程式碼。"
    ),
    "I narrate in Cantonese for at least 11 seconds: 初學者模式會將技術模組整理成有意思嘅階段。揀一個階段，就可以睇用途、跟住產生好嘅張量流程，再比較參數同運算分佈。": (
        "yue-HK", 11, "初學者模式會將技術模組整理成有意思嘅階段。揀一個階段，就可以睇用途、跟住產生好嘅張量流程，再比較參數同運算分佈。"
    ),
    "I narrate in Cantonese for at least 11 seconds: 追蹤模式會顯示模組、運算、執行資料、可重新發布嘅源碼行，仲可以比較固定官方設定同精簡追蹤設定有咩分別。": (
        "yue-HK", 11, "追蹤模式會顯示模組、運算、執行資料、可重新發布嘅源碼行，仲可以比較固定官方設定同精簡追蹤設定有咩分別。"
    ),
    "I narrate in Cantonese for at least 10 seconds: 比較功能會按語意階段、精確介面標籤、追蹤分佈同設定差異整理兩個模型，同時保留原始證據畀你逐項檢查。": (
        "yue-HK", 10, "比較功能會按語意階段、精確介面標籤、追蹤分佈同設定差異整理兩個模型，同時保留原始證據畀你逐項檢查。"
    ),
}


def _narration_binding(language: str, seconds: int, narration: str):
    def execute_narration(context) -> None:
        _narrate(language, seconds, narration)

    return execute_narration


for _step_text, _narration_values in NARRATIONS.items():
    bind(_step_text)(_narration_binding(*_narration_values))
