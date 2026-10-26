import json
import shutil
import socket

from conftest import make_exe, pidoc, write_config

CONFIG = """
[project]
name = "demo"
default_target = "pc"

[targets.pc]
kind = "local"
alias = "devpc"

[targets.pi]
kind = "ssh"
host = "pi@pi4.local"
alias = "board"
cwd = "pimon dir"

[collect]
allow_programs = ["uname", "hostname-echo", "python3"]

[[command]]
id = "kernel"
argv = ["uname", "-a"]
targets = ["pi"]
  [[command.fact]]
  key = "system.kernel"
  extract = "regex"
  pattern = 'Linux \\S+ (\\S+)'

[[command]]
id = "tricky"
argv = ["python3", "-c", "print('a; b' + \\"$HOME\\")"]
targets = ["pi"]

[[command]]
id = "who"
argv = ["hostname-echo"]
targets = ["pc"]
  [[command.fact]]
  key = "system.banner"
  extract = "stdout_line"

[redact]
patterns = [ { re = '\\b(?:\\d{1,3}\\.){3}\\d{1,3}\\b', to = "<ip>" } ]
"""

# 가짜 ssh: 받은 argv 를 NUL 로 구분해 파일에 남기고, 정해 둔 출력을 낸다
FAKE_SSH = """\
printf '%s\\0' "$@" > "$SSH_LOG"
echo "Linux pi4 6.12.47+rpt-rpi-v8 #1 SMP 192.0.2.10 pi4.local"
"""


def setup(repo, bindir, monkeypatch, tmp_path):
    log = tmp_path / "ssh.log"
    monkeypatch.setenv("SSH_LOG", str(log))
    make_exe(bindir, "ssh", FAKE_SSH)
    make_exe(bindir, "hostname-echo", "echo 'built on build-host-7.lan by build-host-7'\n")
    write_config(repo, CONFIG.replace('allow_programs = [', 'env_allow = ["PATH", "SSH_LOG"]\nallow_programs = ['))
    return log


def ssh_calls(log):
    return log.read_bytes().decode().split("\0")[:-1]


def test_ssh_argv(repo, bindir, monkeypatch, tmp_path):
    log = setup(repo, bindir, monkeypatch, tmp_path)
    assert pidoc("collect", "--target", "pi", "--only", "kernel") == 0
    argv = ssh_calls(log)
    assert argv[:6] == ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10"]
    assert argv[6:8] == ["--", "pi@pi4.local"]
    assert argv[8] == "cd 'pimon dir' && env LC_ALL=C.UTF-8 uname -a"
    assert len(argv) == 9


def test_ssh_quotes_arguments(repo, bindir, monkeypatch, tmp_path):
    log = setup(repo, bindir, monkeypatch, tmp_path)
    pidoc("collect", "--target", "pi", "--only", "tricky")
    line = ssh_calls(log)[-1]
    assert line.endswith("python3 -c 'print('\"'\"'a; b'\"'\"' + \"$HOME\")'")


def test_ssh_not_allowed_program_never_runs(repo, bindir, monkeypatch, tmp_path):
    log = setup(repo, bindir, monkeypatch, tmp_path)
    write_config(repo, (repo / "docs/pidoc.toml").read_text()
                 + '\n[[command]]\nid = "rm"\nargv = ["rm", "-rf", "x"]\ntargets = ["pi"]\n')
    assert pidoc("collect", "--target", "pi", "--only", "rm") == 3
    assert not log.exists()


def test_ssh_requires_allow_list(repo, bindir, monkeypatch, tmp_path):
    log = setup(repo, bindir, monkeypatch, tmp_path)
    text = (repo / "docs/pidoc.toml").read_text().replace('allow_programs = ["uname", "hostname-echo", "python3"]', "")
    write_config(repo, text)
    assert pidoc("collect", "--target", "pi") == 3
    assert not log.exists()


def test_ssh_evidence_is_redacted(repo, bindir, monkeypatch, tmp_path):
    setup(repo, bindir, monkeypatch, tmp_path)
    assert pidoc("collect", "--target", "pi", "--only", "kernel", "--keep-raw") == 0
    run = repo / "docs/evidence/runs/20261026T231500-pi"
    out = (run / "kernel.stdout").read_text()
    assert out == "Linux board 6.12.47+rpt-rpi-v8 #1 SMP <ip> board\n"
    record = json.loads((run / "kernel.json").read_text())
    assert record["argv"] == ["uname", "-a"] and record["redacted"] == 3
    assert "pi4" not in (run / "kernel.json").read_text()
    raw = repo / "docs/evidence/private/20261026T231500-pi/kernel.stdout"
    assert "192.0.2.10" in raw.read_text()
    facts = json.loads((repo / "docs/facts/pi.json").read_text())
    assert facts["alias"] == "board"
    assert facts["facts"]["system.kernel"]["value"] == "6.12.47+rpt-rpi-v8"


def test_local_hostname_redacted(repo, bindir, monkeypatch, tmp_path):
    setup(repo, bindir, monkeypatch, tmp_path)
    monkeypatch.setattr(socket, "gethostname", lambda: "build-host-7.lan")
    assert pidoc("collect", "--target", "pc") == 0
    facts = json.loads((repo / "docs/facts/pc.json").read_text())
    assert facts["facts"]["system.banner"]["value"] == "built on devpc by devpc"


def test_replay_rebuilds_facts(repo, bindir, monkeypatch, tmp_path):
    setup(repo, bindir, monkeypatch, tmp_path)
    pidoc("collect", "--target", "pi", "--only", "kernel")
    facts_file = repo / "docs/facts/pi.json"
    before = facts_file.read_text()
    facts_file.unlink()
    shutil.rmtree(bindir)                       # ssh 가 없어도 된다
    assert pidoc("replay", "docs/evidence/runs") == 0
    assert facts_file.read_text() == before


def test_replay_uses_changed_rule(repo, bindir, monkeypatch, tmp_path):
    setup(repo, bindir, monkeypatch, tmp_path)
    pidoc("collect", "--target", "pi", "--only", "kernel")
    text = (repo / "docs/pidoc.toml").read_text().replace(r"Linux \S+ (\S+)", r"(\d+\.\d+)")
    write_config(repo, text)
    assert pidoc("replay", "docs/evidence/runs/20261026T231500-pi") == 0
    facts = json.loads((repo / "docs/facts/pi.json").read_text())
    assert facts["facts"]["system.kernel"]["value"] == "6.12"


def test_replay_detects_tampering(repo, bindir, monkeypatch, tmp_path, capsys):
    setup(repo, bindir, monkeypatch, tmp_path)
    pidoc("collect", "--target", "pi", "--only", "kernel")
    (repo / "docs/evidence/runs/20261026T231500-pi/kernel.stdout").write_text("Linux x 9.9\n")
    assert pidoc("replay", "docs/evidence/runs") == 3
    assert "손댄 증거" in capsys.readouterr().err
