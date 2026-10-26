import json
import socket
import subprocess

from conftest import pidoc


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


# --- links ---

def test_links(miniproj, capsys):
    write(miniproj, "docs/src/b.md", "# 둘째 문서\n\n## 설정 키\n\n## 설정 키\n")
    write(miniproj, "docs/src/a.md", """\
# 첫째

## 설치 방법

[ok1](b.md) [ok2](b.md#설정-키) [ok3](b.md#설정-키-1) [ok4](#설치-방법)
[코드](../../minimon/settings.py) [바깥](https://example.org/x#y) ![그림](<b.md>)
[없는 파일](c.md) [없는 앵커](b.md#없음) [자기 앵커](#없다)
`[코드 안](nope.md)`
""")
    assert pidoc("check", "--only", "links") == 1
    out = capsys.readouterr().out
    assert "docs/src/a.md:7: [links] 링크 대상이 없습니다: c.md" in out
    assert "앵커가 없습니다: b.md#없음" in out and "앵커가 없습니다: #없다" in out
    assert out.count("[links]") == 3


# --- terms ---

def test_terms(miniproj, capsys):
    write(miniproj, "docs/terms.toml", '"GitHub" = ["Github", "github"]\n"라즈베리 파이" = ["라즈베리파이", "라즈베리 파이4"]\n')
    write(miniproj, "docs/src/a.md", """\
# x

Github 에 올리고 라즈베리파이 에서 돌립니다.
GitHub 과 라즈베리 파이 는 맞는 말. `github` 는 코드라 넘김. github.com 주소도 잡힘
""")
    assert pidoc("check", "--only", "terms") == 1
    out = capsys.readouterr().out.splitlines()
    assert "docs/src/a.md:3: [terms] 'Github' 대신 'GitHub'" in out
    assert "docs/src/a.md:3: [terms] '라즈베리파이' 대신 '라즈베리 파이'" in out
    assert "docs/src/a.md:4: [terms] 'github' 대신 'GitHub'" in out
    assert sum("[terms]" in line for line in out) == 3


# --- secrets ---

def test_secrets(miniproj, monkeypatch, capsys):
    monkeypatch.setattr(socket, "gethostname", lambda: "build-host-7")
    write(miniproj, "docs/banned.txt", "# 회사 이름 같은 것\nAcmeCorp\n")
    write(miniproj, "docs/src/a.md", """\
# x

주소 192.0.2.10 과 127.0.0.1:8080, 0.0.0.0 은 괜찮다. 버전처럼 보이는 1.2.3.4 도 IP 형식이면 잡는다.
사내 10.1.2.3 은 안 된다.
메일 dev@example.com 은 되고 someone@corp.test 는 안 된다.

```console
$ ssh pi@build-host-7
acmecorp 서버
```
""")
    assert pidoc("check", "--only", "secrets") == 1
    out = capsys.readouterr().out
    assert "a.md:4: [secrets] IP 주소 10… " in out
    assert "a.md:5: [secrets] 이메일 so…" in out
    assert "a.md:8: [secrets] 실제 hostname bu…" in out
    assert "a.md:9: [secrets] 금지어 Ac…" in out
    assert "a.md:3: [secrets] IP 주소 1." in out          # 1.2.3.4 는 진짜 IP 형식이라 잡는다
    assert "192.0.2.10" not in out and "build-host-7" not in out


def test_secrets_scans_out_facts_and_ip_allow(miniproj, capsys):
    write(miniproj, "docs/src/a.md", "# x\n")
    write(miniproj, "docs/out/a.md", "# x\n\n주소 10.1.2.3\n")
    write(miniproj, "docs/facts/pc.json", json.dumps({"schema": 1, "target": "pc", "facts": {}, "note": "172.16.0.9"}))
    assert pidoc("check", "--only", "secrets") == 1
    out = capsys.readouterr().out
    assert "docs/out/a.md:3:" in out and "docs/facts/pc.json:1:" in out
    toml = miniproj / "docs/pidoc.toml"
    toml.write_text(toml.read_text() + '\n[check]\nip_allow = ["10.0.0.0/8", "172.16.0.9"]\n')
    assert pidoc("check", "--only", "secrets") == 0


# --- stale ---

def git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                   cwd=root, check=True, capture_output=True)


def test_stale_by_hash(miniproj, capsys):
    pidoc("collect")
    write(miniproj, "docs/src/use.md", "<!-- pidoc-deps: minimon/__main__.py -->\n# x\n\n{{fact:minimon.commands}}\n"
                                       "```python pidoc-quote=minimon/settings.py#L5\n```\n")
    write(miniproj, "docs/src/new.md", "# 새 문서\n")
    assert pidoc("render", "docs/src/use.md") == 0
    capsys.readouterr()
    assert pidoc("stale") == 1
    assert capsys.readouterr().out.splitlines() == [
        "docs/src/new.md: 렌더 기록이 없습니다(pidoc render)", "다시 볼 문서 1개"]
    pidoc("render")
    assert pidoc("stale") == 0
    settings = miniproj / "minimon/settings.py"
    settings.write_text(settings.read_text() + "\n# 바뀜\n")
    capsys.readouterr()
    assert pidoc("stale") == 1
    assert "docs/src/use.md: minimon/settings.py 바뀜" in capsys.readouterr().out


def test_stale_since_git(miniproj, capsys):
    toml = miniproj / "docs/pidoc.toml"
    toml.write_text(toml.read_text() + '\n[check]\nstale_deps = { "docs/src/web.md" = ["minimon/web.py"] }\n')
    write(miniproj, "docs/src/web.md", "# 웹\n")
    write(miniproj, "docs/src/other.md", "# 다른 것\n")
    git(miniproj, "init", "-q")
    git(miniproj, "add", "-A")
    git(miniproj, "commit", "-qm", "처음")
    web = miniproj / "minimon/web.py"
    web.write_text(web.read_text() + "\n# 경로 추가 예정\n")
    capsys.readouterr()
    assert pidoc("stale", "--since", "HEAD") == 1
    out = capsys.readouterr().out
    assert "docs/src/web.md: minimon/web.py 바뀜(HEAD 이후)" in out
    assert "other.md" not in out
    assert pidoc("stale", "--since", "no-such-rev") == 2
