"""links: 상대 링크의 대상 파일과 앵커(#제목)가 있는지. http(s)·mailto 같은 바깥 주소는 보지 않는다."""

import re
from urllib.parse import unquote

from . import Finding
from .text import LINK_RE, prose_lines
from .. import doc as docmod

SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def _anchors(path, cache):
    if path not in cache:
        d = docmod.load(path, None)
        cache[path] = docmod.anchors(d.lines, d.in_fence)
    return cache[path]


def run(ctx):
    findings, cache = [], {}
    for d in ctx.docs:
        name = ctx.cfg.rel(d.path)
        for n, line in prose_lines(d):
            for m in LINK_RE.finditer(line):
                url = m.group(2)
                if not url or SCHEME_RE.match(url) or url.startswith("//"):
                    continue
                path_part, _, anchor = url.partition("#")
                target = (d.path.parent / unquote(path_part)).resolve() if path_part else d.path
                if not target.exists():
                    findings.append(Finding(name, n, "links", f"링크 대상이 없습니다: {url}"))
                    continue
                if anchor and target.suffix == ".md" and unquote(anchor) not in _anchors(target, cache):
                    findings.append(Finding(name, n, "links", f"앵커가 없습니다: {url} ({ctx.cfg.rel(target)} 의 제목을 확인)"))
    return findings
