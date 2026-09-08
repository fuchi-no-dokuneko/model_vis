from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from test.e2e.audit_helpers import open_model,rect,settle,visible_click
from test.e2e.browser import set_exact_viewport


def test_resizable_panels_persist_and_fit_narrow_windows(driver,viewer_url):
    set_exact_viewport(driver,1440,1000);open_model(driver,viewer_url)
    before=rect(driver,"#sidebar")["width"]
    driver.find_element(By.ID,"resize-sidebar").send_keys(Keys.ARROW_RIGHT,Keys.ARROW_RIGHT)
    assert rect(driver,"#sidebar")["width"]==before+32
    driver.refresh();settle(driver)
    assert rect(driver,"#sidebar")["width"]==before+32
    set_exact_viewport(driver,1061,900);settle(driver)
    assert rect(driver,"#inspector")["right"]<=1061
    assert rect(driver,"#graph-viewport")["width"]>=300
    set_exact_viewport(driver,1440,1000);settle(driver)
    visible_click(driver,"#reset-panels")
    assert rect(driver,"#sidebar")["width"]==260
