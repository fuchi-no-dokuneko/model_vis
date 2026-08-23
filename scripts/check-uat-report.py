from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from xml.etree import ElementTree


def required_file(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"required UAT report is missing or empty: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate real UAT and Sonar reports")
    parser.add_argument("--directory", type=Path, default=Path("artifacts/uat"))
    args = parser.parse_args()
    checklist_path = args.directory / "checklist.json"
    sonar_path = args.directory / "sonar-test-execution.xml"
    lcov_path = args.directory / "browser.lcov"
    for path in (checklist_path, sonar_path, lcov_path):
        required_file(path)

    checklist = json.loads(checklist_path.read_text(encoding="utf-8"))
    for field in ("repository", "commit", "started_at", "ended_at"):
        if not isinstance(checklist.get(field), str) or not checklist[field]:
            raise ValueError(f"UAT checklist field must be a nonempty string: {field}")
    dt.datetime.fromisoformat(checklist["started_at"])
    dt.datetime.fromisoformat(checklist["ended_at"])
    if checklist.get("dry_run") is not False:
        raise ValueError("UAT checklist is not a real execution")
    if checklist.get("overall") is not True:
        raise ValueError("UAT checklist did not pass")
    scenarios = checklist.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("UAT checklist has no scenarios")
    for scenario in scenarios:
        required = {
            "name": str,
            "passed": bool,
            "duration_ms": int,
            "diagnostic": str,
            "screenshot": str,
        }
        for field, expected in required.items():
            if not isinstance(scenario.get(field), expected):
                raise ValueError(f"invalid scenario field {field}: {scenario.get('name', '<unknown>')}")
        if scenario["passed"] is not True:
            raise ValueError(f"UAT scenario failed: {scenario['name']}")
        required_file(args.directory / scenario["screenshot"])

    root = ElementTree.parse(sonar_path).getroot()
    if root.tag != "testExecutions" or root.attrib.get("version") != "1":
        raise ValueError("invalid Sonar generic test execution root")
    cases = root.findall("./file/testCase")
    if len(cases) != len(scenarios) or any(case.find("failure") is not None for case in cases):
        raise ValueError("Sonar report does not match passing UAT scenarios")
    print(json.dumps({"passed": True, "scenarios": len(scenarios), "directory": str(args.directory)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
