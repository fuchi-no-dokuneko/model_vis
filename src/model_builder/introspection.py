from __future__ import annotations

import hashlib
import inspect
import math
import functools
import os
import re
import sys
from enum import Enum
from pathlib import Path
from types import FrameType
from typing import Any, Callable

import torch
from torch import nn


_ADDRESS = re.compile(r" at 0x[0-9a-fA-F]+")
_SECRET_KEY = re.compile(r"(?:password|secret|api[_-]?key|access[_-]?key|private[_-]?key|credential)", re.IGNORECASE)


def normalized_source_path(path: str | Path | None) -> str | None:
    if not path:
        return None
    resolved = Path(path).resolve()
    value = resolved.as_posix()
    marker = "/site-packages/"
    if marker in value:
        return value.split(marker, 1)[1]
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.name


def source_ref(obj: object, *, executed_line: int | None = None) -> dict[str, Any]:
    try:
        file = inspect.getsourcefile(obj)
        lines, start = inspect.getsourcelines(obj)
    except (OSError, TypeError):
        return {
            "source_uid": None,
            "file": None,
            "symbol": getattr(obj, "__qualname__", getattr(obj, "__name__", None)),
            "start_line": 0,
            "end_line": 0,
            "executed_line": executed_line or 0,
        }
    normalized = normalized_source_path(file)
    uid = "source.sha256." + hashlib.sha256((normalized or "").encode()).hexdigest()
    return {
        "source_uid": uid,
        "file": normalized,
        "symbol": getattr(obj, "__qualname__", getattr(obj, "__name__", None)),
        "start_line": start,
        "end_line": start + len(lines) - 1,
        "executed_line": executed_line or start,
    }


def source_ref_from_frame(frame: FrameType) -> dict[str, Any]:
    file = normalized_source_path(frame.f_code.co_filename)
    try:
        lines, start = inspect.getsourcelines(frame.f_code)
        end = start + len(lines) - 1
    except (OSError, TypeError):
        start = frame.f_code.co_firstlineno
        end = start
    uid = "source.sha256." + hashlib.sha256((file or "").encode()).hexdigest()
    return {
        "source_uid": uid,
        "file": file,
        "symbol": frame.f_code.co_qualname,
        "start_line": start,
        "end_line": end,
        "executed_line": frame.f_lineno,
    }


def tensor_metadata(value: torch.Tensor) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "shape": list(value.shape),
        "dtype": str(value.dtype),
        "device": str(value.device),
        "requires_grad": bool(value.requires_grad),
    }
    try:
        metadata.update({
            "stride": list(value.stride()),
            "storage_offset": int(value.storage_offset()),
            "is_contiguous": bool(value.is_contiguous()),
        })
    except RuntimeError:
        metadata.update({"stride": [], "storage_offset": 0, "is_contiguous": False})
    try:
        metadata["mutation_version"] = int(value._version)
    except RuntimeError:
        metadata["mutation_version"] = None
    return metadata


def sanitize_runtime_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return {"type": f"{type(value).__module__}.{type(value).__qualname__}", "truncated": True}
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, str):
        if Path(value).is_absolute():
            return {"type": "local_path", "name": Path(value).name}
        if len(value) >= 8 and any(value == candidate for candidate in os.environ.values()):
            return {"type": "environment_value", "redacted": True}
        return value if len(value) <= 500 else value[:497] + "..."
    if isinstance(value, Enum):
        return {"enum": f"{type(value).__module__}.{type(value).__qualname__}", "value": str(value.value)}
    if isinstance(value, Path):
        return normalized_source_path(value)
    if isinstance(value, (torch.dtype, torch.device)):
        return str(value)
    if isinstance(value, torch.Size):
        return list(value)
    if torch.is_tensor(value):
        return {"type": "tensor", **tensor_metadata(value)}
    if isinstance(value, nn.Module):
        return {"module": f"{type(value).__module__}.{type(value).__qualname__}"}
    if hasattr(value, "model_type") and hasattr(value, "to_dict"):
        return {
            "config_class": f"{type(value).__module__}.{type(value).__qualname__}",
            "model_type": getattr(value, "model_type", None),
            "config_ref": "config",
        }
    if isinstance(value, dict):
        items = list(value.items())[:100]
        result = {
            str(key): (
                {"redacted": True}
                if _SECRET_KEY.search(str(key))
                else sanitize_runtime_value(item, depth=depth + 1)
            )
            for key, item in items
        }
        if len(value) > len(items):
            result["__truncated_items__"] = len(value) - len(items)
        return result
    if isinstance(value, (tuple, list)):
        items = list(value)[:100]
        result = [sanitize_runtime_value(item, depth=depth + 1) for item in items]
        if len(value) > len(items):
            result.append({"truncated_items": len(value) - len(items)})
        return result
    text = _ADDRESS.sub("", repr(value))
    return {
        "type": f"{type(value).__module__}.{type(value).__qualname__}",
        "repr": text if len(text) <= 500 else text[:497] + "...",
    }


