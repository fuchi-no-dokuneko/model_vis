from pathlib import Path

from uat.gherkin import BINDINGS, assert_all_steps_bound, parse_feature
from uat import steps as _steps  # noqa: F401


def test_daily_and_recording_features_are_fully_bound() -> None:
    suites = {
        "daily.feature": 16,
        "demo-en.feature": 1,
        "demo-yue.feature": 1,
    }
    for filename, expected_count in suites.items():
        scenarios = parse_feature(Path("uat/features") / filename)
        assert len(scenarios) == expected_count
        assert_all_steps_bound(scenarios)
        assert all(step.text in BINDINGS for scenario in scenarios for step in scenario.steps)
