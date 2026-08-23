from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s]+)$")


def production_packages() -> list[tuple[str, str]]:
    result = []
    for line in (ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        match = PIN.fullmatch(line)
        if not match:
            raise ValueError(f"unlocked requirement: {line}")
        result.append((match.group(1), match.group(2).split("+", 1)[0]))
    return result


def active_exceptions() -> set[str]:
    document = json.loads((ROOT / "security/advisory-exceptions.json").read_text(encoding="utf-8"))
    today = dt.date.today()
    result = set()
    for item in document["exceptions"]:
        required = {"id", "package", "rationale", "owner", "expires", "compensating_control"}
        if not required.issubset(item) or not all(str(item[name]).strip() for name in required):
            raise ValueError("advisory exception is incomplete")
        if dt.date.fromisoformat(item["expires"]) < today:
            raise ValueError(f"advisory exception expired: {item['id']}")
        result.add(item["id"])
    return result


def query_osv(packages: list[tuple[str, str]]) -> list[dict[str, Any]]:
    payload = {
        "queries": [
            {"package": {"ecosystem": "PyPI", "name": name}, "version": version}
            for name, version in packages
        ]
    }
    completed = subprocess.run(
        [
            "curl",
            "-4",
            "--fail-with-body",
            "--silent",
            "--show-error",
            "--header",
            "Content-Type: application/json",
            "--data-binary",
            "@-",
            "https://api.osv.dev/v1/querybatch",
        ],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "OSV query failed")
    return json.loads(completed.stdout)["results"]


def query_vulnerability(vulnerability_id: str) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "curl",
            "-4",
            "--fail-with-body",
            "--silent",
            "--show-error",
            f"https://api.osv.dev/v1/vulns/{vulnerability_id}",
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or f"OSV advisory query failed: {vulnerability_id}")
    return json.loads(completed.stdout)


def severity(vulnerability: dict[str, Any]) -> str:
    value = vulnerability.get("database_specific", {}).get("severity")
    return str(value or "UNCLASSIFIED").upper()


def main() -> int:
    packages = production_packages()
    exceptions = active_exceptions()
    summaries = query_osv(packages)
    package_advisories = {
        (package[0], vulnerability["id"])
        for package, result in zip(packages, summaries, strict=True)
        for vulnerability in result.get("vulns", [])
    }
    details = {
        vulnerability_id: query_vulnerability(vulnerability_id)
        for vulnerability_id in sorted({item[1] for item in package_advisories})
    }
    blocking = []
    findings = []
    for package, vulnerability_id in sorted(package_advisories):
        vulnerability = details[vulnerability_id]
        level = severity(vulnerability)
        identifiers = {vulnerability_id, *vulnerability.get("aliases", [])}
        excepted = bool(identifiers & exceptions)
        finding = {"package": package, "id": vulnerability_id, "severity": level, "excepted": excepted}
        findings.append(finding)
        if not excepted and level in {"HIGH", "CRITICAL"}:
            blocking.append(finding)
    print(json.dumps({
        "passed": not blocking,
        "packages": len(packages),
        "advisories": len(findings),
        "unclassified": sum(item["severity"] == "UNCLASSIFIED" for item in findings),
        "blocking": blocking,
    }, indent=2))
    return 0 if not blocking else 1


if __name__ == "__main__":
    sys.exit(main())
