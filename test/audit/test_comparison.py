import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from test.e2e.audit_helpers import open_model,settle,visible_click
from test.e2e.browser import set_exact_viewport


def choose_pair(driver,pair):
    for model in pair:
        search=driver.find_element(By.ID,"search"); search.clear(); search.send_keys(model)
        checkbox=driver.find_element(By.CSS_SELECTOR,f'.favorite-button[data-version-id="{model}"] + label input')
        checkbox.click()


@pytest.mark.parametrize("pair",[("afmoe","aimv2"),("bert","bertjapanese"),("apertus","arcee")])
@pytest.mark.parametrize("view",["architecture","family","module","blocks","operation"])
def test_compare_click_back_reload_and_keyboard_round_trip(driver,viewer_url,pair,view):
    set_exact_viewport(driver,1440,1000)
    open_model(driver,viewer_url,pair[0],view)
    choose_pair(driver,pair); visible_click(driver,"#compare-button")
    wait=WebDriverWait(driver,15)
    wait.until(lambda d: d.find_elements(By.CSS_SELECTOR,".compare-table"))
    assert f"/view/{view}" in driver.current_url and "Window" not in driver.current_url
    close=driver.find_element(By.ID,"close-compare")
    close.send_keys(Keys.SHIFT,Keys.TAB)
    assert driver.switch_to.active_element.get_attribute("id")=="compare-differences-only"
    driver.switch_to.active_element.send_keys(Keys.TAB)
    assert driver.switch_to.active_element.get_attribute("id")=="close-compare"
    assert driver.execute_script("document.querySelector('#search').focus();return document.querySelector('#compare-pane').contains(document.activeElement)")
    if pair[0]=="afmoe":
        row=driver.find_element(By.XPATH,"//table/tbody/tr[td[1]='Config-derived parameters']")
        assert "Unavailable for both" in row.text
    if pair[1]=="bertjapanese": assert "trace reused from bert" in driver.find_element(By.ID,"compare-content").text
    driver.back(); settle(driver)
    assert not driver.find_element(By.ID,"compare-pane").is_displayed()
    driver.forward(); wait.until(lambda d: d.find_elements(By.CSS_SELECTOR,".compare-table"))
    driver.refresh(); wait.until(lambda d: d.find_elements(By.CSS_SELECTOR,".compare-table"))
    assert f"/view/{view}" in driver.find_element(By.ID,"uri-input").get_attribute("value")
    driver.find_element(By.ID,"close-compare").send_keys(Keys.ESCAPE)
    settle(driver)
    assert not driver.find_element(By.ID,"compare-pane").is_displayed()
    assert driver.switch_to.active_element.get_attribute("id")=="compare-button"
