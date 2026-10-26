"""Codex 리뷰 1차(evidence/cx_plan/lab_r1.txt) 지적을 재현하는 시험.

번호는 리뷰의 번호. 고치기 전에 먼저 실패하는 것을 확인했다(REVIEW1.md).
"""

import json
import os
import socket

import pytest

from pidoc import config
from pidoc.checks.numbers import numbers_in, scan_text

from conftest import make_exe, pidoc


def add_command(root, text, programs=()):
    toml = root / "docs/pidoc.toml"
    body = toml.read_text()
    if programs:
        names = ", ".join(f'"{p}"' for p in ("python3", *programs))
        body = body.replace('allow_programs = ["python3"]', f"allow_programs = [{names}]")
    body = body.replace("[extract]", text.strip() + "\n\n[extract]")
    toml.write_text(body)


def write_doc(root, text, name="use.md"):
    path = root / "docs/src" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def facts_of(root, target="pc"):
    return json.loads((root / f"docs/facts/{target}.json").read_text())


# 1. 사실 파일을 손으로 고쳐도 통과하던 것
def test_r01_hand_edited_fact_is_rejected(miniproj, capsys):
    pidoc("collect")
    data = facts_of(miniproj)
    data["facts"]["minimon.scan_path"]["value"] = "/evil"
    (miniproj / "docs/facts/pc.json").write_text(json.dumps(data))
    write_doc(miniproj, "# x\n\n{{fact:minimon.scan_path}} {{fact:minimon.commands}}\n")
    capsys.readouterr()
    assert pidoc("check", "--only", "facts") == 1
    assert "증거에서 다시 뽑은 값과 다릅니다" in capsys.readouterr().out
    assert pidoc("render") == 1


def test_r01_code_fact_source_changed(miniproj, capsys):
    pidoc("extract", "config")
    write_doc(miniproj, "# x\n\n{{fact:code:config.limit.default}}\n")
    assert pidoc("check", "--only", "facts") == 0
    settings = miniproj / "minimon/settings.py"
    settings.write_text(settings.read_text().replace('"limit": 90', '"limit": 95'))
    capsys.readouterr()
    assert pidoc("check", "--only", "facts") == 1
    assert "pidoc extract config 를 다시" in capsys.readouterr().out


# 2. 저장소 밖 파일 인용
def test_r02_quote_outside_root(miniproj, tmp_path, capsys):
    (tmp_path / "secret.txt").write_text("비밀\n")
    (miniproj / "link.txt").symlink_to(tmp_path / "secret.txt")
    write_doc(miniproj, "# x\n\n```text pidoc-quote=/etc/hosts\n```\n\n```text pidoc-quote=../secret.txt\n```\n\n"
                        "```text pidoc-quote=link.txt\n```\n")
    assert pidoc("render") == 1
    out = capsys.readouterr().out
    assert out.count("저장소 밖") == 3
    assert not (miniproj / "docs/out/use.md").exists()


def test_r02_deps_outside_root(miniproj, capsys):
    write_doc(miniproj, "<!-- pidoc-deps: ../../../etc/passwd -->\n# x\n")
    assert pidoc("render") == 1
    assert "저장소 밖" in capsys.readouterr().out


# 3. 사실·출력이 Markdown 구조를 탈출
EVIL = "printf '%s\\n' '![x](file:///etc/passwd) <b>a</b> | `t`'\n"


def test_r03_fact_is_escaped(miniproj, bindir):
    make_exe(bindir, "evil", EVIL)
    add_command(miniproj, '[[command]]\nid = "evil"\nargv = ["evil"]\n  [[command.fact]]\n  key = "x.evil"\n'
                          '  extract = "stdout_line"\n', programs=["evil"])
    assert pidoc("collect", "--only", "evil") == 0
    write_doc(miniproj, "# x\n\n본문 {{fact:x.evil}}\n\n코드 {{fact:x.evil|code}}\n\n날것 {{fact:x.evil|raw}}\n")
    assert pidoc("render") == 0
    out = (miniproj / "docs/out/use.md").read_text().splitlines()
    assert out[2] == "본문 \\!\\[x\\](file:///etc/passwd) \\<b\\>a\\</b\\> \\| \\`t\\`"
    assert out[4] == "코드 `` ![x](file:///etc/passwd) <b>a</b> | `t` ``"
    assert out[6] == "날것 ![x](file:///etc/passwd) <b>a</b> | `t`"


