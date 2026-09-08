import pytest
from selenium.webdriver.common.by import By

from test.e2e.audit_helpers import open_model, screenshot, settle, visible_click
from test.e2e.browser import set_exact_viewport

MODELS=["bit","bert","bertjapanese","apertus","arcee","afmoe","aimv2","clip","moshi","autoencoderkl","autoencoderklkvae","gemma2"]


@pytest.mark.parametrize("model", MODELS)
def test_audit_io_stays_inside_panel_and_reaches_last_step(driver,viewer_url,model):
    for width,height in [(1440,1000),(1024,768),(390,844)]:
        set_exact_viewport(driver,width,height)
        open_model(driver,viewer_url,model,"operation")
        node=driver.find_element(By.CSS_SELECTOR,".graph-node")
        node.click(); settle(driver)
        visible_click(driver,'.inspector-tab[data-panel="shapes"]')
        assert driver.execute_script("return document.documentElement.scrollWidth") == width
        journey=driver.find_element(By.CSS_SELECTOR,"#shapes-panel .journey")
        journey.find_element(By.XPATH,"./button").click()
        steps=journey.find_elements(By.CSS_SELECTOR,".journey-step")
        assert len(steps)>=2
        for step in [steps[0],steps[-1]]:
            driver.execute_script("arguments[0].scrollIntoView({block:'nearest',inline:'center'})",step)
            step.send_keys("")
            assert driver.execute_script("const r=arguments[0].getBoundingClientRect();return r.left>=0&&r.right<=innerWidth",step)
        assert driver.execute_script("return document.documentElement.scrollWidth") == width
        screenshot(driver,f"io-{model}-{width}")


@pytest.mark.parametrize("model,operation,before,after",[("bert","op-000028","3072","3072"),("bit","op-000005","10, 10","4, 4")])
def test_selected_journey_names_the_actual_transform(driver,viewer_url,model,operation,before,after):
    set_exact_viewport(driver,1440,1000)
    open_model(driver,viewer_url,model,"operation",f"/operation/{operation}")
    visible_click(driver,'.inspector-tab[data-panel="shapes"]')
    step=driver.find_element(By.CSS_SELECTOR,f'#shapes-panel .journey-step[data-node-id="{operation}"]')
    assert before in step.text and after in step.text
    assert "Input producers:" in step.text and "Output consumers:" in step.text
