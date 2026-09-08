from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select,WebDriverWait

from test.e2e.audit_helpers import open_model,settle,visible_click
from .gherkin import bind


@bind("I filter GELU by module, dtype and shape")
def filter_gelu(context):
    driver=context.driver
    open_model(driver,context.viewer_url,"bert")
    driver.find_element(By.ID,"graph-search").send_keys("gelu")
    visible_click(driver,"#finder-panel > summary")
    for key,value in [("module","encoder.layer.0."),("dtype","float32"),("shape","[3,5,3072]")]:
        driver.find_element(By.CSS_SELECTOR,f'[data-finder="{key}"]').send_keys(value)


@bind("the finder identifies the exact GELU interface and opens it")
def exact_gelu(context):
    driver=context.driver
    assert "1 matches" in driver.find_element(By.ID,"finder-status").text
    assert "aten.gelu.default" in driver.find_element(By.CSS_SELECTOR,".finder-table").text
    visible_click(driver,".finder-table button")
    assert driver.find_elements(By.CSS_SELECTOR,'.graph-node.selected[data-id="op-000028"]')
    visible_click(driver,"#finder-clear")


@bind("my resized catalog panel survives a reload")
def resize_catalog(context):
    driver=context.driver
    handle=driver.find_element(By.ID,"resize-sidebar")
    before=int(handle.get_attribute("aria-valuenow"))
    handle.send_keys(Keys.ARROW_RIGHT);driver.refresh();settle(driver)
    assert int(driver.find_element(By.ID,"resize-sidebar").get_attribute("aria-valuenow"))>before
    visible_click(driver,"#reset-panels")


@bind("I compare BERT and Arcee using differences and pinned configs")
def compare_configs(context):
    driver=context.driver
    driver.get(f"{context.viewer_url}#/compare/bert/arcee/view/operation")
    WebDriverWait(driver,15).until(lambda d:d.find_elements(By.CSS_SELECTOR,".compare-table"))
    visible_click(driver,"#compare-differences-only")
    visible_click(driver,".comparison-details > summary")
    Select(driver.find_element(By.CSS_SELECTOR,".comparison-details select")).select_by_value("official")
    WebDriverWait(driver,15).until(lambda d:d.find_elements(By.XPATH,"//tr[td[1]='model_type']"))


@bind("scope differences and actual configuration values remain visible")
def compare_values(context):
    driver=context.driver
    assert "Not comparable" in driver.find_element(By.XPATH,"//tr[td[1]='Trace initialized parameters']").text
    row=driver.find_element(By.XPATH,"//tr[td[1]='model_type']").text
    assert "bert" in row and "arcee" in row
    assert all(not r.is_displayed() for r in driver.find_elements(By.CSS_SELECTOR,'tr[data-equal="true"]'))
