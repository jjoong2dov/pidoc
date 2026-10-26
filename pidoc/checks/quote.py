"""quote: pidoc-quote 블록이 실제 파일과 같은지(끝 공백·끝 빈 줄은 무시)."""

from . import Finding
from ..mask import first_difference, normalize_lines
from ..render import RenderError, quote_lines


def run(ctx):
    findings = []
    for d in ctx.docs:
        name = ctx.cfg.rel(d.path)
        for fence in d.fences:
            if fence.directive != "pidoc-quote":
                continue
            spec = fence.opts["pidoc-quote"]
            try:
                lines, _ = quote_lines(ctx.cfg, spec)
            except RenderError as e:
                findings.append(Finding(name, fence.start, "quote", str(e)))
                continue
            body = normalize_lines("\n".join(fence.body))
            if not body:
                continue                       # 비어 있으면 render 가 채운다
            diff = first_difference(body, normalize_lines("\n".join(lines)))
            if diff:
                n, mine, real = diff
                findings.append(Finding(name, fence.start + n, "quote",
                                        f"인용이 {spec} 와 다릅니다(블록 {n}번째 줄): 문서 {mine!r} / 파일 {real!r}"))
    return findings
