from __future__ import annotations

import argparse
import json
from pathlib import Path

from .builder import build


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Compile model structures into static assets")
    command.add_argument("--catalog", type=Path, default=Path("model.txt"))
    command.add_argument("--scope-out", type=Path, default=Path("model_scope.generated.yaml"))
    command.add_argument("--out", type=Path, default=Path("model_code"))
    command.add_argument("--cache", type=Path, default=Path("build_cache"))
    command.add_argument("--device", choices=("auto", "cpu"), default="cpu")
    command.add_argument("--max-resident-memory-gb", type=float, default=70)
    command.add_argument("--require-forward", action="store_true")
    command.add_argument("--allow-staged-large-models", action="store_true")
    command.add_argument("--resume", action="store_true")
    command.add_argument("--fetch-policy", choices=("source-config-only",), default="source-config-only")
    command.add_argument("--forbid-weight-downloads", action="store_true")
    command.add_argument("--plan-only", action="store_true")
    command.add_argument("--offset", type=int, default=0)
    command.add_argument("--limit", type=int)
    command.add_argument("--include", action="append", default=[])
    command.add_argument(
        "--include-file",
        action="append",
        type=Path,
        default=[],
        help="Read family IDs or names to include, one per line; blank lines and comments are ignored",
    )
    return command


def _file_includes(paths: list[Path]) -> list[str]:
    values: list[str] = []
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"include file does not exist: {path}")
        values.extend(
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    return values


def main() -> int:
    args = parser().parse_args()
    report = build(
        args.catalog,
        args.scope_out,
        args.out,
        args.cache,
        plan_only=args.plan_only,
        offset=args.offset,
        limit=args.limit,
        includes=tuple([*args.include, *_file_includes(args.include_file)]),
        resume=args.resume,
    )
    print(json.dumps(report, indent=2))
    return 0 if report["status"] in {"planned", "passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
