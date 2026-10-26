import json

from conftest import pidoc

DOC = """\
<!-- pidoc-target: pc -->
<!-- pidoc-deps: minimon/__main__.py -->
# minimon 쓰기

하위 명령: {{fact:minimon.commands|join}} ({{fact:pc:minimon.scan_path|code}})
기본 경고 기준: {{fact:code:config.limit.default}}

```python pidoc-quote=minimon/settings.py#L5-L9
```

```console pidoc-run=scan
이 내용은 바뀐다
```

```sh
python3 -m minimon {{fact:minimon.commands|join}}
```
"""


def write_doc(root, text=DOC, name="use.md"):
    path = root / "docs/src" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_render_fills_everything(miniproj):
    assert pidoc("collect") == 0
    assert pidoc("extract", "config") == 0
    write_doc(miniproj)
    assert pidoc("render") == 0
    out = (miniproj / "docs/out/use.md").read_text()
    assert out.startswith("# minimon 쓰기\n")                 # 머리말은 지움
    assert "하위 명령: scan, serve (`/`)" in out
    assert "기본 경고 기준: 90" in out
    assert "```python\nDEFAULTS = {\n" in out and '    "web": {"port": 8000, "enabled": False},\n}\n```' in out
    assert "```console\nscan /\n```" in out
    assert "python3 -m minimon scan, serve" in out
    deps = json.loads((miniproj / "docs/out/.deps.json").read_text())
    info = deps["docs/src/use.md"]
    assert set(info["deps"]) == {"minimon/__main__.py", "minimon/settings.py"}
    assert info["facts"] == ["code:config.limit.default", "pc:minimon.commands", "pc:minimon.scan_path"]
    assert info["runs"] == ["20261026T231500-pc"] and info["out"] == "docs/out/use.md"


def test_render_errors_do_not_write(miniproj, capsys):
    pidoc("collect")
    write_doc(miniproj, "# x\n\n{{fact:nope.key}}\n{{fact:minimon.commands|round1}}\n"
                        "{{fact:minimon.scan_path|upper}}\n{{fact:pi:a.b}}\n"
                        "```python pidoc-quote=minimon/settings.py#L5-L999\n```\n"
                        "```console pidoc-run=help target=pi\n```\n")
    assert pidoc("render") == 1
    out = capsys.readouterr().out
    assert "use.md:3: [render] 없는 사실: pc:nope.key" in out
    assert "use.md:4: [render] |round1 은 숫자 사실에만" in out
    assert "use.md:5: [render] 모르는 변환 |upper" in out
    assert "use.md:6: [render] 사실 파일이 없는 대상: pi" in out
    assert "use.md:7: [render] 줄 범위가 파일 밖" in out
    assert "use.md:9: [render] 증거가 없습니다: help (대상 pi)" in out
    assert not (miniproj / "docs/out/use.md").exists()


def test_render_expired_fact(miniproj, monkeypatch, capsys):
    toml = miniproj / "docs/pidoc.toml"
    toml.write_text(toml.read_text().replace('key = "minimon.scan_path"', 'key = "minimon.scan_path"\n  max_age_days = 7'))
    pidoc("collect")
    write_doc(miniproj, "# x\n\n{{fact:minimon.scan_path}}\n")
    monkeypatch.setenv("PIDOC_NOW", "2026-11-10T00:00:00+09:00")
    assert pidoc("render") == 1
    assert "만료된 사실: pc:minimon.scan_path" in capsys.readouterr().out


def test_check_facts_and_numbers(miniproj, capsys):
    pidoc("collect")
    write_doc(miniproj, "# x\n\n{{fact:nope}} 이고 5초마다.\n{{fact:minimon.commands}}\n")
    capsys.readouterr()
    assert pidoc("check") == 1
    out = capsys.readouterr().out
    assert "docs/src/use.md:3: [facts] 없는 사실: pc:nope" in out
    assert "docs/src/use.md:3: [numbers] 근거 없는 숫자: 5" in out
    assert "docs/facts/pc.json: [facts] 경고: 문서에서 쓰이지 않는 사실: pc:minimon.scan_path" in out
    assert "문서 1개 검사: 오류 2, 경고 1" in out


def test_check_only_and_json(miniproj, capsys):
    pidoc("collect")
    write_doc(miniproj, "# x\n\n5초마다.\n")
    capsys.readouterr()
    assert pidoc("check", "--only", "numbers", "--json") == 1
    data = json.loads(capsys.readouterr().out)
    assert data["errors"] == 1 and data["findings"][0]["check"] == "numbers"
    assert pidoc("check", "--only", "spelling") == 2


def test_check_passes_clean_doc(miniproj, capsys):
    pidoc("collect")
    write_doc(miniproj, "# x\n\n{{fact:minimon.commands}} / {{fact:minimon.scan_path}}\n")
    assert pidoc("check") == 0
