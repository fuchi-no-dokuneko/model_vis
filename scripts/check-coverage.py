from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.etree import ElementTree


def percentage(hit: int, found: int) -> float:
    return 100.0 if found == 0 else hit * 100.0 / found


def require_report(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"required coverage report is missing or empty: {path}")


def read_cobertura(path: Path) -> dict[str, float]:
    require_report(path)
    root = ElementTree.parse(path).getroot()
    return {
        "line": float(root.attrib["line-rate"]) * 100,
        "branch": float(root.attrib["branch-rate"]) * 100,
    }


def read_lcov(path: Path) -> dict[str, float]:
    require_report(path)
    lines: dict[tuple[str, int], int] = {}
    branches: dict[tuple[str, int, str, str], int] = {}
    source = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("SF:"):
            source = raw[3:]
        elif raw.startswith("DA:"):
            line, count, *_ = raw[3:].split(",")
            key = (source, int(line))
            lines[key] = max(lines.get(key, 0), int(count))
        elif raw.startswith("BRDA:"):
            line, block, branch, count = raw[5:].split(",")
            key = (source, int(line), block, branch)
            value = 0 if count == "-" else int(count)
            branches[key] = max(branches.get(key, 0), value)
    if not lines or not branches:
        raise ValueError(f"coverage report has no line or branch records: {path}")
    return {
        "line": percentage(sum(value > 0 for value in lines.values()), len(lines)),
        "branch": percentage(sum(value > 0 for value in branches.values()), len(branches)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce required line and branch coverage reports")
    parser.add_argument("--minimum", type=float, default=95.0)
    parser.add_argument("--python-report", type=Path, required=True)
    parser.add_argument("--lcov-report", type=Path, action="append", default=[])
    args = parser.parse_args()

    reports = {str(args.python_report): read_cobertura(args.python_report)}
    reports.update({str(path): read_lcov(path) for path in args.lcov_report})
    failures = [
        f"{path} {kind} coverage {value:.2f}% is below {args.minimum:.2f}%"
        for path, metrics in reports.items()
        for kind, value in metrics.items()
        if value < args.minimum
    ]
    print(json.dumps({"minimum": args.minimum, "reports": reports, "passed": not failures}, indent=2))
    if failures:
        raise SystemExit("\n".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
