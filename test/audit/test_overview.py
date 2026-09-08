import pytest
from selenium.webdriver.common.by import By

from test.e2e.audit_helpers import open_model,screenshot,visible_click
from test.e2e.browser import set_exact_viewport


@pytest.mark.parametrize("model,view",[("clip","architecture"),("autoencoderklkvae","operation")])
def test_fitted_overview_has_readable_unobstructed_nonintersecting_groups(driver,viewer_url,model,view):
    set_exact_viewport(driver,1440,1000)
    open_model(driver,viewer_url,model,view)
    visible_click(driver,"#fit-button")
    evidence=driver.execute_script("""
      const nodes=[...document.querySelectorAll('.overview-group')];
      const bounds=nodes.map(node=>node.getBoundingClientRect());
      const intersections=[];
      bounds.forEach((a,i)=>bounds.slice(i+1).forEach((b,j)=>{
        if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>0.25 && Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>0.25) intersections.push([i,i+j+1]);
      }));
      return {count:nodes.length,intersections,hit:nodes.map((node,i)=>node.contains(document.elementFromPoint(bounds[i].x+bounds[i].width/2,bounds[i].y+bounds[i].height/2)))};
    """)
    assert evidence["count"]>0 and not evidence["intersections"]
    assert all(evidence["hit"])
    screenshot(driver,f"overview-{model}")
    driver.find_element(By.CSS_SELECTOR,".overview-group").click()
    assert driver.find_element(By.ID,"graph-viewport").get_attribute("data-zoom-tier")=="normal"
