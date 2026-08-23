from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


STEP_KEYWORDS = ("Given ", "When ", "Then ", "And ")
Binding = Callable[[object], None]


@dataclass(frozen=True)
class Step:
    text: str
    line: int


@dataclass(frozen=True)
class Scenario:
    name: str
    steps: tuple[Step, ...]


BINDINGS: dict[str, Binding] = {}


def bind(text: str):
    def decorator(function: Binding) -> Binding:
        if text in BINDINGS:
            raise ValueError(f"duplicate Gherkin binding: {text}")
        BINDINGS[text] = function
        return function
    return decorator


def parse_feature(path: Path) -> list[Scenario]:
    scenarios: list[Scenario] = []
    name: str | None = None
    steps: list[Step] = []
    saw_feature = False
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("Feature:"):
            if saw_feature:
                raise ValueError(f"multiple Feature declarations at line {line_number}")
            saw_feature = True
            continue
        if line.startswith("Scenario:"):
            if name:
                scenarios.append(Scenario(name, tuple(steps)))
            name = line.removeprefix("Scenario:").strip()
            steps = []
            continue
        keyword = next((item for item in STEP_KEYWORDS if line.startswith(item)), None)
        if keyword:
            if not name:
                raise ValueError(f"step before Scenario at line {line_number}")
            steps.append(Step(line.removeprefix(keyword).strip(), line_number))
            continue
        raise ValueError(f"unsupported Gherkin syntax at line {line_number}: {line}")
    if name:
        scenarios.append(Scenario(name, tuple(steps)))
    if not saw_feature or not scenarios or any(not scenario.steps for scenario in scenarios):
        raise ValueError("feature must declare at least one nonempty Scenario")
    return scenarios


def assert_all_steps_bound(scenarios: list[Scenario]) -> None:
    missing = [f"line {step.line}: {step.text}" for scenario in scenarios for step in scenario.steps if step.text not in BINDINGS]
    if missing:
        raise ValueError("unbound Gherkin steps: " + ", ".join(missing))
