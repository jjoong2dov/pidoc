"""13장 파이 실기에서 찾아 고친 것.

1. 같은 주소에 OS 를 새로 구우면 ~/.ssh/known_hosts 의 옛 키 때문에 접속이 막힌다
   → 대상마다 known_hosts 파일을 따로 줄 수 있게 했다.
2. ssh 가 오류 메시지에 이 PC 의 홈 경로(사용자 이름 포함)를 찍었고 그대로 증거에 남았다
   → 수집할 때 홈 경로를 ~ 로 가린다.
"""
import json
from pathlib import Path

from conftest import make_exe, pidoc, write_config
from test_ssh_replay import CONFIG, setup, ssh_calls


def test_known_hosts_per_target(repo, bindir, monkeypatch, tmp_path):
    log = setup(repo, bindir, monkeypatch, tmp_path)
    text = (repo / "docs/pidoc.toml").read_text().replace('cwd = "pimon dir"', 'cwd = "pimon dir"\nknown_hosts = "pi.known_hosts"')
    write_config(repo, text)
    assert pidoc("collect", "--target", "pi", "--only", "kernel") == 0
    argv = ssh_calls(log)
    want = str((repo / "docs/pi.known_hosts").resolve())
    assert argv[6:8] == ["-o", f"UserKnownHostsFile={want}"]
    assert argv[8:10] == ["--", "pi@pi4.local"]


def test_home_path_redacted_in_evidence(repo, bindir, monkeypatch, tmp_path):
    setup(repo, bindir, monkeypatch, tmp_path)
    home = tmp_path / "home" / "someone"
    monkeypatch.setenv("HOME", str(home))
    # 진짜 ssh 처럼 stderr 에 known_hosts 경로를 찍고 실패한다
    make_exe(bindir, "ssh", f'echo "Add correct host key in {home}/.ssh/known_hosts to get rid of this message." >&2\nexit 255\n')
    assert pidoc("collect", "--target", "pi", "--only", "kernel") == 3
    run = next((repo / "docs/evidence/runs").iterdir())
    err = (run / "kernel.stderr").read_text()
    assert str(home) not in err
    assert "in ~/.ssh/known_hosts" in err


def test_home_redaction_can_be_turned_off(repo, bindir, monkeypatch, tmp_path):
    setup(repo, bindir, monkeypatch, tmp_path)
    home = tmp_path / "home" / "someone"
    monkeypatch.setenv("HOME", str(home))
    write_config(repo, (repo / "docs/pidoc.toml").read_text().replace("[redact]", "[redact]\nhome = false"))
    make_exe(bindir, "ssh", f'echo "{home}/x" >&2\nexit 255\n')
    pidoc("collect", "--target", "pi", "--only", "kernel")
    run = next((repo / "docs/evidence/runs").iterdir())
    assert str(home) in (run / "kernel.stderr").read_text()


def test_remote_hostname_is_learned_and_redacted(repo, bindir, monkeypatch, tmp_path):
    """3. ssh 대상은 주소만 알고 장비의 호스트 이름은 몰라서, 출력의 host 가 그대로 남았다
    → 수집 전에 uname -n 으로 알아내 가린다. 이름은 공개하지 않는 폴더에 기록한다."""
    setup(repo, bindir, monkeypatch, tmp_path)
    make_exe(bindir, "ssh", 'for last; do :; done\n'
             'if [ "$last" = "uname -n" ]; then echo lab-board-3; exit 0; fi\n'
             'echo "Linux lab-board-3 6.12.47+rpt-rpi-v8 #1 SMP"\n')
    assert pidoc("collect", "--target", "pi", "--only", "kernel") == 0
    run = next((repo / "docs/evidence/runs").iterdir())
    assert (run / "kernel.stdout").read_text() == "Linux board 6.12.47+rpt-rpi-v8 #1 SMP\n"
    names = json.loads((repo / "docs/evidence/private/hostnames.json").read_text())
    assert names == {"pi": ["lab-board-3"]}
    # 검사기도 이 이름을 안다: 손으로 문서에 써 넣으면 secrets 가 잡는다
    src = repo / "docs/src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "a.md").write_text("# 제목\n\n보드 이름은 lab-board-3 입니다.\n")
    assert pidoc("check", "--only", "secrets") == 1
