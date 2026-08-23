import math

from src.model_builder.util import read_json, slug, write_json


def test_slug_and_json_helpers_cover_fallback_and_nonfinite_values(tmp_path) -> None:
    assert slug("---") == "unnamed"
    target = tmp_path / "nested" / "value.json"
    write_json(target, {"tuple": (1, 2), "values": [math.inf, -math.inf, math.nan]})

    result = read_json(target)
    assert result["tuple"] == [1, 2]
    assert result["values"] == ["inf", "-inf", "nan"]