def test_r03_multiline_fact_in_prose_is_error(miniproj, bindir, capsys):
    make_exe(bindir, "two", "printf 'a\\nb\\n'\n")
    add_command(miniproj, '[[command]]\nid = "two"\nargv = ["two"]\n  [[command.fact]]\n  key = "x.two"\n'
                          '  extract = "stdout_all"\n', programs=["two"])
    pidoc("collect", "--only", "two")
    write_doc(miniproj, "# x\n\n{{fact:x.two}}\n")
    assert pidoc("render") == 1
    assert "여러 줄" in capsys.readouterr().out


def test_r03_run_output_cannot_close_fence(miniproj, bindir):
    make_exe(bindir, "fence", "printf '```\\n![x](file:///etc/passwd)\\n````\\n'\n")
    add_command(miniproj, '[[command]]\nid = "fence"\nargv = ["fence"]\n', programs=["fence"])
    pidoc("collect", "--only", "fence")
    write_doc(miniproj, "# x\n\n```text pidoc-run=fence\n```\n")
    assert pidoc("render") == 0
    out = (miniproj / "docs/out/use.md").read_text()
    assert "`````text\n```\n![x](file:///etc/passwd)\n````\n`````\n" in out


# 4. 잘린 출력
def test_r04_truncated_output_is_failure(miniproj, bindir, capsys):
    make_exe(bindir, "long", "echo 123456789\n")
    add_command(miniproj, '[[command]]\nid = "long"\nargv = ["long"]\n  [[command.fact]]\n  key = "x.long"\n'
                          '  extract = "stdout_line"\n  type = "int"\n', programs=["long"])
    toml = miniproj / "docs/pidoc.toml"
    toml.write_text(toml.read_text().replace("[collect]\n", "[collect]\nmax_output = 4\n"))
    assert pidoc("collect", "--only", "long") == 3
    assert not (miniproj / "docs/facts/pc.json").exists()
    assert "잘림" in capsys.readouterr().out
    run = miniproj / "docs/evidence/runs/20261026T231500-pc"
    assert (run / "long.stdout").read_bytes() == b""         # 끝나지 않은 줄은 남기지 않는다


# 5. 한 명령의 추출 일부 실패
def test_r05_partial_extraction_updates_nothing(miniproj, bindir, monkeypatch):
    make_exe(bindir, "pair", 'cat "$PAIR"\n')
    monkeypatch.setenv("PAIR", str(miniproj / "pair.txt"))
    (miniproj / "pair.txt").write_text("a=1 b=2\n")
    add_command(miniproj, '[[command]]\nid = "pair"\nargv = ["pair"]\n'
                          '  [[command.fact]]\n  key = "x.a"\n  extract = "regex"\n  pattern = "a=(\\\\d+)"\n'
                          '  [[command.fact]]\n  key = "x.b"\n  extract = "regex"\n  pattern = "b=(\\\\d+)"\n',
                programs=["pair"])
    toml = miniproj / "docs/pidoc.toml"
    toml.write_text(toml.read_text().replace("[collect]\n", '[collect]\nenv_allow = ["PATH", "PAIR"]\n'))
    assert pidoc("collect", "--only", "pair") == 0
    (miniproj / "pair.txt").write_text("a=5 c=9\n")
    assert pidoc("collect", "--only", "pair") == 3
    f = facts_of(miniproj)["facts"]
    assert f["x.a"]["value"] == "1" and f["x.b"]["value"] == "2"


