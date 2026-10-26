import hashlib
import json
import os
import subprocess
import sys

from conftest import PY, ROOT


def test_collect_saves_evidence(repo, cli):
    repo.write_config([{"id": "hello", "argv": [PY, "-c", "print('hi')"]}])
    assert cli("collect") == 0
    [run_id] = repo.runs()
    assert run_id == "20260102T030405Z"
    rundir = repo.docs / "evidence" / "runs" / run_id
    manifest = json.loads((rundir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == run_id
    assert manifest["created_at"] == "2026-01-02T03:04:05Z"
    rec = repo.record(run_id, "hello")
    assert rec["argv"] == [PY, "-c", "print('hi')"]
    assert rec["exit_code"] == 0
    assert rec["timed_out"] is False
    assert rec["stdout_truncated"] is False
    assert rec["started_at"] == "2026-01-02T03:04:05Z"
    out = repo.stdout(run_id, "hello")
    assert out == b"hi\n"
    assert rec["stdout_sha256"] == hashlib.sha256(out).hexdigest()


def test_raw_bytes_kept(repo, cli):
    code = "import sys; sys.stdout.buffer.write(b'a\\r\\n\\x00\\xff'); sys.stderr.buffer.write(b'e\\xfe')"
    repo.write_config([{"id": "raw", "argv": [PY, "-c", code]}])
    assert cli("collect") == 0
    [run_id] = repo.runs()
    assert repo.stdout(run_id, "raw") == b"a\r\n\x00\xff"
    err = (repo.docs / "evidence" / "runs" / run_id / "pc" / "raw.stderr").read_bytes()
    assert err == b"e\xfe"


def test_no_shell(repo, cli):
    argv = [PY, "-c", "import sys; print(sys.argv[1:])", "a; echo x", "$HOME", "|", "`id`"]
    repo.write_config([{"id": "args", "argv": argv}])
    assert cli("collect") == 0
    [run_id] = repo.runs()
    out = repo.stdout(run_id, "args").decode()
    assert out == repr(["a; echo x", "$HOME", "|", "`id`"]) + "\n"
    assert "x\n" not in out.splitlines(keepends=True)


def test_timeout(repo, cli):
    repo.write_config(
        [{"id": "slow", "argv": [PY, "-c", "import time; print('start', flush=True); time.sleep(30)"],
          "facts": [{"key": "s", "extract": "stdout_all", "type": "string"}]}],
        timeout_s=0.5,
    )
    assert cli("collect") == 3
    [run_id] = repo.runs()
    rec = repo.record(run_id, "slow")
    assert rec["timed_out"] is True
    assert rec["duration_s"] < 10
    assert repo.stdout(run_id, "slow") == b"start\n"
    cli("facts")
    assert repo.facts() == {}


def test_output_limit(repo, cli):
    repo.write_config(
        [{"id": "big", "argv": [PY, "-c", "print('x' * 5000)"]}],
        max_output=100,
    )
    assert cli("collect") == 0
    [run_id] = repo.runs()
    rec = repo.record(run_id, "big")
    assert rec["stdout_truncated"] is True
    assert rec["stdout_bytes"] == 5001
    assert repo.stdout(run_id, "big") == b"x" * 100
    assert rec["stdout_sha256"] == hashlib.sha256(b"x" * 100).hexdigest()


def test_env_allow_list(repo, cli, monkeypatch):
    monkeypatch.setenv("PIDOC_SECRET_X", "s3cret")
    monkeypatch.setenv("LANG", "C")
    code = "import os, json; print(json.dumps({k: os.environ.get(k) for k in ['PIDOC_SECRET_X', 'LANG', 'LC_ALL', 'PIDOC_NOW']}))"
    repo.write_config([{"id": "env", "argv": [PY, "-c", code]}])
    assert cli("collect") == 0
    [run_id] = repo.runs()
    env = json.loads(repo.stdout(run_id, "env"))
    assert env == {"PIDOC_SECRET_X": None, "LANG": "C", "LC_ALL": "C.UTF-8", "PIDOC_NOW": None}


def test_nonzero_exit_reports_failure(repo, cli):
    repo.write_config([{"id": "bad", "argv": [PY, "-c", "import sys; print('o'); sys.exit(4)"]}])
    assert cli("collect") == 3
    [run_id] = repo.runs()
    rec = repo.record(run_id, "bad")
    assert rec["exit_code"] == 4
    assert repo.stdout(run_id, "bad") == b"o\n"


def test_missing_program(repo, cli):
    repo.write_config([{"id": "nope", "argv": ["pidoc-no-such-program-xyz"]}])
    assert cli("collect") == 3
    [run_id] = repo.runs()
    rec = repo.record(run_id, "nope")
    assert rec["exit_code"] is None
    assert rec["error"]


def test_commands_run_in_project_root(repo, cli):
    repo.write_config([{"id": "cwd", "argv": [PY, "-c", "import os; print(os.getcwd())"]}])
    assert cli("collect") == 0
    [run_id] = repo.runs()
    assert repo.stdout(run_id, "cwd").decode().strip() == str(repo.path.resolve())


def test_two_runs_same_time_get_distinct_ids(repo, cli):
    repo.write_config([{"id": "hello", "argv": [PY, "-c", "print(1)"]}])
    assert cli("collect") == 0
    assert cli("collect") == 0
    assert repo.runs() == ["20260102T030405Z", "20260102T030405Z-2"]


def test_bad_config(repo, cli):
    repo.config.write_text("[project\n", encoding="utf-8")
    assert cli("collect") == 2


def test_missing_config(repo, cli):
    assert cli("collect") == 2


def test_unknown_target_kind(repo, cli):
    repo.write_config([{"id": "a", "argv": [PY, "-c", "print(1)"]}])
    text = repo.config.read_text(encoding="utf-8").replace('kind = "local"', 'kind = "ftp"')
    repo.config.write_text(text, encoding="utf-8")
    assert cli("collect") == 2


def test_bad_command_id(repo, cli):
    repo.write_config([{"id": "../evil", "argv": [PY, "-c", "print(1)"]}])
    assert cli("collect") == 2


def test_module_entry_point(repo):
    repo.write_config([{"id": "v", "argv": [PY, "-c", "print('Python 3.99.1')"],
                        "facts": [{"key": "system.python_version", "extract": "regex",
                                   "pattern": r"Python (\S+)", "type": "string"}]}])
    env = dict(os.environ, PYTHONPATH=str(ROOT), PIDOC_NOW="2026-01-02T03:04:05Z")
    for sub in ("collect", "facts"):
        r = subprocess.run([sys.executable, "-m", "pidoc", sub],
                           cwd=repo.path, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    assert repo.facts()["system.python_version"]["value"] == "3.99.1"
