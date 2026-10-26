import hashlib
import json

import pytest

from conftest import PY, ssh_target
from pidoc.redact import Redactor


def make(home, hosts=None):
    return Redactor(home=str(home), hosts=hosts or {"raspi.example": "pi"}, ip_text="192.0.2.x")


@pytest.mark.parametrize("text, expected", [
    ("addr 192.0.2.10/24", "addr 192.0.2.x/24"),
    ("a 198.51.100.7, b 203.0.113.255", "a 192.0.2.x, b 192.0.2.x"),
    ("lo 127.0.0.1 any 0.0.0.0 mask 255.255.255.0", "lo 127.0.0.1 any 0.0.0.0 mask 255.255.255.0"),
    ("ver 1.2.3.4.5 bad 999.1.1.1", "ver 1.2.3.4.5 bad 999.1.1.1"),
    ("ssh pi@raspi.example ok", "ssh pi@pi ok"),
    ("RASPI up; raspi.local", "pi up; pi.local"),
    ("raspi2 myraspi raspi-old", "raspi2 myraspi raspi-old"),
    ("{home}/work/x {home}", "~/work/x ~"),
    ("{home}2/x", "{home}2/x"),
])
def test_redact_text(home, text, expected):
    r = make(home)
    assert r.text(text.format(home=home)) == expected.format(home=home)


def test_redact_bytes_keeps_non_utf8(home):
    r = make(home)
    assert r.bytes(b"\xff raspi \x00 192.0.2.9\n") == b"\xff pi \x00 192.0.2.x\n"


def test_host_given_as_ip_becomes_alias(home):
    r = make(home, hosts={"192.0.2.50": "pi"})
    assert r.text("from 192.0.2.50 and 192.0.2.51") == "from pi and 192.0.2.x"


def test_redact_obj(home):
    r = make(home)
    assert r.obj({"a": ["raspi", 1, None, True], "b": {"c": f"{home}/f"}}) == \
        {"a": ["pi", 1, None, True], "b": {"c": "~/f"}}


def test_evidence_redacted_local(repo, cli, home):
    code = "import sys, socket; print('host', sys.argv[1], 'devbox', 'ip 192.0.2.33', sys.argv[2])"
    argv = [PY, "-c", code, "devbox.example", f"{home}/data"]
    repo.write_config([{"id": "who", "argv": argv}])
    assert cli("collect") == 0
    [run_id] = repo.runs()
    out = repo.stdout(run_id, "who")
    assert out == b"host devpc devpc ip 192.0.2.x ~/data\n"
    rec = repo.record(run_id, "who")
    assert rec["argv"][-2:] == ["devpc", "~/data"]
    assert rec["stdout_sha256"] == hashlib.sha256(out).hexdigest()
    run_dir = repo.docs / "evidence" / "runs" / run_id
    for p in run_dir.rglob("*"):
        if p.is_file():
            data = p.read_bytes()
            assert str(home).encode() not in data, p
            assert b"devbox" not in data, p
            assert b"192.0.2.33" not in data, p


def test_evidence_redacted_ssh(repo, cli, fake_ssh):
    argv = ["printf", "%s\\n", "name raspi", "fqdn raspi.example", "inet 192.0.2.10"]
    repo.write_config([{"id": "net", "argv": argv, "targets": ["pi"]}], extra_targets=ssh_target())
    assert cli("collect") == 0
    [run_id] = repo.runs()
    assert repo.stdout(run_id, "net", target="pi") == b"name pi\nfqdn pi\ninet 192.0.2.x\n"
    rec = repo.record(run_id, "net", target="pi")
    text = json.dumps(rec)
    assert "raspi" not in text and "192.0.2.10" not in text
    # 가짜 ssh 는 가리기 전의 진짜 값을 받았다
    assert "pi@raspi.example" in fake_ssh.calls()[0]


def test_facts_redacted(repo, cli, fake_ssh):
    facts = [{"key": "net.ip", "extract": "regex", "pattern": r"inet (\S+)", "type": "string"},
             {"key": "net.name", "extract": "regex", "pattern": r"name (\S+)", "type": "string"}]
    argv = ["printf", "%s\\n", "name raspi.example", "inet 192.0.2.10"]
    repo.write_config([{"id": "net", "argv": argv, "targets": ["pi"], "facts": facts}],
                      extra_targets=ssh_target())
    cli("collect")
    assert cli("facts") == 0
    f = repo.facts("pi")
    assert f["net.ip"]["value"] == "192.0.2.x"
    assert f["net.name"]["value"] == "pi"


def test_facts_redacted_from_unredacted_evidence(repo, cli, home):
    # 가리기 전에 남은 증거(예: 1단계 run)에서 뽑아도 사실 파일은 가려진다
    fact = {"key": "path", "extract": "stdout_all", "type": "string"}
    repo.write_config([{"id": "p", "argv": [PY, "-c", "print(1)"], "facts": [fact]}])
    cli("collect")
    [run_id] = repo.runs()
    stdout = repo.docs / "evidence" / "runs" / run_id / "pc" / "p.stdout"
    stdout.write_bytes(f"{home}/x on devbox at 192.0.2.4\n".encode())
    assert cli("facts") == 0
    assert repo.facts()["path"]["value"] == "~/x on devpc at 192.0.2.x"


def test_old_facts_file_scrubbed(repo, cli, home):
    repo.write_config([{"id": "p", "argv": [PY, "-c", "print(1)"],
                        "facts": [{"key": "new", "extract": "stdout_all", "type": "string"}]}])
    repo.docs.joinpath("facts").mkdir()
    old = {"old": {"value": f"{home}/y", "type": "string"}}
    (repo.docs / "facts" / "pc.json").write_text(json.dumps(old), encoding="utf-8")
    cli("collect")
    assert cli("facts") == 0
    assert repo.facts()["old"]["value"] == "~/y"
