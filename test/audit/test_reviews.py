import csv
import json
from uuid import uuid4
from xml.etree import ElementTree

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from test.e2e.audit_helpers import ARTIFACTS,open_model,settle,visible_click
from test.e2e.browser import set_exact_viewport


def test_saved_annotation_and_downloaded_subgraph_reproduce_selection(driver,viewer_url):
    set_exact_viewport(driver,1440,1000)
    open_model(driver,viewer_url,"bert","operation","/operation/op-000028")
    driver.execute_script("localStorage.removeItem('model-vis-reviews')")
    driver.refresh();settle(driver)
    visible_click(driver,"#review-button")
    name=driver.find_element(By.ID,"review-name");name.send_keys("GELU audit review")
    note='GELU "preserves" 3072 dimensions.'
    driver.find_element(By.ID,"review-annotation").send_keys(note)
    visible_click(driver,"#save-review")
    folder=(ARTIFACTS/"downloads"/uuid4().hex).resolve();folder.mkdir(parents=True)
    driver.execute_cdp_cmd("Browser.setDownloadBehavior",dict(behavior="allow",downloadPath=str(folder)))
    for extension in ["json","csv","svg"]:
        visible_click(driver,f"#export-{extension}")
        WebDriverWait(driver,10).until(lambda d:(folder/f"bert-investigation.{extension}").exists())
    facts=json.loads((folder/"bert-investigation.json").read_text())
    assert facts["nodes"][0]["id"]=="op-000028" and facts["annotation"]==note
    assert facts["provenance"]["repo_id"]=="google-bert/bert-base-uncased"
    with (folder/"bert-investigation.csv").open() as file:
        rows=list(csv.DictReader(file))
    assert rows[0]["annotation"]==note and rows[0]["operation_id"]=="op-000028"
    svg=ElementTree.parse(folder/"bert-investigation.svg")
    embedded=json.loads(svg.getroot().find("{http://www.w3.org/2000/svg}metadata").text)
    assert embedded["selection"]==facts["selection"]
    driver.refresh();settle(driver);visible_click(driver,"#review-button")
    driver.find_element(By.XPATH,"//div[@id='saved-reviews']//button[text()='GELU audit review']").click()
    WebDriverWait(driver,15).until(lambda d:d.find_elements(By.CSS_SELECTOR,'.graph-node.selected[data-id="op-000028"]'))
    assert driver.find_element(By.ID,"review-annotation").get_attribute("value")==note
