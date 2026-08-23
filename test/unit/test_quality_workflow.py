from pathlib import Path

import yaml


def test_quality_workflow_gates_sonar_and_deploy_on_required_checks() -> None:
    path = Path(".github/workflows/quality.yml")
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    verify = workflow["jobs"]["verify"]
    deploy = workflow["jobs"]["deploy"]
    runs = "\n".join(step.get("run", "") for step in verify["steps"])
    actions = [step.get("uses", "") for step in verify["steps"]]

    assert workflow["on"]["schedule"][0]["cron"] == "15 3 * * *"
    assert "timeout 60s venv/bin/python -m pip install --requirement requirements-test.lock" in runs
    assert "timeout 60s npm ci --ignore-scripts" in runs
    assert "npm run test:coverage:check" in runs
    assert "src.model_builder.drift" in runs
    assert "npm run test:uat:check" in runs
    assert "SonarSource/sonarqube-scan-action@v8.1.0" in actions
    assert deploy["needs"] == "verify"
    assert "refs/heads/main" in deploy["if"]
    assert deploy["steps"][-1]["uses"] == "cloudflare/wrangler-action@v4.0.0"
