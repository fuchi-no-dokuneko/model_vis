import json

import pytest
from selenium.webdriver.common.by import By

from test.e2e.audit_helpers import ARTIFACTS, long_location, open_model, rect, screenshot, settle, visible_click
from test.e2e.browser import set_exact_viewport

SIZES = [(2560,1440),(1920,1080),(1440,1000),(1366,768),(1280,800),
         (1024,768),(981,900),(980,900),(768,1024),(721,900),(720,900),(390,844),(360,800)]


@pytest.mark.parametrize("model", ["bit", "bert", "clip", "autoencoderklkvae"])
def test_audit_52_viewports_have_reachable_navigation(driver, viewer_url, model):
    set_exact_viewport(driver,1440,1000)
    open_model(driver, viewer_url, model)
    # The badge and a long location must participate in normal toolbar layout.
    for index in range(2):
        driver.find_elements(By.CSS_SELECTOR, ".compare-check input")[index].click()
    outcomes=[]
    location=long_location(model)
    assert len(location)>200
    for width,height in SIZES:
        set_exact_viewport(driver,width,height); settle(driver)
        for mode in ["architecture","family","module","blocks","operation"]:
            driver.execute_script("document.querySelector('#uri-input').value=arguments[0]",location)
            visible_click(driver, f'.mode[data-mode="{mode}"]')
            assert f"/view/{mode}" in driver.current_url
        panel=rect(driver,"#inspector")
        if width>1060:
            assert panel["right"]<=width+0.5 and panel["left"]>=0
        else:
            assert "open" not in driver.find_element(By.ID,"inspector").get_attribute("class")
        assert driver.execute_script("return document.documentElement.scrollWidth") == width
        assert rect(driver,"#graph-viewport")["height"]>100
        screenshot(driver,f"viewport-{model}-{width}x{height}")
        outcomes.append(dict(model=model,width=width,height=height,navigation=True,inspector=panel,document_width=width,long_location_length=len(location)))
    (ARTIFACTS/f"viewports-{model}.json").write_text(json.dumps(outcomes,indent=2))


@pytest.mark.parametrize("width", [719,720,721,979,980,981,1024,1059,1060,1061,1199,1200,1201,1799,1800,1801])
def test_new_breakpoint_neighbors_keep_controls_separate(driver,viewer_url,width):
    set_exact_viewport(driver,width,900)
    open_model(driver,viewer_url)
    for mode in ["architecture","family","module","blocks","operation"]:
        visible_click(driver,f'.mode[data-mode="{mode}"]')
    assert driver.execute_script("return document.documentElement.scrollWidth") == width
    if width>1060: assert rect(driver,"#inspector")["right"]<=width+0.5
