import json
from metadata import cap_tags, load_metadata


def test_cap_tags_stops_before_budget():
    assert cap_tags(["aaaa", "bbbb", "cccc"], budget=9) == ["aaaa"]  # 4 + 1 + 4 = 9 > 9 stops


def test_cap_tags_keeps_all_when_under_budget():
    assert cap_tags(["a", "b"], budget=480) == ["a", "b"]


def test_load_metadata_from_json(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"title": "T", "description": "D", "tags": ["x", "y"]}))
    m = load_metadata(str(p), "", "", "")
    assert m == {"title": "T", "description": "D", "tags": ["x", "y"]}


def test_cli_overrides_and_title_truncation(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"title": "old", "description": "D", "tags": ["x"]}))
    long = "z" * 130
    m = load_metadata(str(p), long, "", "a, b ,")
    assert len(m["title"]) == 100
    assert m["tags"] == ["a", "b"]
