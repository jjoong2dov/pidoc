import json
import os
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PY = sys.executable


def toml_str(s):
    # TOML 기본 문자열로 감싼다
    return json.dumps(s)


def toml_argv(argv):
    return "[" + ", ".join(toml_str(a) for a in argv) + "]"


class Repo:
    """tmp_path 안의 가짜 대상 저장소."""

    def __init__(self, path):
        self.path = path
        self.docs = path / "docs"
        self.docs.mkdir(parents=True)
        self.config = self.docs / "pidoc.toml"

    def write_config(self, commands, timeout_s=20, max_output=1048576,
                     env_allow=("PATH", "HOME", "LANG"), env_set=None, extra_targets=""):
        env_set = env_set or {"LC_ALL": "C.UTF-8"}
        lines = [
            "[project]",
            'name = "demo"',
            'root = ".."',
            "",
            "[targets.pc]",
            'kind = "local"',
            'alias = "devpc"',
            "",
            extra_targets,
            "",
            "[collect]",
            f"timeout_s = {timeout_s}",
            f"max_output = {max_output}",
            "env_allow = [" + ", ".join(toml_str(e) for e in env_allow) + "]",
            "env_set = { " + ", ".join(f"{k} = {toml_str(v)}" for k, v in env_set.items()) + " }",
            "",
        ]
        for c in commands:
            lines += [
                "[[command]]",
                f"id = {toml_str(c['id'])}",
                f"argv = {toml_argv(c['argv'])}",
                f"targets = {toml_argv(c.get('targets', ['pc']))}",
            ]
            for f in c.get("facts", []):
                lines.append("  [[command.fact]]")
                for k, v in f.items():
                    val = v if isinstance(v, int) and not isinstance(v, bool) else toml_str(v)
                    lines.append(f"  {k} = {val}")
            lines.append("")
        self.config.write_text("\n".join(lines), encoding="utf-8")

    def runs(self):
        d = self.docs / "evidence" / "runs"
        return sorted(p.name for p in d.iterdir()) if d.exists() else []

    def record(self, run_id, cmd_id, target="pc"):
        p = self.docs / "evidence" / "runs" / run_id / target / f"{cmd_id}.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def stdout(self, run_id, cmd_id, target="pc"):
        return (self.docs / "evidence" / "runs" / run_id / target / f"{cmd_id}.stdout").read_bytes()

    def facts(self, target="pc"):
        p = self.docs / "facts" / f"{target}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@pytest.fixture
def home(tmp_path, monkeypatch):
    # 진짜 홈·호스트 이름이 시험에 섞이지 않게 가짜로 바꾼다
    h = tmp_path / "home" / "user"
    h.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setattr(socket, "gethostname", lambda: "devbox.example")
    return h


@pytest.fixture
def repo(tmp_path, monkeypatch, home):
    monkeypatch.setenv("PIDOC_NOW", "2026-01-02T03:04:05Z")
    return Repo(tmp_path / "target")


FAKE_SSH = """#!{py}
import json, subprocess, sys
with open({log!r}, "a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
# 원격 셸 흉내: 마지막 인자(원격 명령 한 줄)를 sh 로 돌린다
sys.exit(subprocess.run(["/bin/sh", "-c", sys.argv[-1]]).returncode)
"""


class FakeSsh:
    def __init__(self, log):
        self.log = log

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(ln) for ln in self.log.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def fake_ssh(tmp_path, monkeypatch):
    """PATH 앞에 두는 가짜 ssh. 받은 argv 를 파일에 남긴다."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "ssh-calls.jsonl"
    script = bindir / "ssh"
    script.write_text(FAKE_SSH.format(py=PY, log=str(log)), encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    return FakeSsh(log)


def ssh_target(name="pi", host="pi@raspi.example", allow=("printf", "false"), alias="pi"):
    lines = [f"[targets.{name}]", 'kind = "ssh"', f"host = {toml_str(host)}",
             f"alias = {toml_str(alias)}", 'known_hosts = "known_hosts"']
    if allow is not None:
        lines.append(f"allow_programs = {toml_argv(list(allow))}")
    return "\n".join(lines) + "\n"


@pytest.fixture
def cli(repo):
    from pidoc.cli import main

    def run(*args):
        return main([args[0], "--config", str(repo.config), *args[1:]])

    return run
