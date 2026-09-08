import csv
import json
from pathlib import Path
from xml.etree import ElementTree

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from test.e2e.audit_helpers import open_model,visible_click
from .gherkin import bind


@bind("I save an annotated GELU review and export its facts")
def save_export(context):
    driver=context.driver
    open_model(driver,context.viewer_url,"bert","operation","/operation/op-000028")
    visible_click(driver,"#review-button")
    driver.find_element(By.ID,"review-name").send_keys("Daily GELU review")
    context.note="Observed GELU shape [3, 5, 3072]."
    driver.find_element(By.ID,"review-annotation").send_keys(context.note)
    visible_click(driver,"#save-review")
    folder=Path(__file__).parents[1]/"artifacts/uat/review-exports"
    folder.mkdir(parents=True,exist_ok=True);context.exports=folder
    driver.execute_cdp_cmd("Browser.setDownloadBehavior",dict(behavior="allow",downloadPath=str(folder)))
    for extension in ["json","csv","svg"]:
        visible_click(driver,f"#export-{extension}")
        WebDriverWait(driver,10).until(lambda d:(folder/f"bert-investigation.{extension}").exists())


@bind("the downloaded files preserve GELU and its provenance")
def exported_facts(context):
    folder=context.exports
    facts=json.loads((folder/"bert-investigation.json").read_text())
    assert facts["nodes"][0]["id"]=="op-000028" and facts["annotation"]==context.note
    assert facts["provenance"]["repo_id"]=="google-bert/bert-base-uncased"
    with (folder/"bert-investigation.csv").open() as file: rows=list(csv.DictReader(file))
    assert rows[0]["operation_id"]=="op-000028"
    svg=ElementTree.parse(folder/"bert-investigation.svg")
    data=json.loads(svg.getroot().find("{http://www.w3.org/2000/svg}metadata").text)
    assert data["selection"]==facts["selection"]


@bind("I restore the saved review from another model")
def restore(context):
    driver=context.driver
    open_model(driver,context.viewer_url,"bit")
    visible_click(driver,"#review-button")
    driver.find_element(By.XPATH,"//div[@id='saved-reviews']//button[text()='Daily GELU review']").click()
    WebDriverWait(driver,15).until(lambda d:"/version/bert/" in d.current_url and d.find_elements(By.CSS_SELECTOR,'.graph-node.selected[data-id="op-000028"]'))


@bind("BERT GELU and the saved annotation are restored")
def restored(context):
    assert "gelu" in context.driver.find_element(By.ID,"inspector-title").text
    assert context.driver.find_element(By.ID,"review-annotation").get_attribute("value")==context.note
