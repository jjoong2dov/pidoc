import shlex

import pytest

from conftest import PY, ssh_target

TRICKY = ["it's", '"q"', "a  b", "$HOME", "${PATH}", "`id`", "$(id)", "; echo x", "|", "*", "\\n", ""]


def ssh_cmd(cid, argv, **kw):
    return {"id": cid, "argv": argv, "targets": ["pi"], **kw}


def test_ssh_argv(repo, cli, fake_ssh):
    repo.write_config([ssh_cmd("u", ["printf", "ok"])], extra_targets=ssh_target())
    assert cli("collect") == 0
    [call] = fake_ssh.calls()
    kh = (repo.docs / "known_hosts").resolve()
    assert call == ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                    "-o", f"UserKnownHostsFile={kh}", "--", "pi@raspi.example", "printf ok"]
    [run_id] = repo.runs()
    assert repo.stdout(run_id, "u", target="pi") == b"ok"
    rec = repo.record(run_id, "u", target="pi")
    assert rec["argv"] == ["printf", "ok"]
    assert rec["ok"] is True


def test_remote_line_is_safe(repo, cli, fake_ssh):
    argv = ["printf", "[%s]\\n", *TRICKY]
    repo.write_config([ssh_cmd("q", argv)], extra_targets=ssh_target())
    assert cli("collect") == 0
    [call] = fake_ssh.calls()
    line = call[-1]
    assert line == shlex.join(argv)
    assert shlex.split(line) == argv
    # 가짜 ssh 는 그 줄을 sh 로 돌린다: 인자가 한 글자도 바뀌지 않아야 한다
    [run_id] = repo.runs()
    out = repo.stdout(run_id, "q", target="pi").decode()
    assert out == "".join(f"[{a}]\n" for a in TRICKY)
    assert "x\n" not in out.splitlines(keepends=True)


def test_not_allowed_program_never_calls_ssh(repo, cli, fake_ssh):
    repo.write_config([ssh_cmd("bad", ["rm", "-rf", "/tmp/nothing"])],
                      extra_targets=ssh_target(allow=["printf"]))
    assert cli("collect") == 3
    assert fake_ssh.calls() == []
    [run_id] = repo.runs()
    rec = repo.record(run_id, "bad", target="pi")
    assert rec["ok"] is False
    assert rec["exit_code"] is None
    assert "allow_programs" in rec["error"]
    assert repo.stdout(run_id, "bad", target="pi") == b""


def test_allowed_and_refused_mixed(repo, cli, fake_ssh):
    repo.write_config([ssh_cmd("bad", ["uname", "-a"]), ssh_cmd("good", ["printf", "hi"])],
                      extra_targets=ssh_target(allow=["printf"]))
    assert cli("collect") == 3
    assert [c[-1] for c in fake_ssh.calls()] == ["printf hi"]


def test_allow_programs_missing_means_nothing_allowed(repo, cli, fake_ssh):
    repo.write_config([ssh_cmd("u", ["printf", "x"])], extra_targets=ssh_target(allow=None))
    assert cli("collect") == 3
    assert fake_ssh.calls() == []


def test_program_must_match_exactly(repo, cli, fake_ssh):
    repo.write_config([ssh_cmd("u", ["/usr/bin/printf", "x"])],
                      extra_targets=ssh_target(allow=["printf"]))
    assert cli("collect") == 3
    assert fake_ssh.calls() == []


def test_local_target_not_limited(repo, cli, fake_ssh):
    repo.write_config([{"id": "l", "argv": [PY, "-c", "print(1)"]}],
                      extra_targets=ssh_target(allow=["printf"]))
    assert cli("collect") == 0
    assert fake_ssh.calls() == []


def test_host_from_env(repo, cli, fake_ssh, monkeypatch):
    monkeypatch.setenv("PIDOC_TARGET_PI", "admin@other.example")
    repo.write_config([ssh_cmd("u", ["printf", "x"])], extra_targets=ssh_target())
    assert cli("collect") == 0
    [call] = fake_ssh.calls()
    assert call[-2] == "admin@other.example"


def test_env_name_for_dashed_target(repo, cli, fake_ssh, monkeypatch):
    monkeypatch.setenv("PIDOC_TARGET_PI_2", "admin@other.example")
    repo.write_config([{"id": "u", "argv": ["printf", "x"], "targets": ["pi-2"]}],
                      extra_targets=ssh_target(name="pi-2"))
    assert cli("collect") == 0
    assert fake_ssh.calls()[0][-2] == "admin@other.example"


def test_remote_failure_keeps_old_fact(repo, cli, fake_ssh, monkeypatch):
    fact = {"key": "v", "extract": "stdout_all", "type": "string"}
    repo.write_config([ssh_cmd("v", ["printf", "1.0"], facts=[fact])], extra_targets=ssh_target())
    assert cli("collect") == 0
    assert cli("facts") == 0
    monkeypatch.setenv("PIDOC_NOW", "2026-01-03T00:00:00Z")
    repo.write_config([ssh_cmd("v", ["false"], facts=[fact])], extra_targets=ssh_target())
    assert cli("collect") == 3
    rec = repo.record("20260103T000000Z", "v", target="pi")
    assert rec["exit_code"] == 1
    assert cli("facts") == 3
    assert repo.facts("pi")["v"]["value"] == "1.0"


@pytest.mark.parametrize("target_text", [
    '[targets.pi]\nkind = "ssh"\nknown_hosts = "known_hosts"\n',
    '[targets.pi]\nkind = "ssh"\nhost = "-oProxyCommand=x"\nknown_hosts = "known_hosts"\n',
    '[targets.pi]\nkind = "ssh"\nhost = "pi@raspi.example extra"\nknown_hosts = "known_hosts"\n',
    '[targets.pi]\nkind = "ssh"\nhost = "pi@raspi.example"\n',
    '[targets.pi]\nkind = "ssh"\nhost = "pi@raspi.example"\nknown_hosts = "a b"\n',
    '[targets.pi]\nkind = "ssh"\nhost = "pi@raspi.example"\nknown_hosts = "kh"\nallow_programs = "printf"\n',
])
def test_bad_ssh_config(repo, cli, fake_ssh, target_text):
    repo.write_config([ssh_cmd("u", ["printf", "x"])], extra_targets=target_text)
    assert cli("collect") == 2
    assert fake_ssh.calls() == []


def test_bad_host_from_env(repo, cli, fake_ssh, monkeypatch):
    monkeypatch.setenv("PIDOC_TARGET_PI", "-oProxyCommand=x")
    repo.write_config([ssh_cmd("u", ["printf", "x"])], extra_targets=ssh_target())
    assert cli("collect") == 2
    assert fake_ssh.calls() == []
