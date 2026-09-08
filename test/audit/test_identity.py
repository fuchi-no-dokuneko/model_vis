import pytest
from selenium.webdriver.common.by import By

from test.e2e.audit_helpers import open_model,visible_click
from test.e2e.browser import set_exact_viewport


@pytest.mark.parametrize("model,total,head",[("bert","109,482,240","109,514,298"),("arcee","4,291,496,960","4,619,189,760"),("bertjapanese","Unavailable",None)])
def test_identity_distinguishes_checkpoint_trace_and_head_counts(driver,viewer_url,model,total,head):
    set_exact_viewport(driver,1440,1000)
    open_model(driver,viewer_url,model)
    visible_click(driver,"#identity-summary")
    text=driver.find_element(By.ID,"identity-facts").text
    assert total in text
    if head: assert head in text
    assert "pretrained weights were not downloaded" in text
    if model=="bertjapanese":
        assert "trace reused from bert" in text and "selected checkpoint not verified" in text
        assert "Unverified; no pinned mapping" in text
    else:
        assert "Config-derived" in text and "Head scope" in text
    visible_click(driver,'.inspector-tab[data-panel="config"]')
    assert driver.find_element(By.ID,"official-config-link").is_displayed()==(model!="bertjapanese")
