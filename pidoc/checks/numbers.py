"""numbers: 문서 원본에 근거 없이 적힌 숫자 찾기.

숫자는 {{fact:키}} 로 넣는 것이 원칙이다. 다음은 문서 구조나 이름의 일부라서 세지 않는다.
  - {{fact:...}}, HTML 주석, 링크 주소
  - 제목 앞 번호(## 3. 설치, ## 2장), 두 자리까지의 번호 목록 표시(1. 2.), 1(또는 0)부터 1씩 느는 표 첫 열 순번
  - 커밋 해시처럼 보이는 7~40자 16진 낱말(851883f) — 해시가 맞는지는 notes 가 따로 본다
  - 본문의 장·절 참조(3장, 2.1절) — '종이 3장'도 넘어가는 미탐은 감수한다
  - 영문 낱말에 붙은 정수(IPv4, x86_64, H2) 와 `UTF-8`·`SHA-256` 처럼 '글자-숫자'
    (Python3.12 처럼 점이 있는 수는 버전이므로 센다. v1.2 도 센다)
  - 설정 check.number_allow 의 구절("Python 3", "HTTP 200" ...)
  - 줄 끝 <!-- pidoc-ok: 이유 --> (이유를 꼭 적는다)

코드(펜스 코드 블록, 인라인 코드)의 숫자도 센다. 버전·포트가 가장 많이 들어가는 곳이기 때문이다.
다만 명령 예시에는 숫자가 흔하므로 등급은 check.code_numbers(기본 warn)를 따르고,
근거가 있으면 펜스 정보 문자열에 pidoc-ok=이유 를 붙이거나 줄 끝에 <!-- pidoc-ok: 이유 --> 를 단다.
pidoc-run·pidoc-quote 블록은 render 가 증거·파일에서 채우므로 세지 않는다.

한글 수사("두 번", "세 가지")와 비교 표현("최신", "빠르다", "크게")은 경고만 한다(제목 줄은 빼고).
"한 번"은 "한 번 실행해 보세요" 같은 관용구가 대부분이라 세지 않는다.
"""

import re

from . import Finding
from .text import COMMENT_RE, INLINE_CODE_RE

NUMBER_RE = re.compile(r"\d+(?:[.,:]\d+)*")
OK_RE = re.compile(r"<!--\s*pidoc-ok:(.*?)-->\s*$")
HEADING_NUM_RE = re.compile(r"^(#{1,6}\s+)(\d{1,2}(?:\.\d{1,2})*\.?|\d{1,2}(?:장|부|절|편|단계))(?=\s|$)")
LIST_RE = re.compile(r"^(\s*)\d{1,2}[.)](?=\s)")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
LINK_TARGET_RE = re.compile(r"\]\([^)]*\)")
REF_DEF_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s")
AUTOLINK_RE = re.compile(r"<(?:https?|mailto):[^>]*>")
FACT_RE = re.compile(r"\{\{fact:[^{}]*\}\}")
HASH_RE = re.compile(r"(?<![0-9A-Za-z])(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{7,40}(?![0-9A-Za-z])")
CHAPTER_RE = re.compile(r"\d+(?:\.\d+)*(?=장|절)")

KOREAN_NUM_RE = re.compile(
    r"(?<![가-힣])(두|세|네|다섯|여섯|일곱|여덟|아홉|열|스무|수십|수백|수천|수만)\s?"
    r"(번|개|가지|줄|초|분|시간|배|대|단계|명|장|쪽|곳|군데|차례|달|해|살|칸|자리)")
VAGUE_WORDS = ["최신", "빠르다", "빠른", "빠르게", "빨라", "크게", "훨씬", "대폭", "가장"]


def _blank(text, pattern):
    """맞는 부분을 같은 길이 공백으로(위치를 지키려고)."""
    return pattern.sub(lambda m: " " * len(m.group(0)), text)


def strip_structure(line, allow, seq=None):
    """세지 않을 부분을 지운 줄. seq: 표 첫 열에서 순번으로 인정할 수(없으면 0·1)."""
    for pattern in (COMMENT_RE, FACT_RE, INLINE_CODE_RE, AUTOLINK_RE, CHAPTER_RE, HASH_RE):
        line = _blank(line, pattern)
    line = LINK_TARGET_RE.sub(lambda m: "]" + " " * (len(m.group(0)) - 1), line)
    m = HEADING_NUM_RE.match(line)
    if m:
        line = m.group(1) + " " * len(m.group(2)) + line[m.end():]
    m = LIST_RE.match(line)
    if m:
        line = " " * m.end() + line[m.end():]
    if line.lstrip().startswith("|"):
        cells = line.split("|")
        m = re.fullmatch(r"\s*(\d+)\.?\s*", cells[1]) if len(cells) > 2 else None
        if m and int(m.group(1)) in ((0, 1) if seq is None else (seq,)):
            cells[1] = " " * len(cells[1])
            line = "|".join(cells)
    for phrase in allow:
        line = line.replace(phrase, " " * len(phrase))
    return line


