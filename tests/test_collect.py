import json

from pidoc.util import sha256_bytes

from conftest import make_exe, pidoc, write_config

CONFIG = """
[project]
name = "demo"

[targets.pc]
kind = "local"
alias = "devpc"

[collect]
timeout_s = 5
allow_programs = ["fakever", "fakehelp", "fakefail", "fakeonce"]

[[command]]
id = "ver"
argv = ["fakever"]
  [[command.fact]]
  key = "tool.version"
  extract = "regex"
  pattern = 'demo (\\S+)'

[[command]]
id = "fail"
argv = ["fakefail"]
  [[command.fact]]
  key = "tool.never"
  extract = "stdout_all"

[[command]]
id = "once"
argv = ["fakeonce"]
ok_exit = [0, 1]
  [[command.fact]]
  key = "demo.level"
  extract = "json"
  path = "level"
  [[command.fact]]
  key = "demo.temp"
  extract = "json"
  path = "temp"
  type = "float"
"""


def setup(repo, bindir):
    make_exe(bindir, "fakever", "echo 'demo 1.2.3'\n")
    make_exe(bindir, "fakefail", "echo '망가짐' >&2\nexit 5\n")
    make_exe(bindir, "fakeonce", "echo '{\"level\": \"warn\", \"temp\": 71.5}'\nexit 1\n")
    write_config(repo, CONFIG)


def test_collect_saves_evidence_and_facts(repo, bindir, capsys):
    setup(repo, bindir)
    assert pidoc("collect") == 3          # fail 명령 때문에 3, 나머지는 계속
    run = repo / "docs/evidence/runs/20261026T231500-pc"
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["target"] == "pc" and manifest["alias"] == "devpc"
    assert manifest["results"]["ver"] == {"exit": 0, "ok": True}
    assert manifest["results"]["fail"]["ok"] is False
    assert [c["id"] for c in manifest["commands"]] == ["ver", "fail", "once"]
    record = json.loads((run / "ver.json").read_text())
    assert record["stdout"]["sha256"] == sha256_bytes((run / "ver.stdout").read_bytes())
    assert record["argv"] == ["fakever"] and record["exit"] == 0
    assert (run / "fail.stderr").read_bytes() == "망가짐\n".encode()

    data = json.loads((repo / "docs/facts/pc.json").read_text())
    f = data["facts"]
    assert f["tool.version"]["value"] == "1.2.3"
    assert f["tool.version"]["run"] == "20261026T231500-pc"
    assert f["tool.version"]["collected_at"] == "2026-10-26T23:15:00+09:00"
    assert f["demo.temp"]["value"] == 71.5 and f["demo.level"]["value"] == "warn"
    assert "tool.never" not in f
    out = capsys.readouterr().out
    assert "실패 fail: 종료 코드 5" in out and "| 망가짐" in out


def test_collect_only_and_second_run_dir(repo, bindir):
    setup(repo, bindir)
    assert pidoc("collect", "--only", "ver") == 0
    assert pidoc("collect", "--only", "ver") == 0
    runs = sorted(p.name for p in (repo / "docs/evidence/runs").iterdir())
    assert runs == ["20261026T231500-pc", "20261026T231500-pc-2"]


def test_not_allowed_program_is_failure(repo, bindir):
    setup(repo, bindir)
    make_exe(bindir, "evil", "echo hi\n")
    write_config(repo, CONFIG + '\n[[command]]\nid = "evil"\nargv = ["evil"]\n')
    assert pidoc("collect", "--only", "evil") == 3
    record = json.loads((repo / "docs/evidence/runs/20261026T231500-pc/evil.json").read_text())
    assert "허용 목록" in record["error"]


def test_unknown_only_is_usage_error(repo, bindir, capsys):
    setup(repo, bindir)
    assert pidoc("collect", "--only", "nope") == 2
    assert "모르는 명령 id" in capsys.readouterr().err


def test_facts_listing(repo, bindir, capsys):
    setup(repo, bindir)
    pidoc("collect", "--only", "ver")
    capsys.readouterr()
    assert pidoc("facts") == 0
    out = capsys.readouterr().out
    assert "tool.version = 1.2.3" in out and "0.0일 전" in out
    assert pidoc("facts", "--json") == 0
    assert json.loads(capsys.readouterr().out)["pc"]["tool.version"]["value"] == "1.2.3"


def test_init_creates_skeleton(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert pidoc("init") == 0
    assert (tmp_path / "docs/pidoc.toml").is_file()
    assert (tmp_path / "docs/evidence/runs").is_dir()
    assert pidoc("init") == 2                      # 덮어쓰지 않음
    assert pidoc("collect") == 0                   # 견본 그대로 돌아감(python3 --version)


def test_missing_config_is_usage_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert pidoc("facts") == 2
    assert "pidoc init" in capsys.readouterr().err
