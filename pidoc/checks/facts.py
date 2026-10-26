"""facts: 사실 참조 검사 — 없는 키, 변환·타입, 만료, 쓰이지 않는 사실(경고)."""

from . import Finding
from ..render import RenderError, resolve

# 코드·git·시험에서 자동으로 뽑는 사실은 많아서 '쓰이지 않음' 경고에서 뺀다
AUTO_TARGETS = ("code", "git", "test")


def run(ctx):
    findings, used = [], set()
    for d in ctx.docs:
        for ref in d.refs():
            try:
                resolve(ref, ctx.facts, ctx.now)
            except RenderError as e:
                findings.append(Finding(ctx.cfg.rel(d.path), ref.line, "facts", str(e)))
            used.add(ref.full_key)
    if ctx.all_files and ctx.cfg.check.get("unused_facts", "warn") == "warn":
        for target, items in sorted(ctx.facts.items()):
            if target in AUTO_TARGETS:
                continue
            for key in sorted(items):
                if f"{target}:{key}" not in used:
                    path = ctx.cfg.rel(ctx.cfg.facts_dir / f"{target}.json")
                    findings.append(Finding(path, None, "facts", f"문서에서 쓰이지 않는 사실: {target}:{key}", "warn"))
    return findings
