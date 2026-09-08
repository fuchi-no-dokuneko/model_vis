import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

from test.e2e.audit_helpers import open_model,settle,visible_click,screenshot
from test.e2e.browser import set_exact_viewport


@pytest.mark.parametrize("drawer",["sidebar","inspector"])
def test_drawer_resize_reconciles_backdrop_and_focus(driver,viewer_url,drawer):
    set_exact_viewport(driver,390,844); open_model(driver,viewer_url)
    if drawer=="sidebar": visible_click(driver,"#menu-button")
    else:
        driver.find_element(By.CSS_SELECTOR,".graph-node").click(); settle(driver)
    assert driver.find_element(By.ID,drawer).get_attribute("class").find("open")>=0
    for width in [721,1060,1061,1440]:
        set_exact_viewport(driver,width,900); settle(driver)
        if width>1060 or (drawer=="sidebar" and width>720):
            assert not driver.find_element(By.ID,"scrim").is_displayed()
    visible_click(driver,'.inspector-tab[data-panel="config"]')
    assert driver.find_element(By.ID,"config-panel").is_displayed()
    for width in [1060,720,390]:
        set_exact_viewport(driver,width,844); settle(driver)
        assert not driver.find_element(By.ID,"scrim").is_displayed()
    screenshot(driver,f"drawer-{drawer}-restored")


def test_mobile_tools_preserve_compare_detail_labels_and_paths(driver,viewer_url):
    set_exact_viewport(driver,390,844); open_model(driver,viewer_url)
    visible_click(driver,"#tools-button")
    for name in ["detail-mode","label-mode","compare-button"]:
        assert driver.find_element(By.ID,name).is_displayed()
    Select(driver.find_element(By.ID,"detail-mode")).select_by_value("trace")
    Select(driver.find_element(By.ID,"label-mode")).select_by_value("source")
    assert all(button.is_displayed() for button in driver.find_elements(By.CSS_SELECTOR,".mobile-path-control"))
    assert "/detail/trace/labels/source" in driver.current_url
