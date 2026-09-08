from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from test.e2e.audit_helpers import open_model,settle,visible_click
from test.e2e.browser import set_exact_viewport


def test_explicit_detail_and_labels_preserve_fallback_identity(driver,viewer_url):
    set_exact_viewport(driver,1440,1000)
    for detail in ["beginner","standard","trace"]:
        for label in ["semantic","both","source"]:
            driver.get("about:blank")
            driver.get(f"{viewer_url}#/version/bit/view/operation/operation/op-000039/detail/{detail}/labels/{label}")
            WebDriverWait(driver,15).until(lambda d:d.find_elements(By.CSS_SELECTOR,'.graph-node.selected[data-id="op-000039"]'))
            assert driver.find_element(By.ID,"detail-mode").get_attribute("value")==detail
            assert driver.find_element(By.ID,"label-mode").get_attribute("value")==label
            assert "group_norm" in driver.find_element(By.ID,"inspector-title").text


def test_professional_preset_and_copied_investigation_link(driver,viewer_url):
    set_exact_viewport(driver,1440,1000)
    open_model(driver,viewer_url,"bert","operation","/operation/op-000028")
    visible_click(driver,"#professional-preset")
    driver.refresh();settle(driver)
    assert driver.find_element(By.ID,"detail-mode").get_attribute("value")=="standard"
    assert driver.find_element(By.ID,"label-mode").get_attribute("value")=="both"
    driver.execute_cdp_cmd("Browser.grantPermissions",dict(origin=viewer_url.rstrip("/"),permissions=["clipboardReadWrite","clipboardSanitizedWrite"]))
    visible_click(driver,"#review-button");visible_click(driver,"#copy-review-link")
    link=driver.execute_async_script("navigator.clipboard.readText().then(arguments[0])")
    assert "/operation/op-000028" in link and "/detail/standard/labels/both" in link
    driver.get("about:blank");driver.get(link)
    WebDriverWait(driver,15).until(lambda d:d.find_elements(By.CSS_SELECTOR,'.graph-node.selected[data-id="op-000028"]'))
    assert "gelu" in driver.find_element(By.ID,"inspector-title").text
