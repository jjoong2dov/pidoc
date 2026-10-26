import json
import os

import pytest

from conftest import PY

FAKE_AI = """#!{py}
import json, os, sys, time
name = os.path.basename(sys.argv[0])
data = sys.stdin.buffer.read()
with open(os.path.join({log!r}, name + ".prompt"), "wb") as f:
    f.write(data)
with open(os.path.join({log!r}, name + ".argv"), "w", encoding="utf-8") as f:
    json.dump(sys.argv[1:], f)
time.sleep(float(os.environ.get("FAKE_AI_SLEEP", "0")))
sys.stderr.write("가짜 stderr\\n")
with open({reply!r}, "rb") as f:
    sys.stdout.buffer.write(f.read())
sys.exit(int(os.environ.get("FAKE_AI_EXIT", "0")))
"""


class FakeAi:
    def __init__(self, log, reply):
        self.log = log
        self.reply_file = reply

    def reply(self, text):
        self.reply_file.write_text(text, encoding="utf-8")

    def prompt(self, tool):
        p = self.log / f"{tool}.prompt"
        return p.read_text(encoding="utf-8") if p.exists() else None

    def argv(self, tool):
        return json.loads((self.log / f"{tool}.argv").read_text(encoding="utf-8"))


@pytest.fixture
def fake_ai(tmp_path, monkeypatch):
    """PATH 앞에 두는 가짜 claude·codex. stdin 으로 받은 프롬프트를 파일에 남긴다."""
    bindir = tmp_path / "aibin"
    bindir.mkdir()
    log = tmp_path / "ai-calls"
    log.mkdir()
    reply = tmp_path / "ai-reply.md"
    reply.write_text("# 초안\n", encoding="utf-8")
    for tool in ("claude", "codex"):
        s = bindir / tool
        s.write_text(FAKE_AI.format(py=PY, log=str(log), reply=str(reply)), encoding="utf-8")
        s.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    return FakeAi(log, reply)


@pytest.fixture
def setup(repo):
    """설정·사실·틀을 둔 저장소."""
    repo.write_config([], extra_targets='[targets.pi]\nkind = "local"\nalias = "pi"\n')
    facts = repo.docs / "facts"
    facts.mkdir()
    base = {"run": "20260101T000000Z", "command": "c", "extract": "regex",
            "source_sha256": "0" * 64, "collected_at": "2026-01-01T00:00:00Z"}
    (facts / "pc.json").write_text(json.dumps({
        "system.python_version": {"value": "3.11.4", "type": "string", **base},
        "app.workers": {"value": 4, "type": "int", **base},
    }), encoding="utf-8")
    (facts / "pi.json").write_text(json.dumps({
        "os.modules": {"value": ["i2c", "spi"], "type": "list", **base},
    }), encoding="utf-8")
    src = repo.docs / "src"
    src.mkdir()
    tpl = src / "install.md"
    tpl.write_text("# 설치\n\n## 준비물\n\n## 실행\n", encoding="utf-8")
    return tpl


def ai_dirs(repo):
    d = repo.docs / "ai"
    return sorted(p for p in d.iterdir()) if d.exists() else []


def test_none_saves_prompt_only(repo, cli, setup, fake_ai, tmp_path):
    out = tmp_path / "draft.md"
    assert cli("draft", str(setup), "--out", str(out), "--ai", "none") == 0
    assert not out.exists()
    assert fake_ai.prompt("claude") is None and fake_ai.prompt("codex") is None
    [d] = ai_dirs(repo)
    assert d.name == "20260102T030405Z-draft"
    assert sorted(p.name for p in d.iterdir()) == ["meta.json", "prompt.txt"]
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    assert meta["tool"] == "none"
    assert meta["argv"] is None
    assert meta["exit_code"] is None
    assert meta["template"] == "docs/src/install.md"
    assert meta["facts"] == 3


def test_prompt_has_facts_and_template(repo, cli, setup, fake_ai):
    assert cli("draft", str(setup), "--ai", "none") == 0
    [d] = ai_dirs(repo)
    prompt = (d / "prompt.txt").read_text(encoding="utf-8")
    # 대상은 설정 순서, 키는 정렬. 값은 JSON 으로.
    lines = [ln for ln in prompt.splitlines() if ln.startswith(("pc:", "pi:"))]
    assert lines == [
        'pc:app.workers = 4  (int)',
        'pc:system.python_version = "3.11.4"  (string)',
        'pi:os.modules = ["i2c", "spi"]  (list)',
    ]
    assert "{{fact:대상:키}}" in prompt
    assert prompt.endswith("# 설치\n\n## 준비물\n\n## 실행\n")


def test_no_facts(repo, cli, setup):
    for p in (repo.docs / "facts").iterdir():
        p.unlink()
    assert cli("draft", str(setup), "--ai", "none") == 0
    [d] = ai_dirs(repo)
    assert "(사실 없음)" in (d / "prompt.txt").read_text(encoding="utf-8")