def signature_record(callable_obj: object) -> list[dict[str, Any]]:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return []
    result = []
    for parameter in signature.parameters.values():
        if parameter.name == "self":
            continue
        item: dict[str, Any] = {
            "name": parameter.name,
            "kind": parameter.kind.name.lower(),
            "required": (
                parameter.default is inspect.Parameter.empty
                and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
            ),
        }
        if parameter.default is not inspect.Parameter.empty:
            item["default"] = sanitize_runtime_value(parameter.default)
        result.append(item)
    return result


def callable_interface_record(callable_obj: object) -> dict[str, Any]:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return {"name": getattr(callable_obj, "__name__", "call"), "parameters": [], "returns": None, "text": "call(?)"}

    def annotation_name(annotation: Any) -> str | None:
        if annotation is inspect.Signature.empty:
            return None
        if isinstance(annotation, str):
            return annotation
        module = getattr(annotation, "__module__", None)
        name = getattr(annotation, "__qualname__", getattr(annotation, "__name__", None))
        if name:
            return f"{module}.{name}" if module and module != "builtins" else name
        return _ADDRESS.sub("", repr(annotation))[:500]

    parameters = signature_record(callable_obj)
    returns = annotation_name(signature.return_annotation)
    compact = ", ".join(
        f"{item['name']}:{item['kind']}{'' if item['required'] else '?'}"
        for item in parameters
    )
    name = getattr(callable_obj, "__name__", "call")
    return {
        "name": name,
        "parameters": parameters,
        "returns": returns,
        "text": f"{name}({compact})" + (f" -> {returns}" if returns else ""),
    }


