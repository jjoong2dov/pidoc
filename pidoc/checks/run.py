"""run: pidoc-run 블록 검사.

- 최신 성공 증거가 있어야 한다.
- 블록에 본문이 있으면 (정규화 후) 최신 증거와 같아야 한다.
- --rerun: 지금 다시 실행해 본다. 본문이 있으면 본문과, 없으면 최신 증거와 비교한다.
"""

from . import Finding
from .. import evidence, mask
from ..collect import describe_failure, execute


def _compare(name, line, label, expected, actual, rules, cmd_id):
    a = mask.normalize_lines(mask.apply(rules, expected))
    b = mask.normalize_lines(mask.apply(rules, actual))
    diff = mask.first_difference(a, b)
    if not diff:
        return []
    n, x, y = diff
    return [Finding(name, line, "run", f"{cmd_id}: {label} 다릅니다({n}번째 줄, 정규화 뒤): {x!r} / {y!r}")]


def run(ctx):
    cfg, findings = ctx.cfg, []
    for d in ctx.docs:
        name = cfg.rel(d.path)
        for fence in d.fences:
            if fence.directive != "pidoc-run":
                continue
            cmd_id = fence.opts["pidoc-run"]
            target_name = fence.opts.get("target", d.target)
            target = cfg.targets.get(target_name)
            run_ = evidence.latest_with(cfg.runs_dir, target_name, cmd_id)
            if run_ is None:
                findings.append(Finding(name, fence.start, "run",
                                        f"{cmd_id}: 대상 {target_name} 의 성공한 증거가 없습니다 — pidoc collect"))
                continue
            stored = run_.stdout(cmd_id).decode("utf-8", errors="replace")
            rules = mask.rules_for(cfg, target)
            body = "\n".join(fence.body)
            if not ctx.rerun:
                if body.strip():
                    findings += _compare(name, fence.start, "최신 증거와", body, stored, rules, cmd_id)
                continue
            cmd = next((c for c in cfg.commands if c["id"] == cmd_id and target_name in c["targets"]), None)
            if cmd is None or target is None:
                findings.append(Finding(name, fence.start, "run", f"{cmd_id}: 설정에 없는 명령·대상이라 다시 실행할 수 없습니다"))
                continue
            result, _, _, _ = execute(cfg, cmd, target)
            if not result.ok(cmd["ok_exit"]):
                record = {"error": result.error, "timed_out": result.timed_out, "exit": result.exit}
                findings.append(Finding(name, fence.start, "run", f"{cmd_id}: 다시 실행 실패 — {describe_failure(record)}"))
                continue
            fresh = result.stdout.decode("utf-8", errors="replace")
            if body.strip():
                findings += _compare(name, fence.start, "지금 실행한 출력과", body, fresh, rules, cmd_id)
            else:
                findings += _compare(name, fence.start, "지금 실행한 출력과", stored, fresh, rules, cmd_id)
    return findings
