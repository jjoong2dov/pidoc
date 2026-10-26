"""12장 응용: notes·report·i18n-check."""

import json
import subprocess

from pidoc import config, notes

from conftest import make_exe, pidoc


def git(root, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                          cwd=root, check=True, capture_output=True, text=True).stdout


def make_history(root):
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "처음")
    git(root, "tag", "v0.1")
    for msg in ("scan: 경로 검사 추가", "web: /health 고침"):
        (root / "minimon/web.py").write_text((root / "minimon/web.py").read_text() + f"\n# {msg}\n")
        git(root, "commit", "-qam", msg)
    return git(root, "log", "--format=%h", "v0.1..HEAD").split()


# --- notes ---

def test_notes_facts_and_hash_check(miniproj, bindir, tmp_path, monkeypatch, capsys):
    shorts = make_history(miniproj)
    reply = tmp_path / "reply.md"
    reply.write_text(f"# 릴리스 노트 (v0.1..HEAD)\n\n## 고친 것\n\n- 웹 상태 주소 고침 ({shorts[0]})\n"
                     f"- 경로 검사 ({shorts[1]})\n- 지어낸 항목 (1a2b3c4)\n- facade 패턴 정리\n")
    make_exe(bindir, "claude", f'cat > /dev/null\ncat "{reply}"\n')
    assert pidoc("notes", "v0.1..HEAD", "--ai", "claude") == 1
    out = capsys.readouterr().out
    assert "[git] v0.1..HEAD: 커밋 2개" in out
    assert "docs/src/release-notes.md:7: [notes] 범위 밖 커밋 해시: 1a2b3c4" in out
    assert out.count("[notes]") == 1                    # facade 는 해시로 보지 않음
    data = json.loads((miniproj / "docs/facts/git.json").read_text())["facts"]
    assert data["git.count"]["value"] == 2
    assert data["git.commits"]["value"] == [f"{shorts[0]} web: /health 고침", f"{shorts[1]} scan: 경로 검사 추가"]
    prompt = next((miniproj / "docs/ai").iterdir()) / "prompt.txt"
    assert f"- {shorts[0]} web: /health 고침" in prompt.read_text()


def test_notes_check_only(miniproj, capsys):
    shorts = make_history(miniproj)
    notes = miniproj / "notes.md"
    notes.write_text(f"# 노트\n\n- 고침 ({shorts[0]})\n")
    assert pidoc("notes", "v0.1..HEAD", "--check", "notes.md") == 0
    notes.write_text(f"# 노트\n\n- 고침 ({shorts[0]})\n- 처음 ({git(miniproj, 'rev-parse', '--short', 'v0.1').strip()})\n")
    assert pidoc("notes", "v0.1..HEAD", "--check", "notes.md") == 1


def test_notes_all_digit_hash_is_not_a_number(miniproj):
    cfg = config.load(miniproj / "docs/pidoc.toml")
    commits = [{"hash": "8518830" + "a" * 33, "short": "8518830", "subject": "x", "date": ""}]
    assert notes.report_problems(cfg, miniproj / "n.md", "# 노트\n\n- 고침 (8518830)\n", commits) == 0


def test_notes_bad_range(miniproj, capsys):
    make_history(miniproj)
    assert pidoc("notes", "nope..HEAD", "--check", "x.md") == 2
    assert "git log 실패" in capsys.readouterr().err


# --- report ---

JUNIT = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="0" failures="1" skipped="1" tests="5" time="1.234">
<testcase classname="tests.test_a" name="test_ok" time="0.1"/>
<testcase classname="tests.test_a" name="test_bad" time="0.1"><failure message="assert 1 == 2"/></testcase>
<testcase classname="tests.test_b" name="test_skip" time="0"><skipped/></testcase>
<testcase classname="tests.test_b" name="test_x" time="0.1"/>
<testcase classname="tests.test_b" name="test_y" time="0.1"/>
</testsuite></testsuites>
"""


def test_report(miniproj):
    (miniproj / "junit.xml").write_text(JUNIT)
    assert pidoc("report", "junit.xml") == 0
    text = (miniproj / "docs/out/test-report.md").read_text()
    assert "- 시험 5개 중 통과 3개" in text
    assert "- 실패 1개, 오류 0개, 건너뜀 1개" in text
    assert "- 걸린 시간 1.2초" in text
    assert "- 실패한 시험: tests.test\\_a::test\\_bad" in text      # 본문 사실은 Markdown 이스케이프
    assert "`junit.xml`" in text
    f = json.loads((miniproj / "docs/facts/test.json").read_text())["facts"]
    assert f["test.passed"]["value"] == 3 and f["test.time"]["type"] == "float"


def test_report_no_failures_and_template(miniproj):
    (miniproj / "junit.xml").write_text(JUNIT.replace('failures="1"', 'failures="0"')
                                        .replace('<failure message="assert 1 == 2"/>', ""))
    (miniproj / "t.md").write_text("<!-- pidoc-target: test -->\n# 결과\n\n실패: {{fact:test.failed_cases|join}}\n"
                                   "{{fact:test.nope}}\n")
    assert pidoc("report", "junit.xml") == 0
    assert "- 실패한 시험: (없음)" in (miniproj / "docs/out/test-report.md").read_text()
    assert pidoc("report", "junit.xml", "--template", "t.md", "--out", "r.md") == 1   # 없는 사실


def test_report_bad_xml(miniproj, capsys):
    (miniproj / "junit.xml").write_text("<html></html>")
    assert pidoc("report", "junit.xml") == 2
    assert "JUnit XML 이 아닙니다" in capsys.readouterr().err


# --- i18n ---

KO = """\
# 빠른 시작

{{fact:pc:system.python_version}} 이상에서 `python3 -m minimon scan` 을 5초마다 돌립니다.
자세한 것은 [설정](ref.md#설정) 과 3장을 보세요.

```sh
python3 -m minimon scan
```
"""

EN = """\
# Quick start

Run `python3 -m minimon scan` every 5 seconds on {{fact:pc:system.python_version}} or later.
See [settings](ref.md#설정) and Chapter 3.

```sh
python3 -m minimon scan
```
"""


def test_i18n_same(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ko.md").write_text(KO)
    (tmp_path / "en.md").write_text(EN)
    assert pidoc("i18n-check", "ko.md", "en.md") == 0


def test_i18n_differences(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ko.md").write_text(KO)
    (tmp_path / "en.md").write_text(EN.replace("every 5 seconds", "every 10 seconds")
                                    .replace("{{fact:pc:system.python_version}}", "Python 3.12")
                                    .replace("ref.md#설정", "ref.md#settings")
                                    .replace("python3 -m minimon scan\n```", "python -m minimon scan\n```"))
    assert pidoc("i18n-check", "ko.md", "en.md") == 1
    out = capsys.readouterr().out
    assert "en.md:6: [i18n] 코드 블록이 원본(6줄)과 다릅니다" in out
    assert "자리표시자 '{{fact:pc:system.python_version}}' 가 번역본에 없습니다(원본 3줄)" in out
    assert "en.md:3: [i18n] 원본에 없는 숫자 '10'" in out
    assert "en.md:3: [i18n] 원본에 없는 숫자 '3.12'" in out
    assert "en.md:4: [i18n] 원본에 없는 링크 주소 'ref.md#settings'" in out
