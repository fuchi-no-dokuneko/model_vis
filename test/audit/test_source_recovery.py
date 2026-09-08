import json
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from test.audit.network_server import fault_server
from test.e2e.audit_helpers import open_model,visible_click
from test.e2e.browser import set_exact_viewport

ROOT=Path(__file__).parents[2]/"model_code"


def test_failed_source_can_retry_without_losing_selection(driver,viewer_url):
    set_exact_viewport(driver,1440,1000)
    version=json.loads((ROOT/"versions/bert.json").read_text())
    graph=json.loads((ROOT/version["graph_ref"]).read_text())
    node=next(n for n in graph["nodes"] if n["id"]=="op-000028")
    source=json.loads((ROOT/f"sources/{node['source_ref']['source_uid']}.json").read_text())
    with fault_server() as (url,fault):
        open_model(driver,url,"bert","operation","/operation/op-000028")
        fault.update(path=source["asset_path"],status=503)
        visible_click(driver,'.inspector-tab[data-panel="source"]')
        retry=WebDriverWait(driver,10).until(lambda d:d.find_element(By.CSS_SELECTOR,"#source-lines button"))
        assert "Diagnostic details" in driver.find_element(By.ID,"source-lines").text
        assert "sha256" not in driver.find_element(By.ID,"source-lines").text
        fault["status"]=None;retry.click()
        WebDriverWait(driver,15).until(lambda d:d.find_elements(By.CSS_SELECTOR,".source-code-line.active"))
        assert driver.find_elements(By.CSS_SELECTOR,'.graph-node.selected[data-id="op-000028"]')
