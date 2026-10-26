import hashlib

import pytest

from conftest import PY


def version_cmd(text, exit_code=0):
    code = f"import sys; print({text!r}); sys.exit({exit_code})"
    return {"id": "ver", "argv": [PY, "-c", code],
            "facts": [{"key": "app.version", "extract": "regex",
                       "pattern": r"Version (\S+)", "type": "string"}]}


def test_fact_from_evidence(repo, cli):
    repo.write_config([version_cmd("Version 1.2.3")])
    assert cli("collect") == 0
    assert cli("facts") == 0
    [run_id] = repo.runs()
    fact = repo.facts()["app.version"]
    assert fact == {
        "value": "1.2.3",
        "type": "string",
        "run": run_id,
        "command": "ver",
        "extract": "regex",
        "source_sha256": hashlib.sha256(b"Version 1.2.3\n").hexdigest(),
        "collected_at": "2026-01-02T03:04:05Z",
    }


def test_failed_command_keeps_old_fact(repo, cli, monkeypatch):
    repo.write_config([version_cmd("Version 1.0")])
    assert cli("collect") == 0
    assert cli("facts") == 0
    first_run = repo.runs()[0]

    monkeypatch.setenv("PIDOC_NOW", "2026-01-03T00:00:00Z")
    repo.write_config([version_cmd("Version 2.0", exit_code=1)])
    assert cli("collect") == 3
    assert cli("facts") == 3
    fact = repo.facts()["app.version"]
    assert fact["value"] == "1.0"
    assert fact["run"] == first_run


def test_truncated_output_makes_no_fact(repo, cli, monkeypatch):
    repo.write_config([version_cmd("Version 1.0")])
    assert cli("collect") == 0
    assert cli("facts") == 0

    monkeypatch.setenv("PIDOC_NOW", "2026-01-03T00:00:00Z")
    repo.write_config([version_cmd("Version 2.0" + " pad" * 100)], max_output=50)
    assert cli("collect") == 0
    assert cli("facts") == 3
    assert repo.facts()["app.version"]["value"] == "1.0"


def test_truncated_output_first_time(repo, cli):
    repo.write_config([version_cmd("Version 2.0" + " pad" * 100)], max_output=50)
    assert cli("collect") == 0
    assert cli("facts") == 3
    assert repo.facts() == {}


def test_success_updates_fact(repo, cli, monkeypatch):
    repo.write_config([version_cmd("Version 1.0")])
    cli("collect")
    cli("facts")
    monkeypatch.setenv("PIDOC_NOW", "2026-01-03T00:00:00Z")
    repo.write_config([version_cmd("Version 2.0")])
    cli("collect")
    assert cli("facts") == 0
    fact = repo.facts()["app.version"]
    assert fact["value"] == "2.0"
    assert fact["run"] == "20260103T000000Z"
    assert fact["collected_at"] == "2026-01-03T00:00:00Z"


def test_facts_from_named_run(repo, cli, monkeypatch):
    repo.write_config([version_cmd("Version 1.0")])
    cli("collect")
    monkeypatch.setenv("PIDOC_NOW", "2026-01-03T00:00:00Z")
    repo.write_config([version_cmd("Version 2.0")])
    cli("collect")
    assert cli("facts", "--run", "20260102T030405Z") == 0
    assert repo.facts()["app.version"]["value"] == "1.0"


def test_latest_run_with_same_time(repo, cli):
    repo.write_config([version_cmd("Version 1.0")])
    cli("collect")
    repo.write_config([version_cmd("Version 2.0")])
    cli("collect")
    assert cli("facts") == 0
    assert repo.facts()["app.version"]["run"] == "20260102T030405Z-2"


def test_regex_no_match(repo, cli):
    repo.write_config([version_cmd("nothing here")])
    cli("collect")
    assert cli("facts") == 3
    assert repo.facts() == {}


def test_no_runs(repo, cli):
    repo.write_config([version_cmd("Version 1.0")])
    assert cli("facts") == 3


def test_shell_text_becomes_plain_fact(repo, cli):
    repo.write_config([{"id": "arg", "argv": [PY, "-c", "import sys; print(sys.argv[1])", "a; echo x"],
                        "facts": [{"key": "arg", "extract": "stdout_all", "type": "string"}]}])
    cli("collect")
    assert cli("facts") == 0
    assert repo.facts()["arg"]["value"] == "a; echo x"


@pytest.mark.parametrize("out, fact, expected", [
    ("  hello world \n", {"extract": "stdout_all", "type": "string"}, "hello world"),
    ("a\nb\nc\n", {"extract": "stdout_line", "line": 2, "type": "string"}, "b"),
    ("cores: 4\n", {"extract": "regex", "pattern": r"cores: (\d+)", "type": "int"}, 4),
    ("t=48.3C\n", {"extract": "regex", "pattern": r"t=([\d.]+)", "type": "float"}, 48.3),
    ("x\ny\n\nz\n", {"extract": "stdout_all", "type": "list"}, ["x", "y", "z"]),
    ('{"a": {"b": [10, 20]}}', {"extract": "json", "path": "a.b.1", "type": "int"}, 20),
    ('{"ok": true}', {"extract": "json", "path": "ok", "type": "bool"}, True),
    ('{"l": ["p", "q"]}', {"extract": "json", "path": "l", "type": "list"}, ["p", "q"]),
    ("yes\n", {"extract": "stdout_all", "type": "bool"}, True),
    ("false\n", {"extract": "stdout_all", "type": "bool"}, False),
])
def test_extract_and_types(repo, cli, out, fact, expected):
    repo.write_config([{"id": "c", "argv": [PY, "-c", f"print({out!r}, end='')"],
                        "facts": [{"key": "k", **fact}]}])
    cli("collect")
    assert cli("facts") == 0
    got = repo.facts()["k"]
    assert got["value"] == expected
    assert type(got["value"]) is type(expected)
    assert got["type"] == fact["type"]


@pytest.mark.parametrize("out, fact", [
    ("abc\n", {"extract": "stdout_all", "type": "int"}),
    ("maybe\n", {"extract": "stdout_all", "type": "bool"}),
    ("a\n", {"extract": "stdout_line", "line": 5, "type": "string"}),
    ("not json", {"extract": "json", "path": "a", "type": "string"}),
    ('{"a": 1}', {"extract": "json", "path": "b", "type": "int"}),
])
def test_extract_errors(repo, cli, out, fact):
    repo.write_config([{"id": "c", "argv": [PY, "-c", f"print({out!r}, end='')"],
                        "facts": [{"key": "k", **fact}]}])
    cli("collect")
    assert cli("facts") == 3
    assert repo.facts() == {}


def test_bad_extract_kind_is_config_error(repo, cli):
    repo.write_config([{"id": "c", "argv": [PY, "-c", "print(1)"],
                        "facts": [{"key": "k", "extract": "magic", "type": "string"}]}])
    assert cli("collect") == 2
