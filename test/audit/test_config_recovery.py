import json
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from test.audit.network_server import fault_server
from test.e2e.audit_helpers import open_model,visible_click
from test.e2e.browser import set_exact_viewport


def test_failed_configuration_recovers_the_selected_operation(driver,viewer_url):
    set_exact_viewport(driver,1440,1000)
    version=json.loads((Path(__file__).parents[2]/"model_code/versions/bert.json").read_text())
    with fault_server() as (url,fault):
        open_model(driver,url,"bert","operation","/operation/op-000028")
        fault.update(path=version["official_config_ref"],status=503)
        visible_click(driver,'.inspector-tab[data-panel="config"]')
        retry=WebDriverWait(driver,10).until(lambda d:d.find_element(By.CSS_SELECTOR,"#config-view button"))
        assert "could not be loaded" in driver.find_element(By.ID,"config-view").text
        fault["status"]=None;retry.click()
        WebDriverWait(driver,10).until(lambda d:d.find_elements(By.CSS_SELECTOR,".config-row"))
        assert "gelu" in driver.find_element(By.ID,"inspector-title").text
