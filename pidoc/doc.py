"""문서 원본(docs/src/*.md) 읽기: 머리말, 펜스 코드 블록, 사실 참조, 제목 앵커.

Markdown 전체를 해석하지 않고, 검사에 필요한 만큼만 줄 단위로 본다.
"""

import re
from pathlib import Path

FACT_RE = re.compile(r"\{\{fact:([^{}|]*)((?:\|[^{}|]*)*)\}\}")
HEADER_RE = re.compile(r"^<!--\s*pidoc-(target|deps):\s*(.*?)\s*-->\s*$")
FENCE_RE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})(.*)$")


class Fence:
    """펜스 코드 블록 하나. 줄 번호는 1부터."""

    def __init__(self, start, mark, info, indent):
        self.start = start          # 여는 줄
        self.end = None             # 닫는 줄(없으면 문서 끝까지)
        self.mark = mark
        self.info = info.strip()
        self.indent = indent
        self.body = []
        words = self.info.split()
        self.lang = words[0] if words and "=" not in words[0] else ""
        self.opts = dict(w.split("=", 1) for w in words if "=" in w)

    @property
    def directive(self):
        for name in ("pidoc-quote", "pidoc-run"):
            if name in self.opts:
                return name
        return None


class Ref:
    """{{fact:대상:키|변환}} 하나."""

    def __init__(self, match, line, default_target):
        self.text = match.group(0)
        self.line = line
        name = match.group(1).strip()
        self.target, _, self.key = name.rpartition(":")
        self.target = self.target or default_target
        self.transforms = [t.strip() for t in match.group(2).split("|") if t.strip()]

    @property
    def full_key(self):
        return f"{self.target}:{self.key}"


class Doc:
    def __init__(self, path, text, default_target):
        self.path = Path(path)
        self.text = text
        self.lines = text.splitlines()
        self.target = default_target
        self.deps = []
        self.header_lines = 0
        for line in self.lines:
            m = HEADER_RE.match(line)
            if not m:
                break
            self.header_lines += 1
            if m.group(1) == "target":
                self.target = m.group(2)
            else:
                self.deps += [d for d in re.split(r"[,\s]+", m.group(2)) if d]
        self.fences = []
        self.in_fence = [False] * len(self.lines)   # 펜스(여닫는 줄 포함) 안인가
        current = None
        for i, line in enumerate(self.lines):
            n = i + 1
            if current is None:
                m = FENCE_RE.match(line)
                if m and not (m.group(2)[0] == "`" and "`" in m.group(3)):
                    current = Fence(n, m.group(2), m.group(3), m.group(1))
                    self.in_fence[i] = True
                continue
            self.in_fence[i] = True
            stripped = line.strip()
            if stripped and set(stripped) == {current.mark[0]} and len(stripped) >= len(current.mark):
                current.end = n
                self.fences.append(current)
                current = None
            else:
                current.body.append(line)
        if current is not None:
            self.fences.append(current)

    def refs(self):
        """모든 사실 참조(펜스 안 포함 — render 가 거기도 채운다). pidoc 블록 본문은 뺀다."""
        skip = set()
        for f in self.fences:
            if f.directive:
                skip.update(range(f.start + 1, (f.end or len(self.lines) + 1)))
        found = []
        for n, line in enumerate(self.lines, 1):
            if n in skip:
                continue
            found += [Ref(m, n, self.target) for m in FACT_RE.finditer(line)]
        return found


def load(path, default_target):
    path = Path(path)
    return Doc(path, path.read_text(encoding="utf-8"), default_target)


def src_files(cfg, names=None):
    """검사·렌더할 원본 목록. 이름을 주지 않으면 docs/src 아래 *.md 전부."""
    if names:
        files = [Path(n).resolve() for n in names]
        for f in files:
            if not f.is_file():
                from .util import PidocError
                raise PidocError(f"파일이 없습니다: {f}")
        return files
    if not cfg.src_dir.is_dir():
        return []
    return sorted(p.resolve() for p in cfg.src_dir.rglob("*.md"))


def out_path(cfg, src):
    src = Path(src).resolve()
    try:
        return cfg.out_dir / src.relative_to(cfg.src_dir.resolve())
    except ValueError:
        return cfg.out_dir / src.name


def slug(text):
    """GitHub 식 제목 앵커: 소문자, 글자·숫자·한글·-·_ 만 남기고 공백은 -."""
    text = re.sub(r"<[^>]+>", "", text).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(lines, in_fence=None):
    """문서의 제목 앵커 목록(같은 제목은 -1, -2 를 붙인다)."""
    seen, result = {}, set()
    for i, line in enumerate(lines):
        if in_fence and in_fence[i]:
            continue
        m = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        if not m:
            continue
        base = slug(m.group(1))
        n = seen.get(base, 0)
        seen[base] = n + 1
        result.add(base if n == 0 else f"{base}-{n}")
    return result
