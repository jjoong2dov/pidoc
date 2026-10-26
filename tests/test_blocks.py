import os

import pytest

from conftest import PY

# 저장소 root 의 out.txt 를 그대로 찍는 명령(내용은 시험이 바꾼다)
CAT = [PY, "-c", "import sys; sys.stdout.write(open('out.txt', encoding='utf-8').read())"]

LINES = "".join(f"line {i}\n" for i in range(1, 11))


@pytest.fixture
def ready(repo, cli):
    repo.write_config([{"id": "boot", "argv": CAT}])
    (repo.path / "out.txt").write_text("hello\n", encoding="utf-8")
    (repo.path / "app.py").write_text(LINES, encoding="utf-8")
    (repo.docs / "src").mkdir()
    return repo


def src(repo, text, name="a.md"):
    (repo.docs / "src" / name).write_text(text, encoding="utf-8")


def out(repo, name="a.md"):
    p = repo.docs / "out" / name
    return p.read_text(encoding="utf-8") if p.exists() else None


def collect(repo, cli, monkeypatch, text, now):
    (repo.path / "out.txt").write_text(text, encoding="utf-8")
    monkeypatch.setenv("PIDOC_NOW", now)
    assert cli("collect") == 0


# --- pidoc-quote ---

def test_quote_fills_and_checks(ready, cli, capsys):
    src(ready, "앞\n```python pidoc-quote=app.py#L2-L4\n옛 내용\n```\n뒤\n")
    assert cli("render") == 0
    assert out(ready) == "앞\n```python pidoc-quote=app.py#L2-L4\nline 2\nline 3\nline 4\n```\n뒤\n"
    assert cli("check", "--only", "quote") == 0

    # 파일이 바뀌면 다시 render 할 때까지 check 가 잡는다
    (ready.path / "app.py").write_text(LINES.replace("line 3", "line three"), encoding="utf-8")
    capsys.readouterr()
    assert cli("check", "--only", "quote") == 1
    err = capsys.readouterr().err
    assert "out/a.md:2:" in err and "pidoc-quote=app.py#L2-L4" in err and "line three" in err
    assert cli("render") == 0
    assert cli("check", "--only", "quote") == 0


def test_quote_single_line_and_subdir(ready, cli):
    (ready.path / "pkg").mkdir()
    (ready.path / "pkg" / "m.py").write_text("a\nb\n", encoding="utf-8")
    src(ready, "```python pidoc-quote=pkg/m.py#L2-L2\n```\n")
    assert cli("render") == 0
    assert out(ready) == "```python pidoc-quote=pkg/m.py#L2-L2\nb\n```\n"


@pytest.mark.parametrize("ref", [
    "../outside.txt#L1-L1",
    "/etc/hosts#L1-L1",
    "docs/../../outside.txt#L1-L1",
    "link.txt#L1-L1",          # 프로젝트 밖을 가리키는 심볼릭 링크
])
def test_quote_outside_project_is_error(ready, cli, capsys, ref):
    outside = ready.path.parent / "outside.txt"
    outside.write_text("밖\n", encoding="utf-8")
    os.symlink(outside, ready.path / "link.txt")
    src(ready, f"```text pidoc-quote={ref}\n```\n")
    assert cli("render") == 1
    assert out(ready) is None
    err = capsys.readouterr().err
    assert "src/a.md:1:" in err and "프로젝트 밖" in err
    assert cli("check", "--only", "quote") == 1
    assert "프로젝트 밖" in capsys.readouterr().err


@pytest.mark.parametrize("ref, why", [
    ("app.py", "#La-Lb"),
    ("app.py#L4-L2", "범위"),
    ("app.py#L0-L1", "범위"),
    ("app.py#L9-L11", "범위"),
    ("nope.py#L1-L1", "파일이 없음"),
    ("#L1-L1", "경로"),
])
def test_quote_bad_ref(ready, cli, capsys, ref, why):
    src(ready, f"```python pidoc-quote={ref}\n```\n")
    assert cli("render") == 1
    assert why in capsys.readouterr().err