# 6. stale 이 사실·run 변경을 못 봄
def test_r06_stale_sees_fact_and_run_change(miniproj, bindir, capsys, monkeypatch):
    out_file = miniproj / "say.txt"
    out_file.write_text("v1\n")
    monkeypatch.setenv("SAY", str(out_file))
    make_exe(bindir, "say", 'cat "$SAY"\n')
    add_command(miniproj, '[[command]]\nid = "say"\nargv = ["say"]\n  [[command.fact]]\n  key = "x.say"\n'
                          '  extract = "stdout_line"\n', programs=["say"])
    toml = miniproj / "docs/pidoc.toml"
    toml.write_text(toml.read_text().replace("[collect]\n", '[collect]\nenv_allow = ["PATH", "SAY"]\n'))
    pidoc("collect", "--only", "say")
    write_doc(miniproj, "# x\n\n{{fact:x.say}}\n\n```text pidoc-run=say\n```\n")
    assert pidoc("render") == 0
    assert pidoc("stale") == 0
    out_file.write_text("v2\n")
    monkeypatch.setenv("PIDOC_NOW", "2026-10-27T09:00:00+09:00")
    pidoc("collect", "--only", "say")
    capsys.readouterr()
    assert pidoc("stale") == 1
    out = capsys.readouterr().out
    assert "사실 pc:x.say 바뀜" in out and "run pc:say 바뀜" in out


# 7. 코드 안 숫자
def test_r07_numbers_in_code_are_warned():
    found = scan_text("# x\n\n```sh\npython 99.7 --port 65535\n```\n\n`Python 99.7 on port 65535` 실행\n")
    assert [(n, lv) for n, lv, _ in found] == [(4, "warn"), (7, "warn")]
    assert "코드 안 숫자" in found[0][2]


def test_r07_generated_and_ok_blocks_skip():
    text = ("# x\n\n```text pidoc-run=x\n99.7\n```\n\n```sh pidoc-ok=버전 예시\npython 99.7\n```\n\n"
            "`port 65535` <!-- pidoc-ok: 예시 포트 -->\n")
    assert scan_text(text) == []


# 8. 렌더 실패 뒤 옛 결과
def test_r08_old_output_removed_on_failure(miniproj, capsys):
    pidoc("collect")
    write_doc(miniproj, "# x\n\n{{fact:minimon.scan_path}}\n")
    assert pidoc("render") == 0
    write_doc(miniproj, "# x\n\n{{fact:minimon.scan_path}} {{fact:nope}}\n")
    assert pidoc("render") == 1
    assert not (miniproj / "docs/out/use.md").exists()
    deps = json.loads((miniproj / "docs/out/.deps.json").read_text())
    assert "docs/src/use.md" not in deps
    assert "이전 결과 docs/out/use.md 를 지웠습니다" in capsys.readouterr().out


# 9. AI 기록의 비밀
def test_r09_ai_prompt_secret_scan_and_allowlist(miniproj, bindir, capsys):
    pidoc("collect")
    data = facts_of(miniproj)
    (miniproj / "tmpl.md").write_text("# 틀\n")
    make_exe(bindir, "claude", "cat > /dev/null\necho '# 초안'\n")
    toml = miniproj / "docs/pidoc.toml"
    toml.write_text(toml.read_text() + '\n[ai]\nfacts = ["pc:minimon.commands"]\n')
    assert pidoc("draft", "tmpl.md", "--out", "docs/src/d.md", "--ai", "claude") == 0
    prompt = next((miniproj / "docs/ai").iterdir()) / "prompt.txt"
    assert "minimon.commands" in prompt.read_text() and "minimon.scan_path" not in prompt.read_text()
    (miniproj / "tmpl.md").write_text("# 틀\n서버 10.1.2.3 에 올림\n")
    capsys.readouterr()
    assert pidoc("draft", "tmpl.md", "--out", "docs/src/d.md", "--ai", "claude") == 2
    assert "AI 에 보내지 않았습니다" in capsys.readouterr().err


