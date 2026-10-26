import json

import pytest

from conftest import PY


def cmd(cid, out, key, extract="stdout_all", type="string", targets=("pc",), **kw):
    return {"id": cid, "argv": [PY, "-c", f"print({out!r}, end='')"], "targets": list(targets),
            "facts": [{"key": key, "extract": extract, "type": type, **kw}]}


COMMANDS = [
    cmd("ver", "Version 1.2.3\n", "app.version", "regex", pattern=r"Version (\S+)"),
    cmd("temp", "t=48.25C\n", "cpu.temp", "regex", "float", pattern=r"t=([\d.]+)"),
    cmd("cores", "cores: 4\n", "cpu.cores", "regex", "int", pattern=r"cores: (\d+)"),
    cmd("mods", "i2c\nspi\n", "kernel.modules", type="list"),
]


@pytest.fixture
def ready(repo, cli):
    """수집하고 사실까지 뽑아 둔 저장소."""
    repo.write_config(COMMANDS)
    assert cli("collect") == 0
    assert cli("facts") == 0
    (repo.docs / "src").mkdir()
    return repo


def src(repo, name, text):
    (repo.docs / "src" / name).write_text(text, encoding="utf-8")


def out(repo, name):
    p = repo.docs / "out" / name
    return p.read_text(encoding="utf-8") if p.exists() else None


def edit_fact(repo, key, value, target="pc"):
    """사람이 사실 파일의 값만 손으로 고친 것처럼 한다(증거·sha256 은 그대로)."""
    p = repo.docs / "facts" / f"{target}.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data[key]["value"] = value
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_render_transforms(ready, cli):
    src(ready, "a.md",
        "버전 {{fact:app.version}}, {{fact:pc:app.version|code}}\n"
        "온도 {{fact:pc:cpu.temp}} / {{fact:cpu.temp|round1}} / {{fact:cpu.temp|int}}\n"
        "코어 {{fact:cpu.cores}}개, 모듈 {{fact:kernel.modules|join}}\n")
    assert cli("render") == 0
    assert out(ready, "a.md") == (
        "버전 1.2.3, `1.2.3`\n"
        "온도 48.25 / 48.3 / 48\n"
        "코어 4개, 모듈 i2c, spi\n")


@pytest.mark.parametrize("text, why", [
    ("{{fact:no.such}}", "사실이 없음"),
    ("{{fact:zz:app.version}}", "사실이 없음"),
    ("{{fact:app.version|round1}}", "숫자"),
    ("{{fact:app.version|join}}", "목록"),
    ("{{fact:cpu.temp|join}}", "목록"),
    ("{{fact:kernel.modules}}", "join"),
    ("{{fact:app.version|upper}}", "변환"),
    ("{{fact:}}", "키"),
])
def test_render_errors_write_nothing(ready, cli, capsys, text, why):
    src(ready, "a.md", f"첫 줄\n값 {text}\n")
    assert cli("render") == 1
    assert out(ready, "a.md") is None
    err = capsys.readouterr().err
    assert "a.md:2:" in err and why in err


def test_one_bad_doc_blocks_all(ready, cli):
    src(ready, "a.md", "{{fact:app.version}}\n")
    src(ready, "b.md", "{{fact:no.such}}\n")
    assert cli("render") == 1
    assert out(ready, "a.md") is None and out(ready, "b.md") is None


def test_ambiguous_key_needs_target(repo, cli, capsys):
    repo.write_config([cmd("ver", "Version 1.0\n", "app.version", "regex",
                           pattern=r"Version (\S+)", targets=("pc", "pc2"))],
                      extra_targets='[targets.pc2]\nkind = "local"\n')
    cli("collect")
    assert cli("facts") == 0
    (repo.docs / "src").mkdir()
    src(repo, "a.md", "{{fact:app.version}}\n")
    assert cli("render") == 1
    assert "대상" in capsys.readouterr().err
    src(repo, "a.md", "{{fact:pc2:app.version}}\n")
    assert cli("render") == 0
    assert out(repo, "a.md") == "1.0\n"


def test_no_src_dir(repo, cli):
    repo.write_config(COMMANDS)
    assert cli("render") == 2


# --- 손으로 고친 사실 ---

def test_hand_edited_value_caught_by_render(ready, cli, capsys):
    src(ready, "a.md", "온도 {{fact:cpu.temp|round1}}도\n")
    assert cli("render") == 0
    assert out(ready, "a.md") == "온도 48.3도\n"

    edit_fact(ready, "cpu.temp", 45.0)
    capsys.readouterr()
    assert cli("render") == 1
    err = capsys.readouterr().err
    assert "cpu.temp" in err and "증거와 다름" in err and "45.0" in err and "48.25" in err
    # 이전 결과는 그대로 둔다
    assert out(ready, "a.md") == "온도 48.3도\n"


def test_hand_edited_value_first_render_writes_nothing(ready, cli):
    src(ready, "a.md", "버전 {{fact:app.version}}\n")
    edit_fact(ready, "app.version", "1.2.4")
    assert cli("render") == 1
    assert out(ready, "a.md") is None


def test_hand_edited_value_caught_by_check(ready, cli, capsys):
    src(ready, "a.md", "온도 {{fact:cpu.temp|round1}}도\n")
    assert cli("check", "--only", "facts") == 0
    edit_fact(ready, "cpu.temp", 45.0)
    assert cli("check", "--only", "facts") == 1
    err = capsys.readouterr().err
    assert "pc:cpu.temp" in err and "증거와 다름" in err
    # 숫자 검사는 사실과 상관없다
    assert cli("check", "--only", "numbers") == 0


def test_check_catches_unused_edited_fact(ready, cli, capsys):
    # 문서에 안 쓰인 사실도 check 는 본다. render 는 쓰는 사실만 본다.
    src(ready, "a.md", "버전 {{fact:app.version}}\n")
    edit_fact(ready, "cpu.cores", 8)
    assert cli("render") == 0
    assert cli("check", "--only", "facts") == 1
    assert "pc:cpu.cores" in capsys.readouterr().err


@pytest.mark.parametrize("key, value", [
    ("cpu.temp", "48.25"),      # 값은 같고 타입만 다름
    ("cpu.cores", 4.0),
    ("kernel.modules", ["i2c"]),
    ("kernel.modules", "i2c, spi"),
])
def test_hand_edited_type_caught(ready, cli, key, value):
    src(ready, "a.md", "없음\n")
    edit_fact(ready, key, value)
    assert cli("check", "--only", "facts") == 1


def test_value_and_evidence_both_edited(ready, cli, capsys):
    # 증거까지 고쳐 맞추면 sha256 이 어긋난다
    src(ready, "a.md", "온도 {{fact:cpu.temp}}\n")
    edit_fact(ready, "cpu.temp", 45.0)
    [run_id] = ready.runs()
    (ready.docs / "evidence" / "runs" / run_id / "pc" / "temp.stdout").write_bytes(b"t=45.0C\n")
    assert cli("render") == 1
    assert "sha256" in capsys.readouterr().err


def test_fact_pointing_to_missing_run(ready, cli, capsys):
    p = ready.docs / "facts" / "pc.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["app.version"]["run"] = "../x"
    p.write_text(json.dumps(data), encoding="utf-8")
    assert cli("check", "--only", "facts") == 1
    assert "run" in capsys.readouterr().err


def test_broken_facts_file(ready, cli):
    (ready.docs / "facts" / "pc.json").write_text("{깨짐", encoding="utf-8")
    src(ready, "a.md", "없음\n")
    assert cli("render") == 1
    assert cli("check", "--only", "facts") == 1
