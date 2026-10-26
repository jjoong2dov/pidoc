"""검사들이 같이 쓰는 본문 줄 다루기."""

import re

INLINE_CODE_RE = re.compile(r"(`+)(.+?)\1")
COMMENT_RE = re.compile(r"<!--.*?-->")
LINK_RE = re.compile(r"!?\[([^\]]*)\]\(\s*<?([^)\s>]*)>?(?:\s+\"[^\"]*\")?\s*\)")


def prose_lines(d):
    """펜스 밖 본문 줄: (줄 번호, 인라인 코드·주석을 지운 줄)."""
    for i, line in enumerate(d.lines):
        if d.in_fence[i]:
            continue
        line = COMMENT_RE.sub("", line)
        line = INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), line)
        yield i + 1, line
