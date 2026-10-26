import pytest

from pidoc import config
from pidoc.util import PidocError

from conftest import write_config

BASE = """
[project]
name = "demo"

[targets.pc]
kind = "local"
alias = "devpc"

[[command]]
id = "ver"
argv = ["fakever"]
  [[command.fact]]
  key = "tool.version"
  extract = "stdout_line"
"""


def test_load_defaults(repo):
    cfg = config.load(write_config(repo, BASE))
    assert cfg.root == repo.resolve()
    assert cfg.default_target == "pc"
    assert cfg.collect["timeout_s"] == 20
    cmd = cfg.commands[0]
    assert cmd["targets"] == ["pc"] and cmd["ok_exit"] == [0]
    assert cmd["fact"][0]["type"] == "string"


def test_find_walks_up(repo):
    write_config(repo, BASE)
    (repo / "a" / "b").mkdir(parents=True)
    assert config.find(repo / "a" / "b") == repo / "docs" / "pidoc.toml"


@pytest.mark.parametrize("extra, message", [
    ("[collect]\ntimeoutt = 3\n", "모르는 설정 collect.timeoutt"),
    ("[[command]]\nid = \"ver\"\nargv = [\"x\"]\n", "명령 id 가 겹칩니다"),
    ("[[command]]\nid = \"x\"\nargv = []\n", "argv 가 비었습니다"),
    ("[[command]]\nid = \"x\"\nargv = [\"x\"]\ntargets = [\"pi\"]\n", "모르는 대상: pi"),
    ("[[command]]\nid = \"x\"\nargv = [\"x\"]\n[[command.fact]]\nkey = \"Bad Key\"\nextract = \"regex\"\n", "소문자.점.구분"),
    ("[[command]]\nid = \"x\"\nargv = [\"x\"]\n[[command.fact]]\nkey = \"a.b\"\nextract = \"magic\"\n", "extract 는"),
    ("[[command]]\nid = \"x\"\nargv = [\"x\"]\n[[command.fact]]\nkey = \"a.b\"\nextract = \"regex\"\npattern = \"(\"\n", "정규식 오류"),
])
def test_rejects_bad_config(repo, extra, message):
    with pytest.raises(PidocError, match=message):
        config.load(write_config(repo, BASE + extra))


def test_ssh_host_from_env(repo, monkeypatch):
    text = BASE + '\n[targets.pi]\nkind = "ssh"\nalias = "pi4"\n'
    with pytest.raises(PidocError, match="PIDOC_TARGET_PI"):
        config.load(write_config(repo, text))
    monkeypatch.setenv("PIDOC_TARGET_PI", "pi@192.0.2.10")
    cfg = config.load(write_config(repo, text))
    assert cfg.targets["pi"].host == "pi@192.0.2.10"


def test_toml_syntax_error(repo):
    with pytest.raises(PidocError, match="TOML 문법 오류"):
        config.load(write_config(repo, "[project\n"))
