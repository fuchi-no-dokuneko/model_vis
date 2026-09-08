import json
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait

from test.audit.network_server import fault_server
from test.e2e.audit_helpers import open_model,visible_click
from test.e2e.browser import set_exact_viewport


def test_difference_filter_scopes_and_configuration_drilldown(driver,viewer_url):
    set_exact_viewport(driver,1440,1000)
    driver.get(f"{viewer_url}#/compare/bert/arcee/view/operation")
    wait=WebDriverWait(driver,15)
    wait.until(lambda d:d.find_elements(By.CSS_SELECTOR,".compare-table"))
    row=driver.find_element(By.XPATH,"//tr[td[1]='Trace initialized parameters']")
    assert "Not comparable" in row.text
    visible_click(driver,"#compare-differences-only")
    assert driver.find_element(By.XPATH,"//tr[td[1]='Config fields changed']").is_displayed()
    assert all(not r.is_displayed() for r in driver.find_elements(By.CSS_SELECTOR,'tr[data-equal="true"]'))
    details=driver.find_elements(By.CSS_SELECTOR,".comparison-details")
    assert all(not d.get_attribute("open") for d in details)
    visible_click(driver,".comparison-details > summary")
    Select(driver.find_element(By.CSS_SELECTOR,".comparison-details select")).select_by_value("official")
    wait.until(lambda d:d.find_elements(By.XPATH,"//tr[td[1]='model_type']"))
    assert "bert" in driver.find_element(By.XPATH,"//tr[td[1]='model_type']").text
    assert "arcee" in driver.find_element(By.XPATH,"//tr[td[1]='model_type']").text
    visible_click(driver,".comparison-details:nth-of-type(2) > summary")
    assert driver.find_element(By.CSS_SELECTOR,".comparison-details:nth-of-type(2) li").is_displayed()


def test_delayed_comparison_cannot_overwrite_new_pair_or_url(driver,viewer_url):
    set_exact_viewport(driver,1440,1000)
    version=json.loads((Path(__file__).parents[2]/"model_code/versions/bert.json").read_text())
    with fault_server() as (url,fault):
        fault.update(path=version["trace_ref"],delay=3)
        driver.get(f"{url}#/compare/bert/bertjapanese/view/module")
        WebDriverWait(driver,10).until(lambda d:fault["hits"])
        driver.get(f"{url}#/compare/afmoe/aimv2/view/operation")
        WebDriverWait(driver,15).until(lambda d:d.find_elements(By.XPATH,"//tr[td[1]='Version' and td[2]='afmoe']"))
        driver.execute_async_script("setTimeout(arguments[0],3500)")
        assert "/compare/afmoe/aimv2/view/operation" in driver.current_url
        assert driver.find_element(By.XPATH,"//tr[td[1]='Version']/td[2]").text=="afmoe"
