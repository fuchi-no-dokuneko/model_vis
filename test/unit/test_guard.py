import os
import socket
from pathlib import Path

import pytest

from src.model_builder.guard import NoNetworkGuard, scan_forbidden_artifacts


def test_network_is_blocked_during_model_execution() -> None:
    with NoNetworkGuard(), pytest.raises(RuntimeError, match="NO_WEIGHT_DOWNLOAD_GUARD"):
        socket.socket().connect(("127.0.0.1", 9))


def test_forbidden_artifact_scan(tmp_path: Path) -> None:
    allowed = tmp_path / "trace.json"
    forbidden = tmp_path / "model.safetensors"
    allowed.write_text("{}", encoding="utf-8")
    forbidden.write_bytes(b"not actually weights")

    assert scan_forbidden_artifacts([tmp_path]) == [forbidden]


def test_network_guard_restores_existing_offline_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_HUB_OFFLINE", "custom")
    with NoNetworkGuard():
        assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["HF_HUB_OFFLINE"] == "custom"


def test_artifact_scan_skips_missing_directories_and_matches_shard_names(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    shard = nested / "model-00001-of-00002"
    shard.write_bytes(b"fixture")
    direct = tmp_path / "pytorch_model-test"
    direct.write_bytes(b"fixture")

    assert set(scan_forbidden_artifacts([tmp_path / "missing", tmp_path])) == {shard, direct}
    assert scan_forbidden_artifacts([direct]) == [direct]
