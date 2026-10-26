"""pidoc check: 사실·숫자·인용·출력·내부 정보 검사."""

import sys

from pidoc import blocks
from pidoc.numbers import scan
from pidoc.render import RenderError, Resolver, read_doc, render_text, src_docs
from pidoc.secrets import check_secrets
from pidoc.verify import FactsError, load_all

CHECKS = ("facts", "numbers", "quote", "run", "secrets")


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
        # pidoc 블록 안(채워질 자리)은 보지 않는다
        for line, part in blocks.split(text):
            if not isinstance(part, str):
                continue
            _, errors = render_text(part, res, line)
            for n, ph, why in errors:
                print(f"src/{name}:{n}: {ph} — {why}", file=sys.stderr)
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


def check_blocks(cfg, docs, kind):
    """docs/out 의 pidoc 블록이 지금 파일·최신 증거와 같은지 본다."""
    bad = 0

    def err(msg):
        nonlocal bad
        print(msg, file=sys.stderr)
        bad += 1

    for name, text in docs:
        src_bl = blocks.blocks(text)
        # 먼저 src 쪽(경로·명령)이 올바른지 본다. out 이 없어도 알린다.
        wants = {}
        for i, s in enumerate(src_bl):
            if s.kind != kind:
                continue
            try:
                wants[i] = blocks.content(cfg, s)
            except blocks.BlockError as e:
                err(f"src/{name}:{s.line}: {s.label} — {e}")
        if not wants:
            continue
        out_path = cfg.out_dir / name
        try:
            out_bl = blocks.blocks(read_doc(out_path)) if out_path.is_file() else None
        except RenderError as e:
            err(f"out/{name}: {e}")
            continue
        if out_bl is None:
            err(f"out/{name}: 없음 — pidoc render 를 먼저 할 것")
            continue
        if [(b.kind, b.arg) for b in src_bl] != [(b.kind, b.arg) for b in out_bl]:
            err(f"out/{name}: pidoc 블록이 src 와 다름 — pidoc render 를 다시 할 것")
            continue
        for i, want in wants.items():
            s, o = src_bl[i], out_bl[i]
            got = o.body
            if kind == "run":
                mask = blocks.masker(cfg, s.arg)
                got, want = mask(got), mask(want)
            if got != want:
                what = "인용이 파일과 다름" if kind == "quote" else "출력이 최신 증거와 다름"
                n, a, b = blocks.first_diff(got, want)
                err(f"out/{name}:{o.line}: {s.label} — {what}(블록 {n}번째 줄)\n"
                    f"    문서: {a}\n    지금: {b}")
    return bad


def check(cfg, only=None):
    only = only or list(CHECKS)
    docs, bad = _docs(cfg)
    counts = {}
    if "facts" in only:
        counts["facts"] = check_facts(cfg, docs)
    if "numbers" in only:
        counts["numbers"] = check_numbers(docs)
    for kind in ("quote", "run"):
        if kind in only:
            counts[kind] = check_blocks(cfg, docs, kind)
    if "secrets" in only:
        counts["secrets"] = check_secrets(cfg)
    bad += sum(counts.values())
    print("검사 " + ", ".join(f"{k} {v}건" for k, v in counts.items()) + f" (문서 {len(docs)}개)")
    return 1 if bad else 0
