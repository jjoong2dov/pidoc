"""walk: 따라 하기 문서의 pidoc-step 블록을 차례로 실행."""

import json
import socket

from conftest import make_exe, pidoc

DOC = """\
# 따라 하기

```sh pidoc-step
mkdir -p work/sub
cd work/sub
echo 안녕 > note.txt
```

이 블록은 설명용이라 실행하지 않는다.

```sh
rm -rf /
```

```sh pidoc-step
cat note.txt
pwd | sed 's|.*/||'
```

```sh pidoc-step
echo 끝
```
"""


def write(root, text, name="tutorial.md"):
    path = root / "docs/out" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def walk_dir(root):
    return root / "docs/evidence/walks/20261026T231500-pc"


def test_walk_runs_steps_and_keeps_cwd(miniproj, capsys):
    write(miniproj, DOC)
    assert pidoc("walk", "docs/out/tutorial.md", "--target", "pc") == 0
    out = capsys.readouterr().out
    assert "1단계 통과" in out and "3단계 통과" in out and "모든 단계 통과" in out
    d = walk_dir(miniproj)
    assert (d / "step02.stdout").read_text() == "안녕\nsub\n"         # cd 가 다음 단계로 이어짐
    assert (d / "step01.sh").read_text().startswith("mkdir -p work/sub")
    assert "__PIDOC_WALK_CWD__" not in (d / "step01.stderr").read_text()
    manifest = json.loads((d / "manifest.json").read_text())
    assert manifest["result"] == "passed" and len(manifest["steps"]) == 3
    assert manifest["steps"][1]["line"] == 15
    assert (miniproj / "work/sub/note.txt").read_text() == "안녕\n"     # 로컬은 저장소 루트에서 시작


def test_walk_stops_on_failure(miniproj, capsys):
    write(miniproj, DOC.replace("cat note.txt", "echo 앞부분\nfalse | cat\necho 여기는 안 옴"))
    assert pidoc("walk", "docs/out/tutorial.md", "--target", "pc") == 3
    out = capsys.readouterr().out
    assert "2단계 실패 (docs/out/tutorial.md:15): 종료 코드 1" in out    # pipefail
    assert "| 앞부분" in out and "여기는 안 옴" not in out
    assert "3단계" not in out.split("2단계 실패")[1].split("—")[0]
    manifest = json.loads((walk_dir(miniproj) / "manifest.json").read_text())
    assert manifest["failed_step"] == 2 and not (walk_dir(miniproj) / "step03.json").exists()


def test_walk_from_and_dry_run(miniproj, capsys):
    write(miniproj, DOC)
    assert pidoc("walk", "docs/out/tutorial.md", "--target", "pc", "--dry-run") == 0
    out = capsys.readouterr().out
    assert "[2단계 · docs/out/tutorial.md:15 · 실행]" in out and "  $ cat note.txt" in out
    assert "rm -rf" not in out
    assert not (miniproj / "docs/evidence/walks").exists()
    assert pidoc("walk", "docs/out/tutorial.md", "--target", "pc", "--from", "3") == 0
    manifest = json.loads((walk_dir(miniproj) / "manifest.json").read_text())
    assert [s.get("skipped", False) for s in manifest["steps"]] == [True, True, False]
    assert pidoc("walk", "docs/out/tutorial.md", "--target", "pc", "--from", "9") == 2


def test_walk_timeout(miniproj, capsys):
    toml = miniproj / "docs/pidoc.toml"
    toml.write_text(toml.read_text() + "\n[walk]\ntimeout_s = 0.5\n")
    write(miniproj, "# x\n\n```sh pidoc-step\nsleep 5\n```\n")
    assert pidoc("walk", "docs/out/tutorial.md", "--target", "pc") == 3
    assert "1단계 실패 (docs/out/tutorial.md:3): 시간 초과" in capsys.readouterr().out


def test_walk_ignores_allow_programs_and_redacts(miniproj, monkeypatch):
    monkeypatch.setattr(socket, "gethostname", lambda: "build-host-7")
    write(miniproj, "# x\n\n```sh pidoc-step\nuname -s\necho on build-host-7\n```\n")
    assert pidoc("walk", "docs/out/tutorial.md", "--target", "pc") == 0      # allow_programs 는 python3 뿐
    assert (walk_dir(miniproj) / "step01.stdout").read_text().endswith("on devpc\n")


FAKE_SSH = """\
printf '%s\\0' "$@" >> "$SSH_LOG"
printf '\\n' >> "$SSH_LOG"
for last; do :; done
sh -c "$last"
"""


def test_walk_over_ssh(miniproj, bindir, tmp_path, monkeypatch, capsys):
    log = tmp_path / "ssh.log"
    monkeypatch.setenv("SSH_LOG", str(log))
    make_exe(bindir, "ssh", FAKE_SSH)
    toml = miniproj / "docs/pidoc.toml"
    toml.write_text(toml.read_text().replace(
        "[collect]\n", '[targets.pi]\nkind = "ssh"\nhost = "pi@192.0.2.20"\nalias = "pi4"\ncwd = "' + str(tmp_path) + '"\n\n'
        '[collect]\nenv_allow = ["PATH", "SSH_LOG"]\n'))
    write(miniproj, DOC)
    assert pidoc("walk", "docs/out/tutorial.md", "--target", "pi") == 0
    first = log.read_text().split("\0")[:9]                  # 첫 단계의 ssh argv
    assert first[:8] == ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10",
                         "--", "pi@192.0.2.20"]
    assert first[8].startswith("bash -e -o pipefail -c ")
    assert (tmp_path / "work/sub/note.txt").read_text() == "안녕\n"
    d = miniproj / "docs/evidence/walks/20261026T231500-pi"
    assert (d / "step02.stdout").read_text() == "안녕\nsub\n"