def test_r09_secrets_scans_ai_dir_and_gitignore(miniproj, tmp_path, monkeypatch, capsys):
    (miniproj / "docs/ai/x").mkdir(parents=True)
    (miniproj / "docs/ai/x/raw.txt").write_text("10.1.2.3\n")
    assert pidoc("check", "--only", "secrets") == 1
    assert "docs/ai/x/raw.txt:1:" in capsys.readouterr().out
    monkeypatch.chdir(tmp_path)
    pidoc("init")
    assert "ai/" in (tmp_path / "docs/.gitignore").read_text().splitlines()


# 10. allow_programs
def test_r10_shells_cannot_be_allowed(miniproj, capsys):
    toml = miniproj / "docs/pidoc.toml"
    toml.write_text(toml.read_text().replace('allow_programs = ["python3"]', 'allow_programs = ["python3", "bash"]'))
    assert pidoc("collect") == 2
    assert "셸·실행기" in capsys.readouterr().err


def test_r10_inline_code_flag_refused(miniproj, capsys):
    add_command(miniproj, '[[command]]\nid = "inline"\nargv = ["python3", "-c", "print(1)"]\n')
    assert pidoc("collect", "--only", "inline") == 3
    assert "-c" in capsys.readouterr().out


def test_r10_readme_says_not_a_security_boundary():
    readme = (os.path.dirname(__file__) + "/../README.md")
    assert "보안 경계가 아니라 실수 방지 목록" in open(readme, encoding="utf-8").read()


# 11. 비밀 검사 범위
def test_r11_more_secret_patterns(miniproj, capsys):
    write_doc(miniproj, "# x\n\nAuthorization: Bearer abcdefghijklmnop1234\n-----BEGIN OPENSSH PRIVATE KEY-----\n"
                        "2a00:1450:4001::1 와 2001:db8::1\nhttps://user:pw@example.org/x\n/home/alice/work 와 /home/pi/pimon\n"
                        "ghp_abcdefghijklmnopqrstuvwxyz0123456789\n")
    assert pidoc("check", "--only", "secrets") == 1
    out = capsys.readouterr().out
    for n in (3, 4, 5, 6, 7, 8):
        assert f"use.md:{n}:" in out, n
    assert out.count("use.md:5:") == 1                       # 2001:db8:: 은 문서용


def test_r11_sensitive_argv_masked(miniproj, bindir):
    make_exe(bindir, "tok", "echo ok\n")
    add_command(miniproj, '[[command]]\nid = "tok"\nargv = ["tok", "--token", "s3cr3t", "--password=hunter2"]\n',
                programs=["tok"])
    assert pidoc("collect", "--only", "tok") == 0
    run = miniproj / "docs/evidence/runs/20261026T231500-pc"
    for name in ("tok.json", "manifest.json"):
        text = (run / name).read_text()
        assert "s3cr3t" not in text and "hunter2" not in text, name
    assert json.loads((run / "tok.json").read_text())["argv"] == ["tok", "--token", "<가림>", "--password=<가림>"]


