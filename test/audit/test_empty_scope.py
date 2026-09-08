from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from test.e2e.audit_helpers import visible_click
from test.e2e.browser import set_exact_viewport


def test_inactive_dropout_scope_explains_empty_graph_and_returns_to_model(driver,viewer_url):
    set_exact_viewport(driver,1440,1000)
    driver.get("about:blank")
    driver.get(f"{viewer_url}#/version/bert/view/operation/module/encoder.layer.0.attention.self.dropout/detail/trace/labels/source")
    WebDriverWait(driver,15).until(lambda d:d.find_elements(By.CSS_SELECTOR,"#empty-state button"))
    assert "No operations were observed" in driver.find_element(By.ID,"empty-state").text
    assert "dropout" in driver.find_element(By.ID,"inspector-title").text.lower()
    visible_click(driver,"#empty-state button")
    WebDriverWait(driver,15).until(lambda d:d.find_elements(By.CSS_SELECTOR,".graph-node"))
    assert "/version/bert/" in driver.current_url
    assert not driver.find_element(By.ID,"empty-state").is_displayed()