def test_quote_unclosed_block(ready, cli, capsys):
    src(ready, "```python pidoc-quote=app.py#L1-L1\n끝\n")
    assert cli("render") == 1
    assert "닫히지 않은" in capsys.readouterr().err


def test_quote_with_backtick_fence_inside(ready, cli):
    # 인용하는 파일에 ``` 와 ```` 가 들어 있다
    (ready.path / "doc.md").write_text("예:\n```\ncode\n  ````\n끝\n", encoding="utf-8")
    src(ready, "```markdown pidoc-quote=doc.md#L1-L5\n```\n뒤\n")
    assert cli("render") == 0
    text = out(ready)
    assert text == ("`````markdown pidoc-quote=doc.md#L1-L5\n"
                    "예:\n```\ncode\n  ````\n끝\n"
                    "`````\n뒤\n")
    # 울타리 해석으로도 블록 하나, 그 뒤 '뒤' 는 블록 밖이다
    from pidoc.blocks import Block, split
    parts = [p for _, p in split(text)]
    assert [type(p) for p in parts] == [Block, str] and parts[1] == "뒤\n"
    assert parts[0].body == "예:\n```\ncode\n  ````\n끝\n"
    assert cli("check", "--only", "quote") == 0


def test_quote_with_tilde_fence(ready, cli):
    (ready.path / "t.txt").write_text("~~~\n```\n", encoding="utf-8")
    src(ready, "~~~text pidoc-quote=t.txt#L1-L2\n~~~\n")
    assert cli("render") == 0
    assert out(ready) == "~~~~text pidoc-quote=t.txt#L1-L2\n~~~\n```\n~~~~\n"
    assert cli("check", "--only", "quote") == 0


def test_quoted_placeholder_left_alone(ready, cli):
    # 인용한 내용 속 {{fact:...}} 는 채우지 않는다
    (ready.path / "t.txt").write_text("x = '{{fact:no.such}}'\n", encoding="utf-8")
    src(ready, "```python pidoc-quote=t.txt#L1-L1\n```\n")
    assert cli("render") == 0
    assert "{{fact:no.such}}" in out(ready)


def test_directive_inside_other_fence_is_text(ready, cli):
    # 더 긴 울타리 안의 예시는 그냥 코드다
    text = "````markdown\n```python pidoc-quote=../x#L1-L1\n```\n````\n"
    src(ready, text)
    assert cli("render") == 0
    assert out(ready) == text
    assert cli("check", "--only", "quote", "run") == 0


def test_indented_block(ready, cli):
    (ready.path / "t.txt").write_text("a\n  b\n", encoding="utf-8")
    src(ready, "1. 단계\n\n   ```text pidoc-quote=t.txt#L1-L2\n   ```\n")
    assert cli("render") == 0
    assert out(ready) == "1. 단계\n\n   ```text pidoc-quote=t.txt#L1-L2\n   a\n     b\n   ```\n"
    assert cli("check", "--only", "quote") == 0


def test_check_needs_render(ready, cli, capsys):
    src(ready, "```python pidoc-quote=app.py#L1-L1\n```\n")
    assert cli("check", "--only", "quote") == 1
    assert "render" in capsys.readouterr().err
    assert cli("render") == 0
    # src 에 블록을 더하고 render 를 안 했다
    src(ready, "```python pidoc-quote=app.py#L1-L1\n```\n```python pidoc-quote=app.py#L2-L2\n```\n")
    assert cli("check", "--only", "quote") == 1
    assert "render" in capsys.readouterr().err


# --- pidoc-run ---

def test_run_fills_latest_stdout(ready, cli, monkeypatch):
    collect(ready, cli, monkeypatch, "first\n", "2026-01-02T03:04:05Z")
    collect(ready, cli, monkeypatch, "second\n", "2026-01-03T03:04:05Z")
    src(ready, "```console pidoc-run=boot\n```\n")
    assert cli("render") == 0
    assert out(ready) == "```console pidoc-run=boot\nsecond\n```\n"
    assert cli("check", "--only", "run") == 0


