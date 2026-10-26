import json
import os
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
                     env_allow=("PATH", "HOME", "LANG"), env_set=None):
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
                'targets = ["pc"]',
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
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("PIDOC_NOW", "2026-01-02T03:04:05Z")
    return Repo(tmp_path / "target")


@pytest.fixture
def cli(repo):
    from pidoc.cli import main

    def run(*args):
        return main([args[0], "--config", str(repo.config), *args[1:]])

    return run
