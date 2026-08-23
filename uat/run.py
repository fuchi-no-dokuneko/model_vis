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
FEATURE = ROOT / "uat" / "features" / "daily.feature"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@dataclass
class Context:
    driver: Any
    viewer_url: str


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
    file_element = ElementTree.SubElement(root, "file", path="uat/features/daily.feature")
    for scenario in scenarios:
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


def dry_run(output: Path, scenarios: list[Scenario]) -> int:
    assert_all_steps_bound(scenarios)
    records = [{"name": scenario.name, "passed": True, "steps": [step.text for step in scenario.steps]} for scenario in scenarios]
    output.mkdir(parents=True, exist_ok=True)
    document = {
        "repository": git_value("config", "--get", "remote.origin.url"),
        "commit": git_value("rev-parse", "HEAD"),
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


def execute(output: Path, scenarios: list[Scenario]) -> int:
    assert_all_steps_bound(scenarios)
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
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=ROOT / "build"))
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
        context = Context(browser, f"http://127.0.0.1:{server.server_port}/")
        for scenario in scenarios:
            scenario_started = time.perf_counter()
            diagnostic = ""
            passed = True
            try:
                for step in scenario.steps:
                    BINDINGS[step.text](context)
            except Exception as error:
                passed = False
                diagnostic = f"{type(error).__name__}: {error}"
            filename = re.sub(r"[^a-z0-9]+", "-", scenario.name.lower()).strip("-") + ".png"
            browser.save_screenshot(str(screenshots / filename))
            records.append({
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
        thread.join(timeout=5)
        shutil.rmtree(profile, ignore_errors=True)

    document = {
        "repository": git_value("config", "--get", "remote.origin.url"),
        "commit": git_value("rev-parse", "HEAD"),
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
    parser = argparse.ArgumentParser(description="Run daily Gherkin model-vis acceptance")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "uat")
    args = parser.parse_args()
    scenarios = parse_feature(FEATURE)
    return dry_run(args.output, scenarios) if args.dry_run else execute(args.output, scenarios)


if __name__ == "__main__":
    sys.exit(main())
