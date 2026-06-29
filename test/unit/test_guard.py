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

