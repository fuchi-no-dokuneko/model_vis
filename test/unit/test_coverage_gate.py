from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]


def run_gate(python_report: Path, lcov_report: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/check-coverage.py",
            "--python-report", str(python_report),
            "--lcov-report", str(lcov_report),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def write_python_report(path: Path, line_rate: str = "1", branch_rate: str = "1") -> None:
    path.write_text(
        f'<coverage line-rate="{line_rate}" branch-rate="{branch_rate}"/>\n',
        encoding="utf-8",
    )


def write_lcov(path: Path, covered: bool = True) -> None:
    count = 1 if covered else 0
    path.write_text(
        f"TN:\nSF:src/example.js\nDA:1,{count}\nBRDA:1,0,0,{count}\nend_of_record\n",
        encoding="utf-8",
    )


def test_coverage_gate_accepts_complete_reports(tmp_path: Path) -> None:
    python_report = tmp_path / "python.xml"
    lcov_report = tmp_path / "ui.lcov"
    write_python_report(python_report)
    write_lcov(lcov_report)

    result = run_gate(python_report, lcov_report)
    assert result.returncode == 0, result.stderr
    assert '"passed": true' in result.stdout


def test_coverage_gate_rejects_below_threshold_and_missing_reports(tmp_path: Path) -> None:
    python_report = tmp_path / "python.xml"
    lcov_report = tmp_path / "ui.lcov"
    write_python_report(python_report, line_rate="0.94")
    write_lcov(lcov_report, covered=False)
    result = run_gate(python_report, lcov_report)
    assert result.returncode != 0
    assert "below 95.00%" in result.stderr

    missing = run_gate(tmp_path / "missing.xml", lcov_report)
    assert missing.returncode != 0
    assert "missing or empty" in missing.stderr


def test_coverage_gate_rejects_malformed_reports(tmp_path: Path) -> None:
    python_report = tmp_path / "python.xml"
    lcov_report = tmp_path / "ui.lcov"
    python_report.write_text("not xml", encoding="utf-8")
    write_lcov(lcov_report)

    assert run_gate(python_report, lcov_report).returncode != 0
