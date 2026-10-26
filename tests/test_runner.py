import sys

from pidoc import runner

from conftest import make_exe

PY = sys.executable


def test_no_shell_interpretation():
    r = runner.run(["echo", "$HOME; ls | wc"], timeout=5)
    assert r.ok()
    assert r.stdout == b"$HOME; ls | wc\n"


def test_exit_code_and_stderr():
    r = runner.run([PY, "-c", "import sys; sys.stderr.write('나빠'); sys.exit(4)"], timeout=10)
    assert r.exit == 4 and not r.ok()
    assert r.ok(ok_exit=[0, 4])
    assert r.stderr == "나빠".encode()


def test_timeout_kills_process_group(tmp_path):
    exe = make_exe(tmp_path, "slow", "sleep 30 &\nsleep 30\n")
    r = runner.run([str(exe)], timeout=0.5)
    assert r.timed_out and not r.ok()
    assert r.duration_ms < 10000


def test_output_limit_truncates():
    r = runner.run([PY, "-c", "print('x' * 100000)"], timeout=10, max_output=100)
    assert r.stdout == b"x" * 100
    assert r.stdout_truncated and r.ok()


def test_raw_bytes_kept():
    r = runner.run([PY, "-c", "import sys; sys.stdout.buffer.write(b'\\xff\\xfe\\r\\n')"], timeout=10)
    assert r.stdout == b"\xff\xfe\r\n"


def test_env_allow_list(monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN", "abc")
    env = runner.build_env(["PATH"], {"LC_ALL": "C.UTF-8"})
    assert "SECRET_TOKEN" not in env and env["LC_ALL"] == "C.UTF-8"
    r = runner.run([PY, "-c", "import os; print(os.environ.get('SECRET_TOKEN'), os.environ['LC_ALL'])"],
                   env=env, timeout=10)
    assert r.stdout == b"None C.UTF-8\n"


def test_missing_program():
    r = runner.run(["no-such-program-pidoc"], timeout=5)
    assert r.exit is None and "실행하지 못했습니다" in r.error


def test_missing_cwd(tmp_path):
    r = runner.run(["true"], cwd=tmp_path / "nope", timeout=5)
    assert "작업 폴더가 없습니다" in r.error
