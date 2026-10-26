"""시험 도우미: 가짜 대상 저장소, 가짜 실행 파일, 고정 시계."""

import os
import stat
import textwrap
from pathlib import Path

import pytest

from pidoc.cli import main

NOW = "2026-10-26T23:15:00+09:00"


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setenv("PIDOC_NOW", NOW)


@pytest.fixture
def bindir(tmp_path, monkeypatch):
    """PATH 맨 앞에 끼울 가짜 실행 파일 폴더."""
    path = tmp_path / "bin"
    path.mkdir()
    monkeypatch.setenv("PATH", f"{path}{os.pathsep}{os.environ['PATH']}")
    return path


def make_exe(folder, name, script):
    """#!/bin/sh 스크립트로 가짜 프로그램을 만든다."""
    exe = Path(folder) / name
    exe.write_text("#!/bin/sh\n" + textwrap.dedent(script).lstrip())
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return exe


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """docs/ 가 있는 빈 대상 저장소. write_config(text) 로 설정을 쓴다."""
    root = tmp_path / "proj"
    (root / "docs").mkdir(parents=True)
    monkeypatch.chdir(root)
    return root


def write_config(root, text):
    path = Path(root) / "docs" / "pidoc.toml"
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
    return path


def pidoc(*args):
    return main([str(a) for a in args])
