import re
from pathlib import Path

import yaml


FULL_ACTION_SHA = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def test_quality_workflow_gates_sonar_and_deploy_on_required_checks() -> None:
    path = Path(".github/workflows/quality.yml")
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    verify = workflow["jobs"]["verify"]
    deploy = workflow["jobs"]["deploy"]
    runs = "\n".join(step.get("run", "") for step in verify["steps"])
    actions = [
        step["uses"]
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if "uses" in step
    ]

    assert workflow["on"]["schedule"][0]["cron"] == "15 3 * * *"
    assert "timeout 60s venv/bin/python -m pip install --requirement requirements-test.lock" in runs
    assert "timeout 60s npm ci --ignore-scripts" in runs
    assert "npm run test:coverage:check" in runs
    assert "src.model_builder.drift" in runs
    assert "npm run test:uat:check" in runs
    assert actions and all(FULL_ACTION_SHA.fullmatch(action) for action in actions)
    assert "SonarSource/sonarqube-scan-action@fd88b7d7ccbaefd23d8f36f73b59db7a3d246602" in actions
    assert deploy["needs"] == "verify"
    assert "refs/heads/main" in deploy["if"]
    assert deploy["steps"][-1]["uses"] == "cloudflare/wrangler-action@ebbaa1584979971c8614a24965b4405ff95890e0"
