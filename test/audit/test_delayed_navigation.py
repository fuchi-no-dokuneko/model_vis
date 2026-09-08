import json
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from test.audit.network_server import fault_server
from test.e2e.audit_helpers import open_model,visible_click
from test.e2e.browser import set_exact_viewport

ROOT=Path(__file__).parents[2]/"model_code"


def navigate(driver,model,operation):
    field=driver.find_element(By.ID,"uri-input");field.clear()
    field.send_keys(f"modelvis:/version/{model}/view/operation/operation/{operation}/detail/standard/labels/both",Keys.ENTER)


def wait_for_response(driver):
    driver.execute_async_script("setTimeout(arguments[0],3500)")


def test_delayed_graph_cannot_replace_a_newer_model_selection(driver,viewer_url):
    set_exact_viewport(driver,1440,1000)
    version=json.loads((ROOT/"versions/bert.json").read_text())
    with fault_server() as (url,fault):
        fault.update(path=version["graph_ref"],delay=3)
        driver.get(f"{url}#/version/bert/view/operation/operation/op-000028")
        WebDriverWait(driver,10).until(lambda d:fault["hits"])
        navigate(driver,"bit","op-000004")
        WebDriverWait(driver,15).until(lambda d:d.find_elements(By.CSS_SELECTOR,'.graph-node.selected[data-id="op-000004"]'))
        wait_for_response(driver)
        assert "/version/bit/" in driver.current_url
        assert "pad" in driver.find_element(By.ID,"inspector-title").text
        assert not driver.find_element(By.ID,"uri-input").get_attribute("aria-invalid")=="true"


def test_delayed_config_cannot_be_cached_as_another_models_config(driver,viewer_url):
    set_exact_viewport(driver,1440,1000)
    version=json.loads((ROOT/"versions/bert.json").read_text())
    with fault_server() as (url,fault):
        open_model(driver,url,"bert")
        fault.update(path=version["official_config_ref"],delay=3)
        visible_click(driver,'.inspector-tab[data-panel="config"]')
        WebDriverWait(driver,10).until(lambda d:fault["hits"])
        navigate(driver,"arcee","op-000004")
        wait_for_response(driver)
        visible_click(driver,'.inspector-tab[data-panel="config"]')
        WebDriverWait(driver,10).until(lambda d:d.find_elements(By.CSS_SELECTOR,".config-row"))
        assert driver.find_element(By.XPATH,"//div[contains(@class,'config-row')][span[text()='model_type']]/span[2]").text=='arcee'
