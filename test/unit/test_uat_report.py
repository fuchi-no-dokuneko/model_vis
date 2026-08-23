from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from uat.run import write_sonar_report


ROOT = Path(__file__).parents[2]


def run_check(directory: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/check-uat-report.py", "--directory", str(directory)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def valid_report(directory: Path) -> None:
    screenshots = directory / "screenshots"
    screenshots.mkdir(parents=True)
    (screenshots / "catalog.png").write_bytes(b"png")
    (directory / "browser.lcov").write_text(
        "TN:\nSF:src/ui/app.js\nDA:1,1\nBRDA:1,0,0,1\nend_of_record\n",
        encoding="utf-8",
    )
    scenario = {
        "name": "Browse catalog",
        "passed": True,
        "duration_ms": 12,
        "diagnostic": "",
        "screenshot": "screenshots/catalog.png",
    }
    (directory / "checklist.json").write_text(json.dumps({
        "repository": "https://github.com/example/model-vis.git",
        "commit": "abc123",
        "started_at": "2026-08-23T00:00:00+00:00",
        "ended_at": "2026-08-23T00:00:01+00:00",
        "dry_run": False,
        "overall": True,
        "scenarios": [scenario],
    }), encoding="utf-8")
    write_sonar_report(directory / "sonar-test-execution.xml", [scenario])


def test_uat_report_check_accepts_complete_real_report(tmp_path: Path) -> None:
    valid_report(tmp_path)
    result = run_check(tmp_path)
    assert result.returncode == 0, result.stderr
    assert '"scenarios": 1' in result.stdout


def test_uat_report_check_rejects_dry_or_incomplete_reports(tmp_path: Path) -> None:
    valid_report(tmp_path)
    checklist = json.loads((tmp_path / "checklist.json").read_text(encoding="utf-8"))
    checklist["dry_run"] = True
    (tmp_path / "checklist.json").write_text(json.dumps(checklist), encoding="utf-8")
    assert run_check(tmp_path).returncode != 0

    (tmp_path / "browser.lcov").unlink()
    assert run_check(tmp_path).returncode != 0