class ConstructorRecorder:
    """Capture effective Python nn.Module constructor values during model creation."""

    def __init__(self) -> None:
        self._previous: Any = None
        self._records: dict[int, dict[str, Any]] = {}
        self._patched: list[tuple[type[nn.Module], Callable[..., Any]]] = []

    @staticmethod
    def _module_classes() -> list[type[nn.Module]]:
        result: list[type[nn.Module]] = [nn.Module]
        pending = [nn.Module]
        seen: set[type[nn.Module]] = {nn.Module}
        while pending:
            base = pending.pop()
            try:
                children = base.__subclasses__()
            except TypeError:
                children = []
            for child in children:
                if child in seen:
                    continue
                seen.add(child)
                result.append(child)
                pending.append(child)
        return result

    @staticmethod
    def _supplied_by(
        signature: inspect.Signature,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> dict[str, str]:
        supplied: dict[str, str] = {name: "keyword" for name in kwargs}
        remaining = len(args)
        for parameter in signature.parameters.values():
            if parameter.name == "self" or remaining <= 0:
                continue
            if parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD):
                supplied[parameter.name] = "positional"
                remaining -= 1
            elif parameter.kind == parameter.VAR_POSITIONAL:
                supplied[parameter.name] = "positional"
                remaining = 0
        return supplied

    def _capture(
        self,
        instance: nn.Module,
        constructor: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        if id(instance) in self._records:
            return
        try:
            signature = inspect.signature(constructor)
            bound = signature.bind(instance, *args, **kwargs)
            supplied = self._supplied_by(signature, args, kwargs)
            bound.apply_defaults()
        except (TypeError, ValueError):
            return
        values = []
        for parameter in signature.parameters.values():
            if parameter.name == "self" or parameter.name not in bound.arguments:
                continue
            provided = supplied.get(parameter.name, "default")
            values.append({
                "name": parameter.name,
                "kind": parameter.kind.name.lower(),
                "supplied_by": provided,
                "origin": "default" if provided == "default" else "runtime",
                "value": sanitize_runtime_value(bound.arguments[parameter.name]),
            })
        self._records[id(instance)] = {
            "class_name": f"{type(instance).__module__}.{type(instance).__qualname__}",
            "source_ref": source_ref(constructor),
            "signature": signature_record(constructor),
            "positional_arguments": [sanitize_runtime_value(value) for value in args],
            "keyword_arguments": {
                name: sanitize_runtime_value(value) for name, value in kwargs.items()
            },
            "effective_arguments": values,
            "capture_confidence": "actual_call",
        }

    def _patch_loaded_classes(self) -> None:
        for module_class in self._module_classes():
            original = module_class.__dict__.get("__init__")
            if original is None or not callable(original):
                continue

            @functools.wraps(original)
            def wrapped(
                instance: nn.Module,
                *args: Any,
                __original: Callable[..., Any] = original,
                **kwargs: Any,
            ) -> None:
                self._capture(instance, __original, args, kwargs)
                __original(instance, *args, **kwargs)

            try:
                setattr(module_class, "__init__", wrapped)
            except (AttributeError, TypeError):
                continue
            self._patched.append((module_class, original))

    def _profile(self, frame: FrameType, event: str, arg: object) -> None:
        if event != "call" or frame.f_code.co_name != "__init__":
            return
        instance = frame.f_locals.get("self")
        if not isinstance(instance, nn.Module) or id(instance) in self._records:
            return
        constructor = type(instance).__init__
        code = getattr(constructor, "__code__", None)
        if code is not None and code is not frame.f_code:
            return
        try:
            signature = inspect.signature(constructor)
        except (TypeError, ValueError):
            signature = None
        values: list[dict[str, Any]] = []
        if signature is not None:
            for parameter in signature.parameters.values():
                if parameter.name == "self" or parameter.name not in frame.f_locals:
                    continue
                value = sanitize_runtime_value(frame.f_locals[parameter.name])
                origin = "runtime"
                if parameter.default is not inspect.Parameter.empty:
                    default = sanitize_runtime_value(parameter.default)
                    if value == default:
                        origin = "default_or_equal"
                values.append({
                    "name": parameter.name,
                    "kind": parameter.kind.name.lower(),
                    "supplied_by": "unknown",
                    "origin": "default" if origin == "default_or_equal" else "runtime",
                    "value": value,
                })
        self._records[id(instance)] = {
            "class_name": f"{type(instance).__module__}.{type(instance).__qualname__}",
            "source_ref": source_ref(constructor),
            "signature": signature_record(constructor),
            "positional_arguments": [],
            "keyword_arguments": {},
            "effective_arguments": values,
            "capture_confidence": "effective_runtime",
        }

    def __enter__(self) -> ConstructorRecorder:
        self._previous = sys.getprofile()
        self._patch_loaded_classes()
        sys.setprofile(self._profile)
        return self

    def __exit__(self, *exc: object) -> None:
        sys.setprofile(self._previous)
        for module_class, original in reversed(self._patched):
            try:
                setattr(module_class, "__init__", original)
            except (AttributeError, TypeError):
                pass
        self._patched.clear()

    @staticmethod
    def _config_values(config: dict[str, Any]) -> list[tuple[str, Any]]:
        result: list[tuple[str, Any]] = []

        def visit(value: Any, path: str) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    visit(item, f"{path}.{key}" if path else str(key))
            elif isinstance(value, (list, tuple)):
                for index, item in enumerate(value):
                    visit(item, f"{path}[{index}]")
            else:
                result.append((path, sanitize_runtime_value(value)))

        visit(config, "")
        return result

    @staticmethod
    def _attach_config_origin(
        argument: dict[str, Any],
        config_values: list[tuple[str, Any]],
    ) -> None:
        value = argument.get("value")
        if isinstance(value, dict) and value.get("config_ref") == "config":
            argument.update({
                "origin": "config",
                "config_path": "$",
                "origin_confidence": "exact_reference",
            })
            return
        matching = [path for path, candidate in config_values if candidate == value]
        name = argument.get("name", "")
        named = [
            path for path in matching
            if path.rsplit(".", 1)[-1].split("[", 1)[0] == name
        ]
        candidates = named or matching
        if len(candidates) != 1:
            return
        argument.update({
            "origin": "config",
            "config_path": candidates[0],
            "origin_confidence": "name_and_value" if named else "unique_value",
        })

    def records_for(
        self,
        model: nn.Module,
        config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        config_values = self._config_values(config or {})
        result = []
        for index, (path, module) in enumerate(model.named_modules()):
            record = dict(self._records.get(id(module), {
                "class_name": f"{type(module).__module__}.{type(module).__qualname__}",
                "source_ref": source_ref(type(module).__init__),
                "signature": signature_record(type(module).__init__),
                "positional_arguments": [],
                "keyword_arguments": {},
                "effective_arguments": [],
                "capture_confidence": "signature_only",
            }))
            record["effective_arguments"] = [
                dict(argument) for argument in record["effective_arguments"]
            ]
            for argument in record["effective_arguments"]:
                self._attach_config_origin(argument, config_values)
            record.update({
                "module_id": f"module-{index:05d}",
                "qualified_name": path or "<root>",
            })
            result.append(record)
        return result