def test_run_output_without_newline(ready, cli, monkeypatch):
    collect(ready, cli, monkeypatch, "no newline", "2026-01-02T03:04:05Z")
    src(ready, "```console pidoc-run=boot\n```\n")
    assert cli("render") == 0
    assert out(ready) == "```console pidoc-run=boot\nno newline\n```\n"
    assert cli("check", "--only", "run") == 0


def test_run_with_backticks_in_output(ready, cli, monkeypatch):
    collect(ready, cli, monkeypatch, "```\n````x\n", "2026-01-02T03:04:05Z")
    src(ready, "```console pidoc-run=boot\n```\n")
    assert cli("render") == 0
    assert out(ready) == "`````console pidoc-run=boot\n```\n````x\n`````\n"
    assert cli("check", "--only", "run") == 0


def test_run_changed_output_caught(ready, cli, monkeypatch, capsys):
    collect(ready, cli, monkeypatch, "kernel 6.1\n", "2026-01-02T03:04:05Z")
    src(ready, "```console pidoc-run=boot\n```\n")
    assert cli("render") == 0
    collect(ready, cli, monkeypatch, "kernel 6.6\n", "2026-01-03T03:04:05Z")
    capsys.readouterr()
    assert cli("check", "--only", "run") == 1
    err = capsys.readouterr().err
    assert "out/a.md:1:" in err and "pidoc-run=boot" in err and "kernel 6.6" in err


BOOT1 = "booted 2026-01-02T03:04:05Z on pi4.local\nclock 03:04:05\nkernel 6.1\n"
BOOT2 = "booted 2026-01-03T09:10:11Z on pi5.local\nclock 09:10:11\nkernel 6.1\n"


def mask_cfg(repo, **kw):
    repo.write_config([{"id": "boot", "argv": CAT, **kw}])


def test_run_time_and_host_unmasked_fails(ready, cli, monkeypatch):
    mask_cfg(ready)
    collect(ready, cli, monkeypatch, BOOT1, "2026-01-02T03:04:05Z")
    src(ready, "```console pidoc-run=boot\n```\n")
    assert cli("render") == 0
    collect(ready, cli, monkeypatch, BOOT2, "2026-01-03T09:10:11Z")
    # 시각·호스트 이름만 달라도 가리지 않으면 실패한다
    assert cli("check", "--only", "run") == 1


def test_run_time_and_host_masked_passes(ready, cli, monkeypatch):
    mask_cfg(ready, mask=["time", "host"])
    collect(ready, cli, monkeypatch, BOOT1, "2026-01-02T03:04:05Z")
    src(ready, "```console pidoc-run=boot\n```\n")
    assert cli("render") == 0
    collect(ready, cli, monkeypatch, BOOT2, "2026-01-03T09:10:11Z")
    assert cli("check", "--only", "run") == 0
    # 가린 것 말고 다른 곳이 바뀌면 여전히 실패한다
    collect(ready, cli, monkeypatch, BOOT2.replace("6.1", "6.6"), "2026-01-04T00:00:00Z")
    assert cli("check", "--only", "run") == 1


def test_run_only_time_masked_fails_on_host(ready, cli, monkeypatch):
    mask_cfg(ready, mask=["time"])
    collect(ready, cli, monkeypatch, BOOT1, "2026-01-02T03:04:05Z")
    src(ready, "```console pidoc-run=boot\n```\n")
    assert cli("render") == 0
    collect(ready, cli, monkeypatch, BOOT2, "2026-01-03T09:10:11Z")
    assert cli("check", "--only", "run") == 1


def test_run_mask_regex(ready, cli, monkeypatch):
    mask_cfg(ready, mask_regex=[r"up \d+ min"])
    collect(ready, cli, monkeypatch, "up 3 min\nok\n", "2026-01-02T03:04:05Z")
    src(ready, "```console pidoc-run=boot\n```\n")
    assert cli("render") == 0
    collect(ready, cli, monkeypatch, "up 17 min\nok\n", "2026-01-03T03:04:05Z")
    assert cli("check", "--only", "run") == 0


