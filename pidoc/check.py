"""pidoc check: 사실·숫자 검사."""

import sys

from pidoc.numbers import scan
from pidoc.render import RenderError, Resolver, read_doc, render_text, src_docs
from pidoc.verify import FactsError, load_all

CHECKS = ("facts", "numbers")


def _docs(cfg):
    """[(이름, 본문)]. 읽지 못한 문서는 알리고 센다."""
    docs, bad = [], 0
    if cfg.src_dir.is_dir():
        for path in src_docs(cfg):
            try:
                docs.append((path.name, read_doc(path)))
            except RenderError as e:
                print(f"src/{path.name}: {e}", file=sys.stderr)
                bad += 1
    return docs, bad


def check_facts(cfg, docs):
    try:
        res = Resolver(cfg, load_all(cfg))
    except FactsError as e:
        print(e, file=sys.stderr)
        return 1
    bad = 0
    # 문서에 안 쓰인 사실도 모두 본다
    for tname, facts in res.facts.items():
        for key in sorted(facts):
            why = res.verified(tname, key)
            if why:
                print(f"사실 {tname}:{key} — {why}", file=sys.stderr)
                bad += 1
    for name, text in docs:
        _, errors = render_text(text, res)
        for line, ph, why in errors:
            print(f"src/{name}:{line}: {ph} — {why}", file=sys.stderr)
        bad += len(errors)
    return bad


def check_numbers(docs):
    bad = 0
    for name, text in docs:
        lines = text.splitlines()
        for n, col, lit in scan(text):
            print(f"src/{name}:{n}:{col}: 숫자 '{lit}' — 사실 자리표시자로 바꾸거나 "
                  f"줄 끝에 <!-- pidoc-ok: 이유 --> 를 붙일 것", file=sys.stderr)
            print(f"    {lines[n - 1].strip()}", file=sys.stderr)
            bad += 1
    return bad


def check(cfg, only=None):
    only = only or list(CHECKS)
    docs, bad = _docs(cfg)
    counts = {}
    if "facts" in only:
        counts["facts"] = check_facts(cfg, docs)
    if "numbers" in only:
        counts["numbers"] = check_numbers(docs)
    bad += sum(counts.values())
    print("검사 " + ", ".join(f"{k} {v}건" for k, v in counts.items()) + f" (문서 {len(docs)}개)")
    return 1 if bad else 0
