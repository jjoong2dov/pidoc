import socket

from pidoc import config, mask

from conftest import make_exe, pidoc


def write_doc(root, text):
    path = root / "docs/src/use.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


# --- mask ---

def test_mask_rules(miniproj, monkeypatch):
    monkeypatch.setattr(socket, "gethostname", lambda: "build-host-7")
    cfg = config.load(miniproj / "docs/pidoc.toml")
    rules = mask.rules_for(cfg, cfg.targets["pc"])
    text = ('{"time": "2026-10-26T23:15:02+09:00", "host": "devpc"}\n'
            "started 23:15:02.123 on build-host-7 pid=4321 pimon[987]: ok 2026-10-26\n")
    assert mask.apply(rules, text) == ('{"time": "<time>", "host": "<host>"}\n'
                                       "started <time> on <host> pid=<pid> pimon[<pid>]: ok <time>\n")


def test_mask_off_and_patterns(miniproj):
    toml = miniproj / "docs/pidoc.toml"
    toml.write_text(toml.read_text() + "\n[mask]\ntime = false\npatterns = [ { re = '\"temp\": [0-9.]+', to = '\"temp\": <n>' } ]\n")
    cfg = config.load(toml)
    rules = mask.rules_for(cfg, cfg.targets["pc"])
    assert mask.apply(rules, '"temp": 48.3 at 23:15:02') == '"temp": <n> at 23:15:02'


# --- quote ---

QUOTE_OK = """\
# x

```python pidoc-quote=minimon/settings.py#L5-L6
DEFAULTS = {
    "path": "/",   
```

```python pidoc-quote=minimon/settings.py#L5
```
"""


def test_quote_matches_ignoring_trailing_space(miniproj):
    write_doc(miniproj, QUOTE_OK)
    assert pidoc("check", "--only", "quote") == 0


def test_quote_mismatch_and_bad_range(miniproj, capsys):
    write_doc(miniproj, QUOTE_OK.replace('"path": "/"', '"path": "/srv"') +
              "\n```python pidoc-quote=minimon/nope.py\n```\n")
    assert pidoc("check", "--only", "quote") == 1
    out = capsys.readouterr().out
    assert "use.md:5: [quote] 인용이 minimon/settings.py#L5-L6 와 다릅니다(블록 2번째 줄)" in out
    assert "인용할 파일이 없습니다: minimon/nope.py" in out


def test_quote_detects_code_change(miniproj, capsys):
    write_doc(miniproj, QUOTE_OK)
    settings = miniproj / "minimon/settings.py"
    settings.write_text(settings.read_text().replace('"path": "/"', '"path": "/data"'))
    assert pidoc("check", "--only", "quote") == 1


# --- run ---

def test_run_needs_evidence(miniproj, capsys):
    write_doc(miniproj, "# x\n\n```console pidoc-run=scan\n```\n")
    assert pidoc("check", "--only", "run") == 1
    assert "scan: 대상 pc 의 성공한 증거가 없습니다" in capsys.readouterr().out
    pidoc("collect")
    assert pidoc("check", "--only", "run") == 0


def test_run_body_compared_with_evidence(miniproj, capsys):
    pidoc("collect")
    write_doc(miniproj, "# x\n\n```console pidoc-run=scan\nscan /  \n\n```\n")
    assert pidoc("check", "--only", "run") == 0
    write_doc(miniproj, "# x\n\n```console pidoc-run=scan\nscan /tmp\n```\n")
    capsys.readouterr()
    assert pidoc("check", "--only", "run") == 1
    assert "scan: 최신 증거와 다릅니다(1번째 줄, 정규화 뒤): 'scan /tmp' / 'scan /'" in capsys.readouterr().out


CLOCK = """\
echo "at $(date +%H:%M:%S.%N) pid=$$"
cat "$CLOCK_FILE"
"""


def setup_clock(miniproj, bindir, tmp_path, monkeypatch, extra=""):
    make_exe(bindir, "clock", CLOCK)
    monkeypatch.setenv("CLOCK_FILE", str(tmp_path / "clock.txt"))
    (tmp_path / "clock.txt").write_text("level ok\n")
    toml = miniproj / "docs/pidoc.toml"
    toml.write_text(toml.read_text().replace('allow_programs = ["python3"]',
                                             'allow_programs = ["python3", "clock"]\nenv_allow = ["PATH", "CLOCK_FILE"]')
                    + '\n[[command]]\nid = "clock"\nargv = ["clock"]\n' + extra)
    assert pidoc("collect", "--only", "clock") == 0
    write_doc(miniproj, "# x\n\n```console pidoc-run=clock\n```\n")


def test_rerun_masks_time_and_pid(miniproj, bindir, tmp_path, monkeypatch, capsys):
    setup_clock(miniproj, bindir, tmp_path, monkeypatch)
    assert pidoc("check", "--only", "run", "--rerun") == 0
    (tmp_path / "clock.txt").write_text("level warn\n")          # 진짜로 바뀐 출력
    capsys.readouterr()
    assert pidoc("check", "--only", "run", "--rerun") == 1
    assert "지금 실행한 출력과 다릅니다(2번째 줄" in capsys.readouterr().out


def test_rerun_without_time_mask_fails(miniproj, bindir, tmp_path, monkeypatch):
    setup_clock(miniproj, bindir, tmp_path, monkeypatch, extra="\n[mask]\ntime = false\n")
    assert pidoc("check", "--only", "run", "--rerun") == 1
