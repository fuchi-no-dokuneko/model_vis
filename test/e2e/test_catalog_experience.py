from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select, WebDriverWait

from test.e2e.browser import set_exact_viewport


def submit_location(driver, location):
    field = driver.find_element(By.ID, "uri-input")
    field.clear()
    field.send_keys(location, Keys.ENTER)


def settle(driver):
    driver.execute_async_script("const done = arguments[0]; setTimeout(done, 250);")


def test_invalid_location_survives_graph_updates_and_recovers(loaded_viewer):
    driver = loaded_viewer
    wait = WebDriverWait(driver, 10)
    submit_location(driver, "modelvis:/version/not-a-model")
    settle(driver)
    assert "Unknown model version: not-a-model" in driver.find_element(By.ID, "graph-status").text
    for control in ("zoom-in", "fit-button"):
        driver.find_element(By.ID, control).click()
        settle(driver)
        assert "Unknown model version: not-a-model" in driver.find_element(By.ID, "graph-status").text
    assert driver.find_element(By.ID, "uri-input").get_attribute("aria-invalid") == "true"
    submit_location(driver, "modelvis:/version/apertus/view/architecture")
    wait.until(lambda current: current.find_element(By.ID, "uri-input").get_attribute("aria-invalid") != "true")
    settle(driver)
    assert "Unknown model version" not in driver.find_element(By.ID, "graph-status").text
    assert driver.find_elements(By.CSS_SELECTOR, ".graph-node")


def test_invalid_deep_link_on_reload_can_recover(driver, viewer_url):
    driver.get(f"{viewer_url}#/version/not-a-model")
    wait = WebDriverWait(driver, 10)
    wait.until(lambda current: "Unknown model version" in current.find_element(By.ID, "graph-status").text)
    submit_location(driver, "modelvis:/version/apertus/view/module/module/no-such-module")
    wait.until(lambda current: "Unknown module path" in current.find_element(By.ID, "graph-status").text)
    settle(driver)
    assert "no-such-module" in driver.find_element(By.ID, "uri-input").get_attribute("value")
    driver.find_element(By.ID, "fit-button").click()
    settle(driver)
    assert "Unknown module path" in driver.find_element(By.ID, "graph-status").text
    submit_location(driver, "modelvis:/version/apertus/view/architecture")
    wait.until(lambda current: current.find_element(By.ID, "uri-input").get_attribute("aria-invalid") == "false")
    assert driver.find_elements(By.CSS_SELECTOR, ".graph-node")


def test_favorites_persist_filter_and_support_keyboard(loaded_viewer):
    driver = loaded_viewer
    wait = WebDriverWait(driver, 10)
    # A malformed saved value must not break catalog initialization.
    driver.execute_script("localStorage.setItem('model-vis-favorites', '{bad json')")
    driver.refresh()
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, ".favorite-button"))
    button = driver.find_element(By.CSS_SELECTOR, ".favorite-button")
    version_id = button.get_attribute("data-version-id")
    before_route = driver.current_url
    button.send_keys(Keys.SPACE)
    assert button.get_attribute("aria-pressed") == "true"
    assert driver.switch_to.active_element == button
    assert driver.current_url == before_route
    driver.find_element(By.ID, "favorites-only").click()
    assert driver.find_element(By.ID, "result-count").text == "1 model"
    assert driver.find_element(By.CSS_SELECTOR, ".favorite-button").get_attribute("data-version-id") == version_id
    Select(driver.find_element(By.ID, "category")).select_by_value("Vision models")
    assert driver.find_element(By.ID, "catalog-empty").is_displayed()
    Select(driver.find_element(By.ID, "category")).select_by_value("")
    assert driver.find_element(By.ID, "result-count").text == "1 model"
    driver.find_element(By.ID, "search").send_keys("not-a-model")
    assert driver.find_element(By.ID, "catalog-empty").is_displayed()
    assert driver.find_element(By.ID, "result-count").text == "0 models"
    driver.refresh()
    wait.until(lambda current: current.find_elements(By.CSS_SELECTOR, ".favorite-button"))
    button = driver.find_element(By.CSS_SELECTOR, f'.favorite-button[data-version-id="{version_id}"]')
    assert button.get_attribute("aria-pressed") == "true"
    driver.find_element(By.ID, "favorites-only").click()
    driver.find_element(By.CSS_SELECTOR, ".favorite-button").send_keys(Keys.ENTER)
    assert driver.find_element(By.ID, "catalog-empty").is_displayed()
    assert driver.switch_to.active_element == driver.find_element(By.ID, "favorites-only")
    driver.find_element(By.ID, "favorites-only").click()
    assert len(driver.find_elements(By.CSS_SELECTOR, ".model-item")) > 1
    driver.execute_script("localStorage.removeItem('model-vis-favorites')")


def test_favorites_remain_usable_when_storage_is_unavailable(loaded_viewer):
    driver = loaded_viewer
    driver.execute_script(
        "const original = Storage.prototype.setItem; "
        "Storage.prototype.setItem = function(key, value) { "
        "if (key === 'model-vis-favorites') throw new DOMException('Storage full', 'QuotaExceededError'); "
        "return original.call(this, key, value); };"
    )
    driver.find_element(By.CSS_SELECTOR, ".favorite-button").click()
    assert "browser storage is unavailable" in driver.find_element(By.ID, "graph-status").text
    driver.find_element(By.ID, "favorites-only").click()
    assert driver.find_element(By.ID, "result-count").text == "1 model"
    driver.refresh()


def test_filter_after_scrolling_shows_matching_models(loaded_viewer):
    driver = loaded_viewer
    driver.execute_script("const list = document.querySelector('#model-list'); list.scrollTop = list.scrollHeight;")
    settle(driver)
    driver.find_element(By.ID, "search").send_keys("apertus")
    assert driver.find_element(By.ID, "result-count").text == "1 model"
    assert driver.find_element(By.CSS_SELECTOR, ".model-open").is_displayed()
    assert "Apertus" in driver.find_element(By.CSS_SELECTOR, ".model-open").text
    assert driver.execute_script("return document.querySelector('#model-list').scrollTop") == 0


def test_favorites_are_clickable_above_the_mobile_backdrop(loaded_viewer):
    driver = loaded_viewer
    set_exact_viewport(driver, 390, 844)
    driver.find_element(By.ID, "menu-button").click()
    settle(driver)
    button = driver.find_element(By.CSS_SELECTOR, ".favorite-button")
    assert driver.execute_script(
        "const button=arguments[0], r=button.getBoundingClientRect(); "
        "return button.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));", button
    )
    button.click()
    driver.find_element(By.ID, "favorites-only").click()
    assert driver.find_element(By.ID, "result-count").text == "1 model"
    driver.execute_script("localStorage.removeItem('model-vis-favorites')")
