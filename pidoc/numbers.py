"""숫자 검사: 문서 원본에 손으로 적은 숫자 리터럴을 찾는다."""

import re

from pidoc.render import PLACEHOLDER_RE

NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
FENCE_RE = re.compile(r"^\s{0,3}(```+|~~~+)")
HEAD_NUM_RE = re.compile(r"^\s{0,3}#{1,6}[ \t]+(\d+(?:\.\d+)*\.?)(?=\s|$)")
LIST_NUM_RE = re.compile(r"^\s*(\d+[.)])(?=\s)")
# 3장, 2.1절, 제4장, 3 장
REF_RE = re.compile(r"(?:제\s*)?\d+(?:\.\d+)*\s*(?:장|절)")
OK_RE = re.compile(r"<!--\s*pidoc-ok:\s*(?!-->)\S.*?-->\s*$")
# 숫자 바로 앞의 영문 식별자(IPv4, UTF-8, x86_64, eth0)
NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*$")


def _blank(m):
    return " " * len(m.group(0))


def _blank_group(s, m):
    a, b = m.span(1)
    return s[:a] + " " * (b - a) + s[b:]


def scan(text):
    """[(줄, 열, 숫자)]. 열은 1부터."""
    found = []
    fence = None
    for n, line in enumerate(text.splitlines(), 1):
        f = FENCE_RE.match(line)
        if f:
            mark = f.group(1)
            if fence is None:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence) and not line.strip()[len(mark):]:
                fence = None
            continue  # 울타리 줄(정보 문자열)은 보지 않는다
        if OK_RE.search(line):
            continue
        s = PLACEHOLDER_RE.sub(_blank, line)
        if fence is None:
            for rx in (HEAD_NUM_RE, LIST_NUM_RE):
                m = rx.match(s)
                if m:
                    s = _blank_group(s, m)
            s = REF_RE.sub(_blank, s)
        for m in NUM_RE.finditer(s):
            lit = m.group(0)
            name = NAME_RE.search(s, 0, m.start())
            # 이름 속 숫자는 뺀다. 단 v1 같은 버전 표기와 점이 든 숫자는 남긴다.
            if name and name.group(0).lower() != "v" and "." not in lit:
                continue
            found.append((n, m.start() + 1, lit))
    return found
