from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from scripts.serve_https import https_server
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from test.e2e.browser import create_chrome_driver, set_exact_viewport
from test.e2e.browser_coverage import BrowserCoverage
from .gherkin import BINDINGS, Scenario, assert_all_steps_bound, parse_feature
from . import steps as _steps  # noqa: F401


ROOT = Path(__file__).parents[1]
FEATURES = {
    "daily": ROOT / "uat" / "features" / "daily.feature",
    "demo-en": ROOT / "uat" / "features" / "demo-en.feature",
    "demo-yue": ROOT / "uat" / "features" / "demo-yue.feature",
}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@dataclass
class Context:
    driver: Any
    viewer_url: str
    suite: str
    demo_recording: bool = False


@dataclass(frozen=True)
class ScenarioCase:
    feature: Path
    scenario: Scenario


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def git_value(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
        timeout=5,
    )
    return result.stdout.strip()


def write_sonar_report(path: Path, scenarios: list[dict[str, Any]]) -> None:
    root = ElementTree.Element("testExecutions", version="1")
    def feature_path(scenario: dict[str, Any]) -> str:
        return scenario.get("feature", "uat/features/daily.feature")

    for feature in dict.fromkeys(feature_path(scenario) for scenario in scenarios):
        file_element = ElementTree.SubElement(root, "file", path=feature)
        for scenario in (item for item in scenarios if feature_path(item) == feature):
            case = ElementTree.SubElement(
                file_element,
                "testCase",
                name=scenario["name"],
                duration=str(scenario["duration_ms"]),
            )
            if not scenario["passed"]:
                failure = ElementTree.SubElement(case, "failure", message=scenario["diagnostic"])
                failure.text = scenario["diagnostic"]
    ElementTree.indent(root)
    ElementTree.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def dry_run(output: Path, cases: list[ScenarioCase], suite: str) -> int:
    assert_all_steps_bound([case.scenario for case in cases])
    records = [
        {
            "feature": case.feature.relative_to(ROOT).as_posix(),
            "name": case.scenario.name,
            "passed": True,
            "steps": [step.text for step in case.scenario.steps],
        }
        for case in cases
    ]
    output.mkdir(parents=True, exist_ok=True)
    document = {
        "repository": git_value("config", "--get", "remote.origin.url"),
        "commit": git_value("rev-parse", "HEAD"),
        "suite": suite,
        "started_at": iso_now(),
        "ended_at": iso_now(),
        "dry_run": True,
        "overall": True,
        "scenarios": records,
    }
    (output / "checklist.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    write_sonar_report(output / "sonar-test-execution.xml", [
        {**record, "duration_ms": 0, "diagnostic": ""} for record in records
    ])
    print(json.dumps(document, indent=2))
    return 0


def execute(output: Path, cases: list[ScenarioCase], suite: str) -> int:
    assert_all_steps_bound([case.scenario for case in cases])
    subprocess.run(
        ["npm", "run", "build-ui", "--", "--model-code", "model_code", "--out", "build"],
        cwd=ROOT,
        check=True,
        timeout=60,
    )
    if output.exists():
        shutil.rmtree(output)
    screenshots = output / "screenshots"
    screenshots.mkdir(parents=True)
    server = https_server(ROOT / "build", handler=QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    profile = ROOT / "build_cache" / "uat-chromium-profile"
    if profile.exists():
        shutil.rmtree(profile)
    profile.mkdir(parents=True)
    browser = create_chrome_driver(profile)
    set_exact_viewport(browser, 1440, 900)
    coverage = BrowserCoverage(browser, ROOT)
    coverage.start()
    started = iso_now()
    records = []
    try:
        viewer_url = f"https://127.0.0.1:{server.server_port}/"
        for index, case in enumerate(cases, start=1):
            scenario = case.scenario
            case_suite = case.feature.stem
            context = Context(browser, viewer_url, case_suite)
            set_exact_viewport(browser, 1440, 900)
            browser.get(viewer_url)
            WebDriverWait(browser, 15).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".model-item"))
            WebDriverWait(browser, 15).until(lambda current: current.find_elements(By.CSS_SELECTOR, ".graph-node"))
            WebDriverWait(browser, 15).until(
                lambda current: current.execute_script("return location.hash.startsWith('#/version/')")
                and current.find_element(By.ID, "uri-input").get_attribute("value").startswith("modelvis:/version/")
            )
            scenario_started = time.perf_counter()
            diagnostic = ""
            passed = True
            try:
                for step in scenario.steps:
                    BINDINGS[step.text](context)
            except Exception as error:
                passed = False
                diagnostic = f"{step.text}: {type(error).__name__}: {error}"
            finally:
                if context.demo_recording:
                    try:
                        _steps.finish_recording(context)
                    except Exception as error:
                        passed = False
                        diagnostic = f"{diagnostic}; recording cleanup: {type(error).__name__}: {error}".strip("; ")
            filename = f"{index:02d}-" + re.sub(r"[^a-z0-9]+", "-", scenario.name.lower()).strip("-") + ".png"
            browser.save_screenshot(str(screenshots / filename))
            records.append({
                "feature": case.feature.relative_to(ROOT).as_posix(),
                "name": scenario.name,
                "passed": passed,
                "duration_ms": round((time.perf_counter() - scenario_started) * 1000),
                "diagnostic": diagnostic,
                "screenshot": f"screenshots/{filename}",
            })
            coverage.capture()
    finally:
        coverage.write_lcov(output / "browser.lcov")
        browser.quit()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        shutil.rmtree(profile, ignore_errors=True)

    document = {
        "repository": git_value("config", "--get", "remote.origin.url"),
        "commit": git_value("rev-parse", "HEAD"),
        "suite": suite,
        "started_at": started,
        "ended_at": iso_now(),
        "dry_run": False,
        "overall": all(item["passed"] for item in records),
        "scenarios": records,
    }
    (output / "checklist.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    write_sonar_report(output / "sonar-test-execution.xml", records)
    print(json.dumps(document, indent=2))
    return 0 if document["overall"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Model Vis Gherkin acceptance and recording suites")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--suite", choices=(*FEATURES, "all"), default="daily")
    parser.add_argument("--scenario", help="run scenarios whose names contain this text")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    selected = FEATURES.values() if args.suite == "all" else (FEATURES[args.suite],)
    cases = [ScenarioCase(feature, scenario) for feature in selected for scenario in parse_feature(feature)]
    if args.scenario:
        cases = [case for case in cases if args.scenario.lower() in case.scenario.name.lower()]
        if not cases:
            parser.error(f"no scenario contains: {args.scenario}")
    output = args.output or ROOT / "artifacts" / ("uat" if args.suite == "daily" else args.suite)
    return dry_run(output, cases, args.suite) if args.dry_run else execute(output, cases, args.suite)


if __name__ == "__main__":
    sys.exit(main())
