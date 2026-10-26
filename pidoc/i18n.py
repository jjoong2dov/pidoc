"""i18n-check: 원본과 번역본에서 바뀌면 안 되는 것이 같은지 본다.

코드 블록(언어·본문), 인라인 코드, {{...}} 자리표시자, 링크 주소, 본문 숫자.
"""

import os
import re
from collections import Counter
from pathlib import Path

from .checks.numbers import numbers_in
from .checks.text import INLINE_CODE_RE, LINK_RE
from .doc import Doc
from .util import CHECK_FAILED, OK, PidocError

PLACEHOLDER_RE = re.compile(r"\{\{[^{}]*\}\}")
# 한국어 '3장'·'2.1절'은 숫자 검사에서 빠지므로, 영어 쪽의 'Chapter 3'·'Section 2.1'도 똑같이 뺀다
EN_CHAPTER_RE = re.compile(r"(?i)\b(?:chapter|section|ch\.)\s+\d+(?:\.\d+)*")


def _link_target(d, url):
    """상대 링크는 문서 위치 기준으로 가리키는 파일을 풀어서 비교한다.
    번역본을 다른 폴더(src/en/)에 두면 '../reference.md' 처럼 글자는 달라도 같은 파일을 가리킨다.
    (번역을 시킬 때 그렇게 고쳐도 된다고 허락했는데 글자 비교로 오류가 났다)"""
    if re.match(r"^[a-z][a-z0-9+.-]*:|^#|^/", url):
        return url
    path, sep, anchor = url.partition("#")
    if not path:
        return url
    target = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(d.path)), path))
    return os.path.relpath(target) + sep + anchor   # 화면에는 지금 폴더 기준으로


def _items(d):
    """비교할 것들: {종류: [(줄, 값)]}"""
    items = {"code": [], "inline": [], "placeholder": [], "link": [], "number": []}
    for f in d.fences:
        items["code"].append((f.start, (f.lang, "\n".join(line.rstrip() for line in f.body))))
    for i, line in enumerate(d.lines):
        n = i + 1
        if d.in_fence[i]:
            continue
        items["placeholder"] += [(n, m.group(0)) for m in PLACEHOLDER_RE.finditer(line)]
        items["inline"] += [(n, m.group(2).strip()) for m in INLINE_CODE_RE.finditer(line)]
        items["link"] += [(n, _link_target(d, m.group(2))) for m in LINK_RE.finditer(line)]
        items["number"] += [(n, num) for num in numbers_in(EN_CHAPTER_RE.sub("", line))]
    return items


NAMES = {"code": "코드 블록", "inline": "인라인 코드", "placeholder": "자리표시자", "link": "링크 주소", "number": "숫자"}


def compare(orig, trans):
    """(줄, 메시지) 목록. 줄은 번역본 기준(없으면 원본 기준으로 '원본 n줄')."""
    a, b = _items(orig), _items(trans)
    problems = []
    blocks_a, blocks_b = a.pop("code"), b.pop("code")
    for i in range(max(len(blocks_a), len(blocks_b))):
        if i >= len(blocks_b):
            problems.append((None, f"코드 블록이 빠졌습니다(원본 {blocks_a[i][0]}줄)"))
        elif i >= len(blocks_a):
            problems.append((blocks_b[i][0], "원본에 없는 코드 블록"))
        elif blocks_a[i][1] != blocks_b[i][1]:
            problems.append((blocks_b[i][0], f"코드 블록이 원본({blocks_a[i][0]}줄)과 다릅니다"))
    for kind in a:
        ca = Counter(v for _, v in a[kind])
        cb = Counter(v for _, v in b[kind])
        for value in sorted((ca - cb).elements()):
            line = next(n for n, v in a[kind] if v == value)
            problems.append((None, f"{NAMES[kind]} {value!r} 가 번역본에 없습니다(원본 {line}줄)"))
        for value in sorted((cb - ca).elements()):
            line = next(n for n, v in b[kind] if v == value)
            problems.append((line, f"원본에 없는 {NAMES[kind]} {value!r}"))
    return problems


def i18n_check(orig_path, trans_path):
    paths = [Path(orig_path), Path(trans_path)]
    for p in paths:
        if not p.is_file():
            raise PidocError(f"파일이 없습니다: {p}")
    orig, trans = (Doc(p, p.read_text(encoding="utf-8"), None) for p in paths)
    problems = compare(orig, trans)
    for line, msg in problems:
        where = f"{trans_path}:{line}:" if line else f"{trans_path}:"
        print(f"{where} [i18n] {msg}")
    print(f"번역 검사: 문제 {len(problems)}개")
    return CHECK_FAILED if problems else OK