def test_claude_gets_prompt_on_stdin(repo, cli, setup, fake_ai, tmp_path):
    fake_ai.reply("# 설치\n\n파이썬 {{fact:pc:system.python_version}} 이 필요하다.\n")
    out = tmp_path / "draft.md"
    assert cli("draft", str(setup), "--out", str(out), "--ai", "claude") == 0
    [d] = ai_dirs(repo)
    prompt = (d / "prompt.txt").read_text(encoding="utf-8")
    assert fake_ai.prompt("claude") == prompt
    assert fake_ai.argv("claude") == ["-p"]
    assert out.read_text(encoding="utf-8") == "# 설치\n\n파이썬 {{fact:pc:system.python_version}} 이 필요하다.\n"
    assert (d / "raw.txt").read_bytes() == out.read_bytes()
    assert (d / "stderr.txt").read_text(encoding="utf-8") == "가짜 stderr\n"
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    assert meta["tool"] == "claude"
    assert meta["argv"] == ["claude", "-p"]
    assert meta["exit_code"] == 0
    assert meta["ok"] is True
    assert meta["started_at"] == "2026-01-02T03:04:05Z"
    assert meta["numeric_lines"] == []


def test_codex_exec_stdin(repo, cli, setup, fake_ai, tmp_path):
    out = tmp_path / "draft.md"
    assert cli("draft", str(setup), "--out", str(out), "--ai", "codex") == 0
    assert fake_ai.argv("codex") == ["exec", "-"]
    [d] = ai_dirs(repo)
    assert fake_ai.prompt("codex") == (d / "prompt.txt").read_text(encoding="utf-8")
    assert fake_ai.prompt("claude") is None
    assert out.read_text(encoding="utf-8") == "# 초안\n"


def test_numeric_lines_shown(repo, cli, setup, fake_ai, tmp_path, capsys):
    fake_ai.reply("# 설치\n\n워커는 {{fact:pc:app.workers}} 개.\n포트 8080 을 연다.\n\n버전 3.11\n")
    out = tmp_path / "draft.md"
    assert cli("draft", str(setup), "--out", str(out), "--ai", "claude") == 0
    printed = capsys.readouterr().out
    assert "(기록: docs/ai/20260102T030405Z-draft)" in printed
    assert "숫자 리터럴이 있는 줄 2개" in printed
    assert "  4: 포트 8080 을 연다." in printed
    assert "  6: 버전 3.11" in printed
    assert "  3:" not in printed
    [d] = ai_dirs(repo)
    assert json.loads((d / "meta.json").read_text(encoding="utf-8"))["numeric_lines"] == [4, 6]


def test_ai_failure_writes_no_out(repo, cli, setup, fake_ai, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_AI_EXIT", "1")
    fake_ai.reply("부분 응답\n")
    out = tmp_path / "draft.md"
    assert cli("draft", str(setup), "--out", str(out), "--ai", "claude") == 3
    assert not out.exists()
    [d] = ai_dirs(repo)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    assert meta["exit_code"] == 1
    assert meta["ok"] is False
    assert (d / "raw.txt").read_text(encoding="utf-8") == "부분 응답\n"


def test_ai_not_found(repo, cli, setup, tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    out = tmp_path / "draft.md"
    assert cli("draft", str(setup), "--out", str(out), "--ai", "claude") == 3
    assert not out.exists()
    [d] = ai_dirs(repo)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    assert meta["exit_code"] is None
    assert "실행하지 못함" in meta["error"]


def test_ai_timeout(repo, cli, setup, fake_ai, tmp_path, monkeypatch):
    from pidoc import draft
    monkeypatch.setattr(draft, "AI_TIMEOUT_S", 0.5)
    monkeypatch.setenv("FAKE_AI_SLEEP", "10")
    out = tmp_path / "draft.md"
    assert cli("draft", str(setup), "--out", str(out), "--ai", "claude") == 3
    assert not out.exists()
    [d] = ai_dirs(repo)
    assert json.loads((d / "meta.json").read_text(encoding="utf-8"))["timed_out"] is True


def test_two_drafts_same_time(repo, cli, setup):
    assert cli("draft", str(setup), "--ai", "none") == 0
    assert cli("draft", str(setup), "--ai", "none") == 0
    assert [d.name for d in ai_dirs(repo)] == ["20260102T030405Z-draft", "20260102T030405Z-draft-2"]


def test_missing_template(repo, cli, setup, tmp_path):
    assert cli("draft", str(tmp_path / "nope.md"), "--ai", "none") == 2
    assert ai_dirs(repo) == []


def test_out_required_for_ai(repo, cli, setup, fake_ai):
    assert cli("draft", str(setup), "--ai", "claude") == 2
    assert fake_ai.prompt("claude") is None
    assert ai_dirs(repo) == []
