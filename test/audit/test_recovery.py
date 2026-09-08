import json
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from test.audit.network_server import fault_server
from test.e2e.audit_helpers import open_model,settle,visible_click
from test.e2e.browser import set_exact_viewport

ROOT=Path(__file__).parents[2]/"model_code"


def test_graph_503_retry_restores_the_requested_gelu(driver,viewer_url):
    set_exact_viewport(driver,1440,1000)
    with fault_server() as (url,fault):
        version=json.loads((ROOT/"versions/bert.json").read_text())
        fault.update(path=version["graph_ref"],status=503)
        driver.get(f"{url}#/version/bert/view/operation/operation/op-000028/detail/trace/labels/source")
        wait=WebDriverWait(driver,15)
        retry=wait.until(lambda d:d.find_element(By.CSS_SELECTOR,"#empty-state button"))
        assert "sha256" not in driver.find_element(By.ID,"empty-state").text
        fault["status"]=None;retry.click()
        wait.until(lambda d:d.find_elements(By.CSS_SELECTOR,'.graph-node.selected[data-id="op-000028"]'))
        assert "gelu" in driver.find_element(By.ID,"inspector-title").text


def test_offline_navigation_offers_retry_and_keeps_requested_operation(driver,viewer_url):
    set_exact_viewport(driver,1440,1000)
    open_model(driver,viewer_url)
    driver.execute_cdp_cmd("Network.enable",{})
    try:
        driver.execute_cdp_cmd("Network.emulateNetworkConditions",dict(offline=True,latency=0,downloadThroughput=-1,uploadThroughput=-1))
        field=driver.find_element(By.ID,"uri-input");field.clear()
        field.send_keys("modelvis:/version/bert/view/operation/operation/op-000028/detail/trace/labels/source",Keys.ENTER)
        retry=WebDriverWait(driver,10).until(lambda d:d.find_element(By.CSS_SELECTOR,"#empty-state button"))
        driver.execute_cdp_cmd("Network.emulateNetworkConditions",dict(offline=False,latency=0,downloadThroughput=-1,uploadThroughput=-1))
        retry.click()
        WebDriverWait(driver,15).until(lambda d:d.find_elements(By.CSS_SELECTOR,'.graph-node.selected[data-id="op-000028"]'))
    finally:driver.execute_cdp_cmd("Network.emulateNetworkConditions",dict(offline=False,latency=0,downloadThroughput=-1,uploadThroughput=-1))
