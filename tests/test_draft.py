import json

from conftest import make_exe, pidoc

TEMPLATE = "# 빠른 시작\n\n## 설치\n\n## 실행\n"

GOOD = """\
```markdown
# 빠른 시작

## 설치

파이썬 {{fact:pc:system.python_version}} 이상이 필요합니다.

## 실행

```console pidoc-run=scan target=pc
```
```
"""

# AI 가 받은 stdin 과 argv 를 파일에 남기고, 정해 둔 응답을 낸다
FAKE = """\
cat > "$AI_LOG.stdin"
printf '%s\\n' "$@" > "$AI_LOG.argv"
cat "$AI_REPLY"
"""


def setup(miniproj, bindir, tmp_path, monkeypatch, reply, name="claude"):
    (miniproj / "tmpl.md").write_text(TEMPLATE)
    (miniproj / "docs/facts").mkdir(parents=True, exist_ok=True)
    (miniproj / "docs/facts/pc.json").write_text(json.dumps({
        "schema": 1, "target": "pc", "alias": "devpc",
        "facts": {"system.python_version": {"value": "3.12.3", "type": "string"}}}))
    log = tmp_path / "ai"
    (tmp_path / "reply.txt").write_text(reply)
    monkeypatch.setenv("AI_LOG", str(log))
    monkeypatch.setenv("AI_REPLY", str(tmp_path / "reply.txt"))
    make_exe(bindir, name, FAKE)
    return log


def test_draft_with_claude(miniproj, bindir, tmp_path, monkeypatch, capsys):
    log = setup(miniproj, bindir, tmp_path, monkeypatch, GOOD)
    assert pidoc("draft", "tmpl.md", "--out", "docs/src/quick.md", "--ai", "claude") == 0
    assert (tmp_path / "ai.argv").read_text() == "-p\n"
    prompt = (tmp_path / "ai.stdin").read_text()
    assert "{{fact:pc:system.python_version}} (string) = 3.12.3" in prompt
    assert "pidoc-run=scan target=pc" in prompt
    assert prompt.endswith(TEMPLATE + "\n")
    text = (miniproj / "docs/src/quick.md").read_text()
    assert text.startswith("# 빠른 시작") and "```markdown" not in text

    records = list((miniproj / "docs/ai").iterdir())
    assert [r.name for r in records] == ["20261026T231500-draft"]
    rec = records[0]
    meta = json.loads((rec / "meta.json").read_text())
    assert meta["provider"] == "claude" and meta["argv"] == ["claude", "-p"] and meta["exit"] == 0
    assert (rec / "prompt.txt").read_text() == prompt
    assert (rec / "raw.txt").read_text() == GOOD
    assert len((rec / "input.sha256").read_text().strip()) == 64


def test_draft_reports_numbers(miniproj, bindir, tmp_path, monkeypatch, capsys):
    setup(miniproj, bindir, tmp_path, monkeypatch, "# 빠른 시작\n\n파이썬 3.12 가 필요하고 5초마다 돕니다.\n")
    assert pidoc("draft", "tmpl.md", "--out", "docs/src/quick.md", "--ai", "claude") == 1
    out = capsys.readouterr().out
    assert "docs/src/quick.md:3: [numbers] 근거 없는 숫자: 3.12, 5 " in out
    assert "| 파이썬 3.12 가" in out
    assert "빠른" not in out.split("초안:")[1].split("\n", 1)[1]   # 제목 '빠른 시작' 은 경고 없음
    assert (miniproj / "docs/src/quick.md").exists()      # 초안은 저장


def test_draft_with_codex(miniproj, bindir, tmp_path, monkeypatch):
    setup(miniproj, bindir, tmp_path, monkeypatch, GOOD, name="codex")
    assert pidoc("draft", "tmpl.md", "--out", "docs/src/quick.md", "--ai", "codex") == 0
    assert (tmp_path / "ai.argv").read_text() == "exec\n-\n"


def test_draft_none_saves_prompt_only(miniproj, bindir, tmp_path, monkeypatch, capsys):
    setup(miniproj, bindir, tmp_path, monkeypatch, GOOD)
    assert pidoc("draft", "tmpl.md", "--out", "docs/src/quick.md") == 0   # 설정 없으면 none
    assert not (tmp_path / "ai.stdin").exists()
    assert not (miniproj / "docs/src/quick.md").exists()
    rec = miniproj / "docs/ai/20261026T231500-draft"
    assert "## 틀" in (rec / "prompt.txt").read_text()
    assert not (rec / "raw.txt").exists()
    assert "프롬프트만 저장" in capsys.readouterr().out


def test_draft_ai_failure(miniproj, bindir, tmp_path, monkeypatch, capsys):
    setup(miniproj, bindir, tmp_path, monkeypatch, GOOD)
    make_exe(bindir, "claude", "echo '로그인이 필요합니다' >&2\nexit 1\n")
    assert pidoc("draft", "tmpl.md", "--out", "x.md", "--ai", "claude") == 3
    assert "로그인이 필요합니다" in capsys.readouterr().err


def test_model_from_config(miniproj, bindir, tmp_path, monkeypatch):
    setup(miniproj, bindir, tmp_path, monkeypatch, GOOD)
    toml = miniproj / "docs/pidoc.toml"
    toml.write_text(toml.read_text() + '\n[ai]\nprovider = "claude"\nmodel = "some-model"\n')
    assert pidoc("draft", "tmpl.md", "--out", "docs/src/quick.md") == 0
    assert (tmp_path / "ai.argv").read_text() == "-p\n--model\nsome-model\n"