@pytest.mark.parametrize("kw, why", [
    ({"mask": ["date"]}, "mask"),
    ({"mask_regex": ["("]}, "mask_regex"),
])
def test_run_bad_mask_config(ready, cli, kw, why, capsys):
    mask_cfg(ready, **kw)
    assert cli("check", "--only", "run") == 2
    assert why in capsys.readouterr().err


def test_run_date_command_style_masked(ready, cli, monkeypatch):
    mask_cfg(ready, mask=["time"])
    collect(ready, cli, monkeypatch, "Fri Jan  2 03:04:05 UTC 2026\n", "2026-01-02T03:04:05Z")
    src(ready, "```console pidoc-run=boot\n```\n")
    assert cli("render") == 0
    collect(ready, cli, monkeypatch, "Sat Feb 14 23:59:00 UTC 2026\n", "2026-01-03T03:04:05Z")
    assert cli("check", "--only", "run") == 0


def test_run_errors(ready, cli, monkeypatch, capsys):
    src(ready, "```console pidoc-run=boot\n```\n")
    assert cli("render") == 1
    assert "collect" in capsys.readouterr().err   # 증거가 없음
    src(ready, "```console pidoc-run=nope\n```\n")
    assert cli("render") == 1
    assert "없는 명령" in capsys.readouterr().err


def test_run_latest_failed(repo, cli, capsys):
    repo.write_config([{"id": "boot", "argv": [PY, "-c", "import sys; sys.exit(1)"]}])
    assert cli("collect") == 3
    (repo.docs / "src").mkdir()
    src(repo, "```console pidoc-run=boot\n```\n")
    capsys.readouterr()
    assert cli("render") == 1
    assert "실패" in capsys.readouterr().err


def test_run_tampered_evidence(ready, cli, monkeypatch, capsys):
    collect(ready, cli, monkeypatch, "hello\n", "2026-01-02T03:04:05Z")
    [run_id] = ready.runs()
    (ready.docs / "evidence" / "runs" / run_id / "pc" / "boot.stdout").write_bytes(b"forged\n")
    src(ready, "```console pidoc-run=boot\n```\n")
    capsys.readouterr()
    assert cli("render") == 1
    assert "sha256" in capsys.readouterr().err


def test_run_multi_target_needs_target(repo, cli, capsys):
    repo.write_config([{"id": "boot", "argv": [PY, "-c", "print('x')"], "targets": ["pc", "pc2"]}],
                      extra_targets='[targets.pc2]\nkind = "local"\n')
    assert cli("collect") == 0
    (repo.docs / "src").mkdir()
    src(repo, "```console pidoc-run=boot\n```\n")
    capsys.readouterr()
    assert cli("render") == 1
    assert "대상" in capsys.readouterr().err
    src(repo, "```console pidoc-run=pc2:boot\n```\n")
    assert cli("render") == 0
    assert out(repo) == "```console pidoc-run=pc2:boot\nx\n```\n"


def test_placeholders_outside_blocks_still_work(repo, cli, capsys):
    repo.write_config([{"id": "ver", "argv": [PY, "-c", "print('Version 1.2.3')"],
                        "facts": [{"key": "app.version", "extract": "regex",
                                   "pattern": r"Version (\S+)"}]}])
    assert cli("collect") == 0
    assert cli("facts") == 0
    (repo.docs / "src").mkdir()
    body = "첫\n```console pidoc-run=ver\n{{fact:no.such}}\n```\n버전 {{fact:app.version}}\n"
    src(repo, body + "틀림 {{fact:no.such}}\n")
    capsys.readouterr()
    assert cli("render") == 1
    # 블록 안 옛 내용은 보지 않고, 오류 줄 번호는 원본 기준이다
    err = capsys.readouterr().err
    assert "a.md:6:" in err and "a.md:3:" not in err
    assert cli("check", "--only", "facts") == 1
    src(repo, body)
    assert cli("render") == 0
    assert out(repo) == "첫\n```console pidoc-run=ver\nVersion 1.2.3\n```\n버전 1.2.3\n"
    # secrets 는 뺀다: 증거 argv 의 파이썬 경로가 시험 기계의 홈 아래일 수 있다
    assert cli("check", "--only", "facts", "numbers", "quote", "run") == 0