# 12. 이미 있는 .gitignore
def test_r12_existing_gitignore_gets_required_lines(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/.gitignore").write_text("out/\n")
    assert pidoc("init") == 0
    lines = (tmp_path / "docs/.gitignore").read_text().splitlines()
    assert lines.count("out/") == 1 and "evidence/private/" in lines and "ai/" in lines


# 13. 더 최근 수집이 실패했는데 옛 사실이 쓰임
def test_r13_newer_failure_blocks_old_fact(miniproj, bindir, capsys, monkeypatch):
    make_exe(bindir, "ver", "echo 1.0\n")
    add_command(miniproj, '[[command]]\nid = "ver"\nargv = ["ver"]\n  [[command.fact]]\n  key = "x.ver"\n'
                          '  extract = "stdout_line"\n', programs=["ver"])
    pidoc("collect", "--only", "ver")
    write_doc(miniproj, "# x\n\n{{fact:x.ver}}\n\n```text pidoc-run=ver\n```\n")
    assert pidoc("render") == 0
    make_exe(bindir, "ver", "exit 1\n")
    monkeypatch.setenv("PIDOC_NOW", "2026-10-27T09:00:00+09:00")
    assert pidoc("collect", "--only", "ver") == 3
    capsys.readouterr()
    assert pidoc("render") == 1
    out = capsys.readouterr().out
    assert out.count("더 최근 수집(20261027T090000-pc)이 실패") == 2


# 14. UTF-8 이 아닌 출력
def test_r14_invalid_utf8_is_failure(miniproj, bindir, capsys):
    make_exe(bindir, "bad", "printf 'v=\\377\\n'\n")
    add_command(miniproj, '[[command]]\nid = "bad"\nargv = ["bad"]\n  [[command.fact]]\n  key = "x.bad"\n'
                          '  extract = "stdout_line"\n', programs=["bad"])
    assert pidoc("collect", "--only", "bad") == 3
    assert "UTF-8" in capsys.readouterr().out


# 15. 영문에 붙은 버전, 표·목록 순번 오인
@pytest.mark.parametrize("line, expected", [
    ("Python3.99 필요", ["3.99"]), ("OpenSSL3.7", ["3.7"]), ("version3.2", ["3.2"]),
    ("2026. 출시", ["2026"]),
])
def test_r15_numbers_attached_to_words(line, expected):
    assert numbers_in(line) == expected


def test_r15_table_first_column_must_be_sequence():
    found = scan_text("| 번호 | 값 |\n|---|---|\n| 1 | 가 |\n| 2 | 나 |\n\n| 온도 | 판정 |\n|---|---|\n| 70 | 주의 |\n")
    assert [n for n, _, _ in found] == [8]


# 16. 저장소 밖 출력·cwd
def test_r16_draft_out_outside_root(miniproj, tmp_path, capsys):
    (miniproj / "tmpl.md").write_text("# 틀\n")
    assert pidoc("draft", "tmpl.md", "--out", str(tmp_path / "x.md")) == 2
    assert "저장소 밖" in capsys.readouterr().err


def test_r16_command_cwd_outside_root(miniproj, capsys):
    add_command(miniproj, '[[command]]\nid = "out"\nargv = ["python3", "--version"]\ncwd = "../.."\n')
    assert pidoc("collect", "--only", "out") == 2
    assert "저장소 밖" in capsys.readouterr().err


# 17. 사실 파일 형식
def test_r17_fact_file_schema(miniproj, capsys):
    pidoc("collect")
    data = facts_of(miniproj)
    data["facts"]["minimon.scan_path"]["type"] = "int"
    (miniproj / "docs/facts/pc.json").write_text(json.dumps(data))
    assert pidoc("facts") == 2
    assert "type 이 int 인데 값은 string" in capsys.readouterr().err


def test_r17_nan_rejected():
    from pidoc import facts
    with pytest.raises(facts.FactError):
        facts.convert("nan", "float")


# 18. 무관한 AST 호출
def test_r18_extract_tracks_receivers(miniproj):
    main = miniproj / "minimon/__main__.py"
    main.write_text(main.read_text().replace("    return p\n", "    builder = Other()\n    builder.add_argument(\"--internal\")\n    return p\n"))
    web = miniproj / "minimon/web.py"
    web.write_text(web.read_text().replace("        if path == \"/health\":",
                                           "        filesystem_path = '/x'\n        if filesystem_path == \"/tmp\":\n            pass\n        if path == \"/health\":"))
    pidoc("extract", "cli", "http")
    f = json.loads((miniproj / "docs/facts/code.json").read_text())["facts"]
    assert f["cli.minimon.options"]["value"] == ["--config", "--limit"]
    assert f["http.get.paths"]["value"] == ["/health", "/disk", "/disk.json"]


def test_r03_pdf_fetcher_blocks_outside(miniproj):
    pytest.importorskip("weasyprint")
    from pidoc.build import url_fetcher
    fetcher = url_fetcher(config.load(miniproj / "docs/pidoc.toml"))
    fetch = getattr(fetcher, "fetch", fetcher)
    for url in ("file:///etc/hosts", "https://example.org/x.png"):
        with pytest.raises(ValueError):
            fetch(url)
    fetch((miniproj / "minimon/web.py").as_uri())          # 저장소 안은 된다
