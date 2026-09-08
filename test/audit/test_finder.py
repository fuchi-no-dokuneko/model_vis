from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from test.e2e.audit_helpers import open_model,settle,visible_click
from test.e2e.browser import set_exact_viewport


def test_finder_zero_results_filters_navigation_and_context_restore(driver,viewer_url):
    set_exact_viewport(driver,1440,1000)
    open_model(driver,viewer_url,"bert","architecture")
    original=driver.current_url
    search=driver.find_element(By.ID,"graph-search")
    search.send_keys("zzzz-no-such-operation")
    assert "0 matches" in driver.find_element(By.ID,"finder-status").text
    assert driver.find_element(By.ID,"finder-next").get_attribute("disabled")
    search.clear();search.send_keys("gelu")
    assert "12 matches" in driver.find_element(By.ID,"finder-status").text
    visible_click(driver,"#finder-panel > summary")
    field=driver.find_element(By.CSS_SELECTOR,'[data-finder="module"]')
    field.send_keys("encoder.layer.0.")
    driver.find_element(By.CSS_SELECTOR,'[data-finder="shape"]').send_keys("[3,5,3072]")
    assert "1 matches" in driver.find_element(By.ID,"finder-status").text
    visible_click(driver,".finder-table button")
    WebDriverWait(driver,10).until(lambda d:d.find_elements(By.CSS_SELECTOR,'.graph-node.selected[data-id="op-000028"]'))
    assert "gelu" in driver.find_element(By.ID,"inspector-title").text
    visible_click(driver,"#finder-clear")
    assert driver.current_url==original
    assert driver.find_element(By.ID,"graph-search").get_attribute("value")==""


def test_finder_table_pages_reach_the_final_operations(driver,viewer_url):
    set_exact_viewport(driver,1440,1000)
    open_model(driver,viewer_url,"bit","operation")
    visible_click(driver,"#finder-panel > summary")
    while driver.find_element(By.ID,"finder-page-next").is_enabled():
        visible_click(driver,"#finder-page-next")
    assert driver.find_element(By.ID,"finder-page").text=="5 / 5"
    assert driver.find_elements(By.CSS_SELECTOR,".finder-table tbody tr")
