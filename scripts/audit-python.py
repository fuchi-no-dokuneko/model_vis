from __future__ import annotations

import datetime as dt
import json
import math
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s]+)$")
SEVERITY_ORDER = {"NONE": 0, "LOW": 1, "MODERATE": 2, "HIGH": 3, "CRITICAL": 4}


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


def _named_severity(value: object) -> str | None:
    normalized = str(value or "").strip().upper()
    if normalized == "MEDIUM":
        normalized = "MODERATE"
    return normalized if normalized in SEVERITY_ORDER else None


def _cvss_v3_score(vector: str) -> float | None:
    if not vector.startswith(("CVSS:3.0/", "CVSS:3.1/")):
        return None
    metrics = dict(item.split(":", 1) for item in vector.split("/")[1:] if ":" in item)
    required = {"AV", "AC", "PR", "UI", "S", "C", "I", "A"}
    if not required.issubset(metrics):
        return None
    try:
        av = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}[metrics["AV"]]
        ac = {"L": 0.77, "H": 0.44}[metrics["AC"]]
        scope_changed = metrics["S"] == "C"
        pr = (
            {"N": 0.85, "L": 0.68, "H": 0.5}
            if scope_changed
            else {"N": 0.85, "L": 0.62, "H": 0.27}
        )[metrics["PR"]]
        ui = {"N": 0.85, "R": 0.62}[metrics["UI"]]
        impacts = [{"N": 0.0, "L": 0.22, "H": 0.56}[metrics[name]] for name in ("C", "I", "A")]
    except KeyError:
        return None
    impact_subscore = 1 - math.prod(1 - value for value in impacts)
    impact = (
        7.52 * (impact_subscore - 0.029) - 3.25 * (impact_subscore - 0.02) ** 15
        if scope_changed
        else 6.42 * impact_subscore
    )
    if impact <= 0:
        return 0.0
    exploitability = 8.22 * av * ac * pr * ui
    base = min(10.0, (1.08 if scope_changed else 1.0) * (impact + exploitability))
    return math.ceil((base - 1e-10) * 10) / 10


def _cvss_v2_score(vector: str) -> float | None:
    if not vector.startswith("CVSS:2.0/"):
        return None
    metrics = dict(item.split(":", 1) for item in vector.split("/")[1:] if ":" in item)
    required = {"AV", "AC", "Au", "C", "I", "A"}
    if not required.issubset(metrics):
        return None
    try:
        av = {"L": 0.395, "A": 0.646, "N": 1.0}[metrics["AV"]]
        ac = {"H": 0.35, "M": 0.61, "L": 0.71}[metrics["AC"]]
        authentication = {"M": 0.45, "S": 0.56, "N": 0.704}[metrics["Au"]]
        impacts = [{"N": 0.0, "P": 0.275, "C": 0.66}[metrics[name]] for name in ("C", "I", "A")]
    except KeyError:
        return None
    impact = 10.41 * (1 - math.prod(1 - value for value in impacts))
    exploitability = 20 * av * ac * authentication
    score = ((0.6 * impact) + (0.4 * exploitability) - 1.5) * (0 if impact == 0 else 1.176)
    return math.floor((max(0.0, score) * 10) + 0.5) / 10


def _score_severity(value: object) -> str | None:
    raw = str(value or "").strip()
    score = _cvss_v3_score(raw)
    if score is None:
        score = _cvss_v2_score(raw)
    if score is None:
        try:
            score = float(raw)
        except ValueError:
            return None
    if score <= 0:
        return "NONE"
    if score < 4:
        return "LOW"
    if score < 7:
        return "MODERATE"
    if score < 9:
        return "HIGH"
    return "CRITICAL"


def severity(vulnerability: dict[str, Any]) -> str:
    candidates = []
    for container in (
        vulnerability.get("database_specific", {}),
        *(
            value
            for affected in vulnerability.get("affected", [])
            for value in (
                affected.get("database_specific", {}),
                affected.get("ecosystem_specific", {}),
            )
        ),
    ):
        if level := _named_severity(container.get("severity")):
            candidates.append(level)
    for item in vulnerability.get("severity", []):
        if level := _score_severity(item.get("score")):
            candidates.append(level)
    return max(candidates, key=SEVERITY_ORDER.__getitem__) if candidates else "UNCLASSIFIED"


def merged_findings(
    package_advisories: set[tuple[str, str]],
    details: dict[str, dict[str, Any]],
    exceptions: set[str],
) -> list[dict[str, Any]]:
    by_package: dict[str, list[str]] = defaultdict(list)
    for package, vulnerability_id in sorted(package_advisories):
        by_package[package].append(vulnerability_id)

    findings = []
    for package, vulnerability_ids in sorted(by_package.items()):
        groups: list[dict[str, Any]] = []
        for vulnerability_id in vulnerability_ids:
            vulnerability = details[vulnerability_id]
            identifiers = {vulnerability_id, *vulnerability.get("aliases", [])}
            matches = [group for group in groups if group["identifiers"] & identifiers]
            if not matches:
                groups.append({"identifiers": identifiers, "records": [vulnerability]})
                continue
            target = matches[0]
            target["identifiers"].update(identifiers)
            target["records"].append(vulnerability)
            for duplicate in matches[1:]:
                target["identifiers"].update(duplicate["identifiers"])
                target["records"].extend(duplicate["records"])
                groups.remove(duplicate)

        for group in groups:
            identifiers = group["identifiers"]
            canonical = min(
                identifiers,
                key=lambda value: (
                    0 if value.startswith("GHSA-") else 1 if value.startswith("CVE-") else 2,
                    value,
                ),
            )
            levels = [severity(record) for record in group["records"]]
            classified = [level for level in levels if level in SEVERITY_ORDER]
            level = max(classified, key=SEVERITY_ORDER.__getitem__) if classified else "UNCLASSIFIED"
            findings.append({
                "package": package,
                "id": canonical,
                "aliases": sorted(identifiers - {canonical}),
                "severity": level,
                "excepted": bool(identifiers & exceptions),
            })
    return sorted(findings, key=lambda item: (item["package"], item["id"]))


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
    findings = merged_findings(package_advisories, details, exceptions)
    blocking = [
        finding
        for finding in findings
        if not finding["excepted"] and finding["severity"] in {"HIGH", "CRITICAL"}
    ]
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
