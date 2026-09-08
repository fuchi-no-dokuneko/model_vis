from __future__ import annotations

from bisect import bisect_right
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SOURCE_PATHS = {
    path.name: Path("src/ui") / path.name
    for path in (Path(__file__).parents[2] / "src/ui").glob("*.js")
}


class BrowserCoverage:
    def __init__(self, driver, root: Path) -> None:
        self.driver = driver
        self.root = root
        self.entries: dict[str, dict[tuple[str, int, int], dict[tuple[int, int], int]]] = {}

    def start(self) -> None:
        self.driver.execute_cdp_cmd("Profiler.enable", {})
        self.driver.execute_cdp_cmd(
            "Profiler.startPreciseCoverage",
            {"callCount": True, "detailed": True, "allowTriggeredUpdates": False},
        )

    def capture(self) -> None:
        entries = self.driver.execute_cdp_cmd("Profiler.takePreciseCoverage", {})["result"]
        for entry in entries:
            url = entry.get("url", "")
            name = Path(urlparse(url).path).name
            if name not in SOURCE_PATHS:
                continue
            merged_functions = self.entries.setdefault(url, {})
            for function in entry.get("functions", []):
                function_ranges = function.get("ranges", [])
                if not function_ranges:
                    continue
                primary = function_ranges[0]
                function_key = (
                    function.get("functionName") or "",
                    primary["startOffset"],
                    primary["endOffset"],
                )
                merged_ranges = merged_functions.setdefault(function_key, {})
                for item in function_ranges:
                    range_key = (item["startOffset"], item["endOffset"])
                    merged_ranges[range_key] = max(merged_ranges.get(range_key, 0), int(item["count"]))

    def write_lcov(self, output: Path) -> None:
        self.capture()
        self.driver.execute_cdp_cmd("Profiler.stopPreciseCoverage", {})
        self.driver.execute_cdp_cmd("Profiler.disable", {})
        records = []
        for url, merged_functions in self.entries.items():
            name = Path(urlparse(url).path).name
            relative = SOURCE_PATHS.get(name)
            if relative and (self.root / relative).is_file():
                functions = [
                    {
                        "functionName": function_name,
                        "ranges": [
                            {"startOffset": start, "endOffset": end, "count": count}
                            for (start, end), count in sorted(ranges.items())
                        ],
                    }
                    for (function_name, _start, _end), ranges in merged_functions.items()
                ]
                records.append(self._record(relative, functions))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("".join(records), encoding="utf-8")

    def _record(self, relative: Path, functions: list[dict[str, Any]]) -> str:
        source = (self.root / relative).read_text(encoding="utf-8")
        starts = [0]
        for index, character in enumerate(source):
            if character == "\n":
                starts.append(index + 1)

        ranges = [item for function in functions for item in function.get("ranges", [])]

        def line_number(offset: int) -> int:
            return bisect_right(starts, offset)

        def count_at(offset: int) -> int:
            matching = [
                item for item in ranges
                if item["startOffset"] <= offset < item["endOffset"]
            ]
            if not matching:
                return 0
            most_specific = min(matching, key=lambda item: item["endOffset"] - item["startOffset"])
            return int(most_specific["count"])

        lines = []
        for number, start in enumerate(starts, start=1):
            end = starts[number] - 1 if number < len(starts) else len(source)
            text = source[start:end]
            if text.strip():
                first_code = start + len(text) - len(text.lstrip())
                lines.append((number, count_at(first_code)))

        function_rows = []
        branch_rows = []
        for function_index, function in enumerate(functions):
            function_ranges = function.get("ranges", [])
            if not function_ranges:
                continue
            primary = function_ranges[0]
            function_rows.append((line_number(primary["startOffset"]), function.get("functionName") or f"anonymous_{function_index}", int(primary["count"])))
            for branch_index, branch in enumerate(function_ranges[1:]):
                branch_rows.append((line_number(branch["startOffset"]), function_index, branch_index, int(branch["count"])))

        result = ["TN:\n", f"SF:{relative.as_posix()}\n"]
        result.extend(f"FN:{line},{name}\n" for line, name, _ in function_rows)
        result.extend(f"FNDA:{count},{name}\n" for _, name, count in function_rows)
        result.extend((f"FNF:{len(function_rows)}\n", f"FNH:{sum(count > 0 for _, _, count in function_rows)}\n"))
        result.extend(f"BRDA:{line},{block},{branch},{count}\n" for line, block, branch, count in branch_rows)
        result.extend((f"BRF:{len(branch_rows)}\n", f"BRH:{sum(count > 0 for *_, count in branch_rows)}\n"))
        result.extend(f"DA:{line},{count}\n" for line, count in lines)
        result.extend((f"LF:{len(lines)}\n", f"LH:{sum(count > 0 for _, count in lines)}\n", "end_of_record\n"))
        return "".join(result)
