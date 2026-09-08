from pathlib import Path
import json
from urllib.parse import quote

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

ARTIFACTS = Path(__file__).parents[2] / "artifacts" / "audit-v2"


def long_location(model):
    root=Path(__file__).parents[2]/"model_code"
    version=json.loads((root/f"versions/{model}.json").read_text())
    graph=json.loads((root/version["graph_ref"]).read_text())
    node=max((n for n in graph["nodes"] if n["kind"]=="aten_op" and n.get("source_ref")),key=lambda n:len(n.get("module_path","")))
    source=node["source_ref"]
    parts=["version",model,"view","operation","module",node["module_path"],"operation",node["id"],"source",source["source_uid"],"line",str(source["start_line"]),"detail","standard","labels","both"]
    return "modelvis:/"+"/".join(quote(p,safe="") for p in parts)


def settle(driver):
    driver.execute_async_script("const done=arguments[0]; requestAnimationFrame(()=>requestAnimationFrame(()=>setTimeout(done,180)));")


def open_model(driver, url, model="bit", view="architecture", suffix=""):
    driver.get("about:blank")
    driver.get(f"{url}#/version/{model}/view/{view}/detail/standard/labels/both{suffix}")
    WebDriverWait(driver, 20).until(lambda d: d.find_elements(By.CSS_SELECTOR, ".graph-node"))
    settle(driver)


def visible_click(driver, selector):
    element = driver.find_element(By.CSS_SELECTOR, selector)
    if not element.is_displayed() and "workspace-tools" in driver.execute_script("return arguments[0].closest('#workspace-tools')?.id || ''", element):
        driver.find_element(By.ID, "tools-button").click()
    driver.execute_script("arguments[0].scrollIntoView({block:'nearest',inline:'center'})", element)
    assert driver.execute_script("const e=arguments[0],r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))", element)
    element.click()
    settle(driver)


def escape(driver):
    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
    settle(driver)


def rect(driver, selector):
    return driver.execute_script("const r=document.querySelector(arguments[0]).getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height}", selector)


def screenshot(driver, name):
    directory = ARTIFACTS / "screenshots"
    directory.mkdir(parents=True, exist_ok=True)
    driver.save_screenshot(str(directory / f"{name}.png"))
