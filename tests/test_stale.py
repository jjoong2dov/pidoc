import json

import pytest

from conftest import PY

# 저장소 root 의 temp.txt 를 읽어 찍는 명령(값은 시험이 바꾼다)
TEMP = {"id": "temp",
        "argv": [PY, "-c", "import sys; sys.stdout.write(open('temp.txt').read())"],
        "facts": [{"key": "cpu.temp", "extract": "regex", "type": "float",
                   "pattern": r"t=([\d.]+)"}]}
APP = "def main():\n    return 1\n"


@pytest.fixture
def ready(repo, cli):
    repo.write_config([TEMP])
    (repo.path / "temp.txt").write_text("t=48.25\n", encoding="utf-8")
    (repo.path / "app.py").write_text(APP, encoding="utf-8")
    assert cli("collect") == 0
    assert cli("facts") == 0
    src = repo.docs / "src"
    src.mkdir()
    (src / "code.md").write_text("```python pidoc-quote=app.py#L1-L2\n```\n", encoding="utf-8")
    (src / "temp.md").write_text("온도 {{fact:cpu.temp}}\n", encoding="utf-8")
    (src / "plain.md").write_text("그냥 글\n", encoding="utf-8")
    assert cli("render") == 0
    return repo


def recollect(repo, cli, monkeypatch, text, now):
    (repo.path / "temp.txt").write_text(text, encoding="utf-8")
    monkeypatch.setenv("PIDOC_NOW", now)
    assert cli("collect") == 0
    assert cli("facts") == 0


def test_render_writes_deps(ready):
    deps = json.loads((ready.docs / "out" / ".deps.json").read_text(encoding="utf-8"))
    assert set(deps) == {"code.md", "temp.md", "plain.md"}
    assert list(deps["code.md"]["files"]) == ["app.py"]
    assert list(deps["temp.md"]["facts"]) == ["pc:cpu.temp"]
    assert deps["plain.md"]["files"] == {} and deps["plain.md"]["facts"] == {}


def test_fresh_after_render(ready, cli, capsys):
    capsys.readouterr()
    assert cli("stale") == 0
    assert "다시 볼 문서 0개" in capsys.readouterr().out


def test_source_file_changed(ready, cli, capsys):
    (ready.path / "app.py").write_text(APP.replace("1", "2"), encoding="utf-8")
    capsys.readouterr()
    assert cli("stale") == 1
    out = capsys.readouterr().out
    assert "out/code.md" in out and "파일 app.py 가 바뀜" in out
    assert "temp.md" not in out and "plain.md" not in out
    # 다시 렌더하면 풀린다
    assert cli("render") == 0
    assert cli("stale") == 0


def test_source_file_removed(ready, cli, capsys):
    (ready.path / "app.py").unlink()
    capsys.readouterr()
    assert cli("stale") == 1
    assert "파일 app.py 가 없어짐" in capsys.readouterr().out


def test_fact_value_changed(ready, cli, capsys, monkeypatch):
    recollect(ready, cli, monkeypatch, "t=51.0\n", "2026-01-03T00:00:00Z")
    capsys.readouterr()
    assert cli("stale") == 1
    out = capsys.readouterr().out
    assert "out/temp.md" in out and "사실 pc:cpu.temp 값이 바뀜" in out
    assert "code.md" not in out
    assert cli("render") == 0
    assert cli("stale") == 0


def test_same_value_recollected_is_not_stale(ready, cli, monkeypatch):
    # 다시 모아 run·시각은 바뀌어도 값이 같으면 다시 볼 필요가 없다
    recollect(ready, cli, monkeypatch, "t=48.25\n", "2026-01-03T00:00:00Z")
    assert cli("stale") == 0


def test_fact_removed(ready, cli, capsys):
    (ready.docs / "facts" / "pc.json").write_text("{}", encoding="utf-8")
    capsys.readouterr()
    assert cli("stale") == 1
    assert "사실 pc:cpu.temp 가 없어짐" in capsys.readouterr().out


def test_src_doc_changed_or_new(ready, cli, capsys):
    (ready.docs / "src" / "plain.md").write_text("고친 글\n", encoding="utf-8")
    (ready.docs / "src" / "new.md").write_text("새 글\n", encoding="utf-8")
    capsys.readouterr()
    assert cli("stale") == 1
    out = capsys.readouterr().out
    assert "out/plain.md" in out and "원본 문서가 바뀜" in out
    assert "out/new.md" in out and "렌더 기록에 없음" in out
    assert "다시 볼 문서 2개" in out


def test_no_deps_file(ready, cli, capsys):
    (ready.docs / "out" / ".deps.json").unlink()
    assert cli("stale") == 2
    assert "pidoc render" in capsys.readouterr().err


def test_failed_render_keeps_old_deps(ready, cli):
    (ready.path / "app.py").write_text(APP.replace("1", "2"), encoding="utf-8")
    (ready.docs / "src" / "bad.md").write_text("{{fact:no.such}}\n", encoding="utf-8")
    assert cli("render") == 1
    # 결과를 안 썼으니 옛 기록 그대로 → 여전히 낡음
    assert cli("stale") == 1
