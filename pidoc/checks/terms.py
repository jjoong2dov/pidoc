"""terms: 용어집(docs/terms.toml) 위반. 형식: "바른말" = ["틀린말", ...]

영문 낱말은 낱말 단위로, 대소문자를 구분해 찾는다(GitHub 이 바른말이면 Github 를 잡는다).
"""

import re
import tomllib

from . import Finding
from .text import prose_lines
from ..util import PidocError


def load_terms(path):
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise PidocError(f"{path}: TOML 문법 오류: {e}")
    for right, wrongs in data.items():
        if not isinstance(wrongs, list) or not all(isinstance(w, str) and w for w in wrongs):
            raise PidocError(f"{path}: \"{right}\" 의 값은 틀린말 목록이어야 합니다")
    return data


def _pattern(word):
    if re.fullmatch(r"[\x00-\x7f]+", word):
        return re.compile(r"(?<![A-Za-z0-9_])" + re.escape(word) + r"(?![A-Za-z0-9_])")
    return re.compile(re.escape(word))


def run(ctx):
    path = ctx.cfg.docs_dir / ctx.cfg.check.get("terms", "terms.toml")
    terms = load_terms(path)
    rules = [(right, _pattern(right), wrong, _pattern(wrong)) for right, wrongs in terms.items() for wrong in wrongs]
    findings = []
    for d in ctx.docs:
        name = ctx.cfg.rel(d.path)
        for n, line in prose_lines(d):
            for right, right_re, wrong, wrong_re in rules:
                text = right_re.sub(lambda m: " " * len(m.group(0)), line)   # 바른말 안의 일부는 넘김
                if wrong_re.search(text):
                    findings.append(Finding(name, n, "terms", f"'{wrong}' 대신 '{right}'"))
    return findings
