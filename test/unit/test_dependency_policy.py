import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location("audit_python", ROOT / "scripts" / "audit-python.py")
assert SPEC and SPEC.loader
audit_python = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_python)

active_exceptions = audit_python.active_exceptions
production_packages = audit_python.production_packages
severity = audit_python.severity


def test_dependency_lock_is_exact_and_uses_cpu_torch() -> None:
    packages = dict(production_packages())
    assert packages["torch"] == "2.12.0"
    assert packages["pillow"] == "12.3.0"
    assert packages["setuptools"] == "78.1.1"
    assert all(version for version in packages.values())


def test_advisory_severity_uses_reviewed_osv_classification() -> None:
    assert severity({"database_specific": {"severity": "high"}}) == "HIGH"
    assert severity({}) == "UNCLASSIFIED"


def test_advisory_exceptions_are_complete_and_current(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(audit_python, "ROOT", tmp_path)
    security = tmp_path / "security"
    security.mkdir()
    (security / "advisory-exceptions.json").write_text('{"exceptions":[{"id":"ADV-1"}]}', encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete"):
        active_exceptions()
