import pytest

from pidoc.numbers import scan

# (줄, 잡혀야 할 숫자들). 잡힘이 맞는지는 보고서 표에 적는다.
CASES = [
    # 빠져야 하는 것
    ("## 3. 설치", []),
    ("### 3.2 설정 파일", []),
    ("자세한 내용은 3장을 보세요.", []),
    ("2.1절과 제4장을 참고한다.", []),
    ("3 장과 4장", []),
    ("IPv4 주소만 쓴다.", []),
    ("파일은 UTF-8 로 저장한다.", []),
    ("SHA-256 으로 확인한다.", []),
    ("1. 전원을 켠다.", []),
    ("  2) 로그인한다.", []),
    ("10. 열 번째 단계", []),
    ("x86_64, ARM64, eth0, python3", []),
    ("온도는 {{fact:pc:cpu.temp|round1}}도", []),
    ("최대 3번 다시 한다. <!-- pidoc-ok: 설정 기본값 -->", []),
    # 잡혀야 하는 것
    ("온도는 48.3도", ["48.3"]),
    ("## Python 3.11 설치", ["3.11"]),
    ("## 3. Python 3.11 설치", ["3.11"]),
    ("1. Python 3.11 을 깐다.", ["3.11"]),
    ("메모리는 512MB, 디스크는 1,024개 블록", ["512", "1,024"]),
    ("버전 v1.2.3 을 쓴다.", ["1.2.3"]),
    ("Python3.11 이 있다.", ["3.11"]),
    ("버전3 이후", ["3"]),
    ("1.5배 빠르다", ["1.5"]),
    ("ping 192.0.2.1", ["192.0.2.1"]),
    ("최대 3번 다시 한다. <!-- pidoc-ok: -->", ["3"]),
    ("최대 3번 다시 한다. <!-- 메모 -->", ["3"]),
    # 오탐(숫자지만 사실이 아님) — 지금 규칙으로는 잡힌다
    ("그림 3 을 보라", ["3"]),
    ("2단계에서 만든다", ["2"]),
    ("Raspberry Pi 4 에서", ["4"]),
    ("H.264 영상", ["264"]),
    ("https://example.com/v2/docs", ["2"]),
    ("2026년 1월에 썼다", ["2026", "1"]),
    # 미탐(사실일 수 있는데 빠진다)
    ("Debian-12 에서 돌린다", []),
    ("커널 rc5 를 쓴다", []),
]


@pytest.mark.parametrize("line, expected", CASES)
def test_scan_line(line, expected):
    assert [lit for _, _, lit in scan(line + "\n")] == expected


def test_scan_positions():
    assert scan("머리\n\n온도는 48.3도\n") == [(3, 5, "48.3")]


def test_code_block():
    text = (
        "```console\n"
        "# 3 번째 주석\n"
        "1. 목록 아님\n"
        "$ ping -c 4 192.0.2.1\n"
        "```\n"
        "## 4. 끝\n"
    )
    assert [(n, lit) for n, _, lit in scan(text)] == [
        (2, "3"), (3, "1"), (4, "4"), (4, "192.0.2.1")]


def test_fence_info_line_skipped():
    assert scan("```python pidoc-quote=a.py#L10-L24\nx = 1\n```\n") == [(2, 5, "1")]


@pytest.fixture
def docs(repo):
    repo.write_config([])
    (repo.docs / "src").mkdir()
    return repo


def test_check_numbers_cli(docs, cli, capsys):
    (docs.docs / "src" / "a.md").write_text("## 3. 설치\n온도는 48.3도\n", encoding="utf-8")
    assert cli("check", "--only", "numbers") == 1
    err = capsys.readouterr().err
    assert "a.md:2:5:" in err and "48.3" in err and "pidoc-ok" in err


def test_check_numbers_ok(docs, cli):
    (docs.docs / "src" / "a.md").write_text(
        "## 3. 설치\n온도는 48.3도 <!-- pidoc-ok: 예시 값 -->\n", encoding="utf-8")
    assert cli("check", "--only", "numbers") == 0
    assert cli("check") == 0
