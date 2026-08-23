import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location("audit_python", ROOT / "scripts" / "audit-python.py")
assert SPEC and SPEC.loader
audit_python = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_python)

active_exceptions = audit_python.active_exceptions
merged_findings = audit_python.merged_findings
production_packages = audit_python.production_packages
severity = audit_python.severity


@pytest.fixture
def aliased_osv_records() -> tuple[set[tuple[str, str]], dict[str, dict]]:
    vector = "CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:L/A:N"
    return (
        {
            ("setuptools", "GHSA-h35f-9h28-mq5c"),
            ("setuptools", "PYSEC-2026-3447"),
            ("torch", "GHSA-low-example"),
        },
        {
            "GHSA-h35f-9h28-mq5c": {
                "aliases": ["CVE-2026-59890", "PYSEC-2026-3447"],
                "database_specific": {"severity": "MODERATE"},
                "severity": [{"type": "CVSS_V3", "score": vector}],
            },
            "PYSEC-2026-3447": {
                "aliases": ["CVE-2026-59890", "GHSA-h35f-9h28-mq5c"],
                "severity": [{"type": "CVSS_V3", "score": vector}],
            },
            "GHSA-low-example": {
                "database_specific": {"severity": "LOW"},
            },
        },
    )


def test_dependency_lock_is_exact_and_uses_cpu_torch() -> None:
    packages = dict(production_packages())
    assert packages["torch"] == "2.12.0"
    assert packages["pillow"] == "12.3.0"
    assert packages["setuptools"] == "78.1.1"
    assert all(version for version in packages.values())


def test_advisory_severity_uses_reviewed_osv_classification() -> None:
    assert severity({"database_specific": {"severity": "high"}}) == "HIGH"
    assert severity({
        "database_specific": {"severity": "low"},
        "affected": [{"ecosystem_specific": {"severity": "high"}}],
        "severity": [{
            "type": "CVSS_V3",
            "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        }],
    }) == "CRITICAL"
    assert severity({"severity": [{"type": "CVSS_V3", "score": "7.2"}]}) == "HIGH"
    assert severity({}) == "UNCLASSIFIED"


def test_aliased_advisories_are_merged_and_keep_strongest_evidence(
    aliased_osv_records: tuple[set[tuple[str, str]], dict[str, dict]],
) -> None:
    package_advisories, details = aliased_osv_records
    findings = merged_findings(package_advisories, details, {"PYSEC-2026-3447"})

    assert len(findings) == 2
    setuptools = next(item for item in findings if item["package"] == "setuptools")
    assert setuptools == {
        "package": "setuptools",
        "id": "GHSA-h35f-9h28-mq5c",
        "aliases": ["CVE-2026-59890", "PYSEC-2026-3447"],
        "severity": "MODERATE",
        "excepted": True,
    }


def test_advisory_exceptions_are_complete_and_current(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(audit_python, "ROOT", tmp_path)
    security = tmp_path / "security"
    security.mkdir()
    (security / "advisory-exceptions.json").write_text('{"exceptions":[{"id":"ADV-1"}]}', encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete"):
        active_exceptions()
