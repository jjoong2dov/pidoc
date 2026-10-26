"""numbers: 문서 원본 본문에 근거 없이 적힌 숫자 찾기.

숫자는 {{fact:키}} 로 넣는 것이 원칙이다. 다음은 문서 구조나 이름의 일부라서 세지 않는다.
  - 펜스 코드 블록, 인라인 코드(`...`), {{fact:...}}, HTML 주석, 링크 주소
  - 제목 앞 번호(## 3. 설치, ## 2장), 번호 목록 표시(1. 2.), 표 첫 열의 순번
  - 본문의 장·절 참조(3장, 2.1절) — '종이 3장'도 넘어가는 미탐은 감수한다
  - 영문 낱말에 붙은 숫자(IPv4, x86_64, H2) 와 `UTF-8`·`SHA-256` 처럼 '글자-숫자'
  - 설정 check.number_allow 의 구절("Python 3", "HTTP 200" ...)
  - 줄 끝 <!-- pidoc-ok: 이유 --> (이유를 꼭 적는다)
v1.2 처럼 v 뒤 숫자는 버전이므로 센다.

한글 수사("두 번", "세 가지")와 비교 표현("최신", "빠르다", "크게")은 경고만 한다(제목 줄은 빼고).
"한 번"은 "한 번 실행해 보세요" 같은 관용구가 대부분이라 세지 않는다.
"""

import re

from . import Finding

NUMBER_RE = re.compile(r"\d+(?:[.,:]\d+)*")
OK_RE = re.compile(r"<!--\s*pidoc-ok:(.*?)-->\s*$")
HEADING_NUM_RE = re.compile(r"^(#{1,6}\s+)(\d+(?:\.\d+)*\.?|\d+(?:장|부|절|편|단계))(?=\s|$)")
LIST_RE = re.compile(r"^(\s*)\d+[.)](?=\s)")
LINK_TARGET_RE = re.compile(r"\]\([^)]*\)")
REF_DEF_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s")
AUTOLINK_RE = re.compile(r"<(?:https?|mailto):[^>]*>")
INLINE_CODE_RE = re.compile(r"(`+)(.+?)\1")
FACT_RE = re.compile(r"\{\{fact:[^{}]*\}\}")
COMMENT_RE = re.compile(r"<!--.*?-->")
CHAPTER_RE = re.compile(r"\d+(?:\.\d+)*(?=장|절)")

KOREAN_NUM_RE = re.compile(
    r"(?<![가-힣])(두|세|네|다섯|여섯|일곱|여덟|아홉|열|스무|수십|수백|수천|수만)\s?"
    r"(번|개|가지|줄|초|분|시간|배|대|단계|명|장|쪽|곳|군데|차례|달|해|살|칸|자리)")
VAGUE_WORDS = ["최신", "빠르다", "빠른", "빠르게", "빨라", "크게", "훨씬", "대폭", "가장"]


def _blank(text, pattern):
    """맞는 부분을 같은 길이 공백으로(위치를 지키려고)."""
    return pattern.sub(lambda m: " " * len(m.group(0)), text)


def strip_structure(line, allow):
    """세지 않을 부분을 지운 줄."""
    for pattern in (COMMENT_RE, FACT_RE, INLINE_CODE_RE, AUTOLINK_RE, CHAPTER_RE):
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
        if len(cells) > 2 and re.fullmatch(r"\s*\d+\.?\s*", cells[1]):
            cells[1] = " " * len(cells[1])
            line = "|".join(cells)
    for phrase in allow:
        line = line.replace(phrase, " " * len(phrase))
    return line


def _is_name_part(text, start):
    """숫자 앞이 영문 낱말이면 이름의 일부(IPv4, x86_64, UTF-8). 단 'v1.2' 는 버전."""
    before = text[:start]
    if before.endswith("-") and re.search(r"[A-Za-z]-$", before):
        return True
    m = re.search(r"[A-Za-z_]+$", before)
    if not m:
        return False
    return m.group(0) not in ("v", "V")


def numbers_in(line, allow=()):
    text = strip_structure(line, allow)
    return [m.group(0) for m in NUMBER_RE.finditer(text) if not _is_name_part(text, m.start())]


def scan_lines(lines, in_fence, allow=(), level="error"):
    """(줄 번호, 검사 수준, 메시지) 목록."""
    results = []
    in_comment = False
    for i, line in enumerate(lines):
        n = i + 1
        if in_fence[i]:
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
        found = numbers_in(line, allow)
        if found and level != "off":
            results.append((n, level, f"근거 없는 숫자: {', '.join(found)} — {{{{fact:키}}}} 로 바꾸거나 "
                                      "줄 끝에 <!-- pidoc-ok: 이유 --> 를 다세요"))
        if level == "off" or re.match(r"^#{1,6}\s", line):
            continue                     # 제목은 '빠른 시작' 같은 관용구가 많아 경고하지 않는다
        plain = strip_structure(line, allow)
        for m in KOREAN_NUM_RE.finditer(plain):
            results.append((n, "warn", f"한글 수사 '{m.group(0)}' — 근거가 있는 수인지 보세요"))
        for word in VAGUE_WORDS:
            if word in plain:
                results.append((n, "warn", f"비교 표현 '{word}' — 무엇과 비교해 얼마나인지 근거가 있나요?"))
    return results


def scan_text(text, allow=(), level="error"):
    """문서 글 하나를 검사(draft 결과 등)."""
    from ..doc import Doc
    d = Doc("x.md", text, None)
    return scan_lines(d.lines, d.in_fence, allow, level)


def run(ctx):
    settings = ctx.cfg.check
    level = settings.get("numbers", "error")
    allow = settings.get("number_allow", [])
    findings = []
    for d in ctx.docs:
        for n, lv, msg in scan_lines(d.lines, d.in_fence, allow, level):
            findings.append(Finding(ctx.cfg.rel(d.path), n, "numbers", msg, lv))
    return findings