def _is_name_part(text, start, token):
    """숫자 앞이 영문 낱말이면 이름의 일부(IPv4, x86_64, UTF-8). 단 'v1.2'·'Python3.12' 처럼 점이 있으면 버전."""
    if "." in token:
        return False
    before = text[:start]
    if before.endswith("-") and re.search(r"[A-Za-z]-$", before):
        return True
    m = re.search(r"[A-Za-z_]+$", before)
    if not m:
        return False
    return m.group(0) not in ("v", "V")


def numbers_in(line, allow=(), seq=None):
    text = strip_structure(line, allow, seq)
    return [m.group(0) for m in NUMBER_RE.finditer(text) if not _is_name_part(text, m.start(), m.group(0))]


def code_numbers_in(code, allow=()):
    """코드 조각의 숫자(구조 예외 없이, 사실 참조·이름 일부·해시·number_allow 만 뺀다)."""
    for pattern in (FACT_RE, HASH_RE):
        code = _blank(code, pattern)
    for phrase in allow:
        code = code.replace(phrase, " " * len(phrase))
    return [m.group(0) for m in NUMBER_RE.finditer(code) if not _is_name_part(code, m.start(), m.group(0))]


CODE_HINT = "코드 안 숫자: {} — 근거가 있으면 {{{{fact:키}}}} 로 바꾸거나 펜스에 pidoc-ok=이유 / 줄 끝에 <!-- pidoc-ok: 이유 -->"


def _table_seq(line, prev):
    """표 첫 열 순번 상태. (이 줄에서 기대하는 순번, 다음 상태)"""
    if not line.lstrip().startswith("|"):
        return None, None
    if TABLE_SEP_RE.match(line):
        return None, prev
    cells = line.split("|")
    m = re.fullmatch(r"\s*(\d+)\.?\s*", cells[1]) if len(cells) > 2 else None
    expect = None if prev is None else prev + 1
    if not m:
        return expect, prev
    n = int(m.group(1))
    ok = n in ((0, 1) if prev is None else (prev + 1,))
    return expect, (n if ok else -10)


def scan_doc(d, allow=(), level="error", code_level="warn"):
    """(줄 번호, 검사 수준, 메시지) 목록."""
    results = []
    code_lines = {}                      # 줄 번호 → 검사할 펜스 본문 줄인가
    for f in d.fences:
        reason = f.opts.get("pidoc-ok")
        if reason is not None and not reason.strip():
            results.append((f.start, "error", "pidoc-ok= 에 이유를 적으세요"))
        skip = f.directive is not None or bool(reason)
        for n in range(f.start + 1, (f.end or len(d.lines) + 1)):
            code_lines[n] = not skip
    in_comment = False
    table = None
    for i, line in enumerate(d.lines):
        n = i + 1
        if d.in_fence[i]:
            table = None
            if code_lines.get(n) and code_level != "off" and not OK_RE.search(line):
                found = code_numbers_in(line, allow)
                if found:
                    results.append((n, code_level, CODE_HINT.format(", ".join(found))))
            continue
        if in_comment:
            if "-->" in line:
                in_comment = False
                line = line.split("-->", 1)[1]
            else:
                continue
        if "<!--" in line and "-->" not in line.split("<!--", 1)[1]:
            in_comment = True
            line = line.split("<!--", 1)[0]
        ok = OK_RE.search(line)
        if ok:
            if not ok.group(1).strip():
                results.append((n, "error", "pidoc-ok 에 이유를 적으세요: <!-- pidoc-ok: 이유 -->"))
            continue
        if REF_DEF_RE.match(line):
            continue
        seq, table = _table_seq(line, table)
        found = numbers_in(line, allow, seq)
        if found and level != "off":
            results.append((n, level, f"근거 없는 숫자: {', '.join(found)} — {{{{fact:키}}}} 로 바꾸거나 "
                                      "줄 끝에 <!-- pidoc-ok: 이유 --> 를 다세요"))
        if code_level != "off":
            spans = [m.group(2) for m in INLINE_CODE_RE.finditer(COMMENT_RE.sub("", line))]
            found = [x for span in spans for x in code_numbers_in(span, allow)]
            if found:
                results.append((n, code_level, CODE_HINT.format(", ".join(found))))
        if level == "off" or re.match(r"^#{1,6}\s", line):
            continue                     # 제목은 '빠른 시작' 같은 관용구가 많아 경고하지 않는다
        plain = strip_structure(line, allow)
        for m in KOREAN_NUM_RE.finditer(plain):
            results.append((n, "warn", f"한글 수사 '{m.group(0)}' — 근거가 있는 수인지 보세요"))
        for word in VAGUE_WORDS:
            if word in plain:
                results.append((n, "warn", f"비교 표현 '{word}' — 무엇과 비교해 얼마나인지 근거가 있나요?"))
    return results


def scan_text(text, allow=(), level="error", code_level="warn"):
    """문서 글 하나를 검사(draft 결과 등)."""
    from ..doc import Doc
    return scan_doc(Doc("x.md", text, None), allow, level, code_level)


def run(ctx):
    settings = ctx.cfg.check
    level = settings.get("numbers", "error")
    code_level = settings.get("code_numbers", "warn")
    allow = settings.get("number_allow", [])
    findings = []
    for d in ctx.docs:
        for n, lv, msg in scan_doc(d, allow, level, code_level):
            findings.append(Finding(ctx.cfg.rel(d.path), n, "numbers", msg, lv))
    return findings
