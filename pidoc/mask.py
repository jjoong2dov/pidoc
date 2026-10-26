"""비교용 정규화(mask): 실행할 때마다 바뀌는 값을 자리표시로 바꾼다.

설정 [mask]
  time = true       2026-10-26T23:15:02+09:00, 23:15:02, 2026-10-26 → <time>
  hostname = true   대상 alias 와 실제 hostname → <host>
  pid = true        pid=1234, name[1234] → <pid>
  patterns = [ { re = '"temp": [0-9.]+', to = '"temp": <n>' } ]   그 밖의 값(온도 등)
비교에만 쓴다. 문서에 나가는 출력은 바꾸지 않는다.
"""

import re

from . import redact

TIME_RES = [
    re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?"),
    re.compile(r"\d{4}-\d{2}-\d{2}"),
    re.compile(r"(?<![\d:])\d{1,2}:\d{2}:\d{2}(?:\.\d+)?(?![\d:])"),
]
PID_RES = [
    (re.compile(r"(?i)\b(pid[=: ]+)\d+"), r"\1<pid>"),
    (re.compile(r"([A-Za-z0-9_.-]+)\[\d+\]"), r"\1[<pid>]"),
]


def rules_for(cfg, target):
    m = cfg.mask
    rules = []
    if m.get("time", True):
        rules += [(p, "<time>") for p in TIME_RES]
    if m.get("pid", True):
        rules += PID_RES
    if m.get("hostname", True) and target is not None:
        names = redact.real_names(cfg, target) + [target.alias]
        rules += [(redact.name_pattern(n), "<host>") for n in sorted(set(names), key=lambda n: (-len(n), n))]
    rules += [(re.compile(p["re"]), p["to"]) for p in m.get("patterns", [])]
    return rules


def apply(rules, text):
    for pattern, to in rules:
        text = pattern.sub(to, text)
    return text


def normalize_lines(text):
    """끝 공백과 끝 빈 줄은 비교하지 않는다."""
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return lines


def first_difference(a, b):
    """두 줄 목록이 처음 다른 곳. 같으면 None. (줄 번호, a 줄, b 줄)"""
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else "(없음)"
        y = b[i] if i < len(b) else "(없음)"
        if x != y:
            return i + 1, x, y
    return None
