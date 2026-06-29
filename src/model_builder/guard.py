from __future__ import annotations

import os
import re
import socket
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any


FORBIDDEN_SUFFIXES = {
    ".bin", ".safetensors", ".pt", ".pth", ".ckpt", ".gguf", ".onnx", ".h5"
}
FORBIDDEN_NAMES = (re.compile(r"^pytorch_model-"), re.compile(r"^model-.*of-"))


class NoNetworkGuard(AbstractContextManager["NoNetworkGuard"]):
    """Block all network access while models are instantiated and executed."""

    def __enter__(self) -> "NoNetworkGuard":
        self._old_env = {
            key: os.environ.get(key)
            for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "DIFFUSERS_OFFLINE")
        }
        os.environ.update({
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "DIFFUSERS_OFFLINE": "1",
        })
        self._connect = socket.socket.connect

        def blocked_connect(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("network access blocked by NO_WEIGHT_DOWNLOAD_GUARD")

        socket.socket.connect = blocked_connect  # type: ignore[method-assign]
        return self

    def __exit__(self, *exc: object) -> None:
        socket.socket.connect = self._connect  # type: ignore[method-assign]
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def scan_forbidden_artifacts(paths: list[Path]) -> list[Path]:
    violations: list[Path] = []
    for root in paths:
        if not root.exists():
            continue
        files = (root.rglob("*") if root.is_dir() else (root,))
        for path in files:
            if not path.is_file():
                continue
            if path.suffix.lower() in FORBIDDEN_SUFFIXES:
                violations.append(path)
            elif any(pattern.match(path.name) for pattern in FORBIDDEN_NAMES):
                violations.append(path)
    return violations

