"""숫자 검사: 잡아야 할 것과 오탐을 줄이려고 넘기는 것을 고정한다."""

import pytest

from pidoc.checks.numbers import numbers_in, scan_text

ALLOW = ["Python 3", "HTTP 200"]


@pytest.mark.parametrize("line, expected", [
    ("5초마다 수집합니다.", ["5"]),
    ("기본 포트는 8080 입니다.", ["8080"]),
    ("pimon v0.3 부터 됩니다.", ["0.3"]),                 # v 뒤는 버전
    ("메모리 3,200 MB", ["3,200"]),
    ("2026-10-26 에 확인", ["2026", "10", "26"]),
    ("http://127.0.0.1:8080/status 를 엽니다", ["127.0.0.1:8080"]),   # 맨 주소는 센다
    ("64bit 커널", ["64"]),
    ("라즈베리 파이 4 에서", ["4"]),
    ("1234567 개", ["1234567"]),                         # 16진 글자가 없으면 해시가 아님
])
def test_catches(line, expected):
    assert numbers_in(line, ALLOW) == expected


@pytest.mark.parametrize("line", [
    "IPv4 만 지원합니다.",
    "UTF-8 로 저장하고 SHA-256 으로 확인",
    "x86_64 와 aarch64 에서",
    "`python3 -m pimon once` 를 실행",                  # 인라인 코드
    "온도는 {{fact:pc:pimon.temp|round1}} 도입니다.",       # 사실 참조
    "[3장](ch03.md#3-설치) 을 보세요",                     # 링크 주소
    "<https://example.org/v2/x>",
    "Python 3 이상, 정상이면 HTTP 200",                   # number_allow
    "<!-- 메모: 42 -->",
    "ch04 태그에서 시작",
    "자세한 것은 12장과 2.1절에서",
    "고침 (851883f), 처음 (a1b2c3d4e5)",                  # 커밋 해시

    "## 3. 설치",
    "## 2장 준비",
    "1. 첫째 할 일",
    "  2) 둘째 할 일",
    "| 1 | 수집 | 끝 |",
])
def test_not_numbers(line):
    assert numbers_in(line, ALLOW) == []


def test_heading_number_only_first():
    assert numbers_in("## 3. 5초마다 모으기", ALLOW) == ["5"]


def test_table_only_first_column():
    assert numbers_in("| 1 | 주기 | 5 |", ALLOW) == ["5"]
    assert numbers_in("| 2 | 주기 | 5 |", ALLOW) == ["2", "5"]      # 표가 2 부터 시작하면 순번이 아니다


def test_scan_code_warns_and_ok_comments():
    text = """\
# 제목

```console
$ uname -r
6.12.47
```

여기 30초는 예시입니다. <!-- pidoc-ok: 설명용 가정값 -->
이유 없는 예외 10 <!-- pidoc-ok: -->
<!--
여러 줄 주석 99
-->
남은 것 7
"""
    found = scan_text(text)
    assert [(n, level) for n, level, _ in found] == [(5, "warn"), (9, "error"), (13, "error")]
    assert "코드 안 숫자: 6.12.47" in found[0][2]                   # 코드 안은 경고(리뷰 7번)
    assert "이유를 적으세요" in found[1][2]
    assert "근거 없는 숫자: 7" in found[2][2]
    assert scan_text(text, code_level="off")[0][0] == 9


def test_korean_numerals_and_vague_words_warn_only():
    found = scan_text("두 번 재시도합니다.\n한 번 실행해 보세요.\n세 번째 줄\n최신 버전이 훨씬 빠르다.\n## 빠른 시작\n")
    msgs = [(n, level, msg.split(" —")[0]) for n, level, msg in found]
    assert msgs == [
        (1, "warn", "한글 수사 '두 번'"),
        (3, "warn", "한글 수사 '세 번'"),
        (4, "warn", "비교 표현 '최신'"),
        (4, "warn", "비교 표현 '빠르다'"),
        (4, "warn", "비교 표현 '훨씬'"),
    ]


def test_level_warn_and_off():
    assert scan_text("5초", level="warn")[0][1] == "warn"
    assert scan_text("5초, 두 번", level="off") == []
