from pathlib import Path

from uat.gherkin import BINDINGS, assert_all_steps_bound, parse_feature
from uat import steps as _steps  # noqa: F401


def test_daily_feature_has_five_fully_bound_scenarios() -> None:
    scenarios = parse_feature(Path("uat/features/daily.feature"))
    assert [scenario.name for scenario in scenarios] == [
        "Browse the generated catalog",
        "Inspect semantic stages",
        "Run Tensor Journey",
        "Compare models",
        "Inspect distributions",
    ]
    assert_all_steps_bound(scenarios)
    assert all(step.text in BINDINGS for scenario in scenarios for step in scenario.steps)
