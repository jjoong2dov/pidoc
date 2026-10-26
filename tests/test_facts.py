import pytest

from pidoc import facts
from pidoc.facts import FactError

OUT = b"pimon 0.3\nusage: demo {once,run,check-config}\n"


def rule(**kw):
    kw.setdefault("type", "string")
    return kw


def test_stdout_all_and_line():
    assert facts.extract(rule(extract="stdout_all"), OUT) == "pimon 0.3\nusage: demo {once,run,check-config}"
    assert facts.extract(rule(extract="stdout_line"), OUT) == "pimon 0.3"
    assert facts.extract(rule(extract="stdout_line", line=2), OUT).startswith("usage")
    with pytest.raises(FactError, match="3 번째 줄"):
        facts.extract(rule(extract="stdout_line", line=3), OUT)


def test_regex_group_and_list():
    r = rule(extract="regex", pattern=r"\{([a-z,-]+)\}", type="list")
    assert facts.extract(r, OUT) == ["once", "run", "check-config"]
    assert facts.extract(rule(extract="regex", pattern=r"\d+\.\d+", type="float"), OUT) == 0.3
    with pytest.raises(FactError, match="정규식이 맞지"):
        facts.extract(rule(extract="regex", pattern="nothing"), OUT)


def test_json_path():
    data = b'{"checks": {"temp": {"value": 48.3, "level": "ok"}}, "list": [1, 2]}'
    assert facts.extract(rule(extract="json", path="checks.temp.value", type="float"), data) == 48.3
    assert facts.extract(rule(extract="json", path="list.1", type="int"), data) == 2
    with pytest.raises(FactError, match="disk 가 없습니다"):
        facts.extract(rule(extract="json", path="checks.disk"), data)
    with pytest.raises(FactError, match="JSON 이 아닙니다"):
        facts.extract(rule(extract="json", path="a"), b"not json")


@pytest.mark.parametrize("value, kind, expected", [
    ("42", "int", 42), (42.0, "int", 42), ("3.5", "float", 3.5), ("yes", "bool", True),
    (False, "bool", False), ("a, b", "list", ["a", "b"]), (7, "string", "7"),
])
def test_convert(value, kind, expected):
    assert facts.convert(value, kind) == expected


@pytest.mark.parametrize("value, kind", [("4.5", "int"), (4.5, "int"), (True, "int"), ("maybe", "bool"),
                                          ({"a": 1}, "string"), ("x", "float")])
def test_convert_rejects(value, kind):
    with pytest.raises(FactError):
        facts.convert(value, kind)


def test_update_file_keeps_old_keys(tmp_path):
    facts.update_file(tmp_path, "pc", "devpc", {"a.b": {"value": 1, "type": "int"}})
    facts.update_file(tmp_path, "pc", "devpc", {"c.d": {"value": 2, "type": "int"}})
    data = facts.load_file(tmp_path, "pc")
    assert set(data["facts"]) == {"a.b", "c.d"}
    assert (tmp_path / "pc.json").read_text().endswith("}\n")


def test_expired():
    f = {"collected_at": "2026-10-01T00:00:00+09:00", "max_age_days": 7}
    assert facts.is_expired(f)
    assert not facts.is_expired(dict(f, max_age_days=None))
