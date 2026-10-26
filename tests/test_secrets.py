import pytest

from conftest import ssh_target

# 찾아야 할 값들(실제 값이 아닌 꾸민 값)
FOUND = {
    "IPv4": "10.20.30.40",
    "이메일": "someone@corp.lan",
    "호스트 이름": "raspi.example",
    "홈 경로": "/home/pi/app",
    "개인키": "-----BEGIN OPENSSH PRIVATE KEY-----",
    "금지어": "codename-blue",
}


@pytest.fixture
def docs(repo):
    repo.write_config([], extra_targets=ssh_target())
    for d in ("src", "out", "facts", "evidence/runs/r1/pc"):
        (repo.docs / d).mkdir(parents=True)
    (repo.docs / "banned.txt").write_text("# 금지어\n\nCodename-Blue\n", encoding="utf-8")
    return repo


def put(repo, rel, text):
    p = repo.docs / rel
    p.write_text(text, encoding="utf-8")
    return p


@pytest.mark.parametrize("kind", list(FOUND))
def test_finds_each_kind_without_echoing(docs, cli, capsys, kind):
    value = FOUND[kind]
    put(docs, "src/a.md", f"첫 줄\n여기 {value} 가 있다\n")
    assert cli("check", "--only", "secrets") == 1
    cap = capsys.readouterr()
    shown = cap.out + cap.err
    assert f"src/a.md:2: {kind}" in shown
    # 찾은 값은 앞 두 글자만 보인다. 줄 내용도 찍지 않는다.
    assert f"'{value[:2]}…'" in shown
    assert value not in shown and value[:3] not in shown and "여기" not in shown


def test_this_pc_home_and_hostname(docs, cli, capsys, home):
    put(docs, "src/a.md", f"경로 {home}/proj\n이 PC 는 devbox 이다\n")
    assert cli("check", "--only", "secrets") == 1
    err = capsys.readouterr().err
    assert "a.md:1: 홈 경로" in err and "a.md:2: 호스트 이름" in err
    assert str(home) not in err and "devbox" not in err


def test_scans_out_facts_evidence(docs, cli, capsys):
    put(docs, "out/a.md", "10.20.30.40\n")
    put(docs, "facts/pc.json", '{"k": {"value": "someone@corp.lan"}}\n')
    put(docs, "evidence/runs/r1/pc/x.stdout", "ok\nraspi.example\n")
    (docs.docs / "evidence/runs/r1/pc/y.stderr").write_bytes(b"\xff\xfe /home/pi\n")
    assert cli("check", "--only", "secrets") == 1
    cap = capsys.readouterr()
    assert "out/a.md:1: IPv4" in cap.err
    assert "facts/pc.json:1: 이메일" in cap.err
    assert "evidence/runs/r1/pc/x.stdout:2: 호스트 이름" in cap.err
    assert "evidence/runs/r1/pc/y.stderr:1: 홈 경로" in cap.err
    assert "secrets 4건" in cap.out


def test_allowed_values_pass(docs, cli):
    put(docs, "src/a.md",
        "예시 192.0.2.10, 198.51.100.7, 203.0.113.1, 가린 IP 192.0.2.x\n"
        "루프백 127.0.0.1, 넷마스크 255.255.255.0, 모두 0.0.0.0\n"
        "메일 user@example.com, a@b.example, c@host.test\n"
        "별칭 pi 와 devpc, 경로 ~/app, /tmp/home/user\n"
        "-----BEGIN PUBLIC KEY-----\n")
    put(docs, "evidence/runs/r1/pc/x.stdout", "hello\n")
    assert cli("check", "--only", "secrets") == 0


def test_no_banned_file_is_fine(docs, cli):
    (docs.docs / "banned.txt").unlink()
    put(docs, "src/a.md", "codename-blue\n")
    assert cli("check", "--only", "secrets") == 0


def test_multiple_in_one_line(docs, cli, capsys):
    put(docs, "src/a.md", "10.0.0.1 과 10.0.0.2\n")
    assert cli("check", "--only", "secrets") == 1
    assert capsys.readouterr().err.count("a.md:1: IPv4") == 2
