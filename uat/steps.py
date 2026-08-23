from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .gherkin import bind


def _wait(context):
    return WebDriverWait(context.driver, 15)


@bind("the built Model Vis site is running")
def built_site(context) -> None:
    assert context.viewer_url.startswith("http://127.0.0.1:")


@bind("I open the model catalog")
def open_catalog(context) -> None:
    context.driver.get(context.viewer_url)
    _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".model-item"))


@bind("51 generated models are listed")
def catalog_count(context) -> None:
    _wait(context).until(lambda current: current.find_element(By.ID, "result-count").text == "51 models")


@bind("I inspect DINOv3 semantic architecture")
def inspect_architecture(context) -> None:
    context.driver.get(f"{context.viewer_url}#/version/dinov3/view/architecture/detail/beginner/labels/semantic")
    _wait(context).until(lambda current: current.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="semantic_stage"]'))


@bind("semantic stages and exact tags are shown")
def semantic_stages(context) -> None:
    nodes = context.driver.find_elements(By.CSS_SELECTOR, '.graph-node[data-kind="semantic_stage"]')
    assert len(nodes) >= 3
    assert context.driver.find_elements(By.CSS_SELECTOR, ".confidence-label")


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
