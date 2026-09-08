import json
from pathlib import Path

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from test.e2e.audit_helpers import open_model,screenshot,visible_click
from test.e2e.browser import set_exact_viewport

MODELS=["bit","bert","bertjapanese","apertus","arcee","afmoe","aimv2","clip",
        "moshi","autoencoderkl","autoencoderklkvae","gemma2"]


@pytest.mark.parametrize("model",MODELS)
def test_detailed_model_views_and_all_inspector_panels(driver,viewer_url,model):
    set_exact_viewport(driver,1440,1000)
    open_model(driver,viewer_url,model)
    driver.get_log("browser")
    for view in ["architecture","family","module","blocks","operation"]:
        visible_click(driver,f'.mode[data-mode="{view}"]')
        assert driver.find_elements(By.CSS_SELECTOR,".graph-node")
    root=Path(__file__).parents[2]/"model_code"
    version=json.loads((root/f"versions/{model}.json").read_text())
    graph=json.loads((root/version["graph_ref"]).read_text())
    node=next(n for n in graph["nodes"] if n["kind"]=="aten_op")
    address=driver.find_element(By.ID,"uri-input");address.clear()
    address.send_keys(f'modelvis:/version/{model}/view/operation/operation/{node["id"]}/detail/standard/labels/both',Keys.ENTER)
    WebDriverWait(driver,15).until(lambda d:d.find_elements(By.CSS_SELECTOR,f'.graph-node.selected[data-id="{node["id"]}"]'))
    for panel in ["explain","details","shapes","source","runtime","config"]:
        visible_click(driver,f'.inspector-tab[data-panel="{panel}"]')
        element=driver.find_element(By.ID,f"{panel}-panel")
        assert element.is_displayed() and element.text.strip()
        assert driver.execute_script("return document.documentElement.scrollWidth")==1440
    assert not [e for e in driver.get_log("browser") if e["level"]=="SEVERE"]
    screenshot(driver,f"inspector-{model}-config")
