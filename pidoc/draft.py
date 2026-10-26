"""pidoc draft: 틀과 사실 목록으로 프롬프트를 만들어 AI 에 보내고 호출 기록을 남긴다."""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

from pidoc import clock, runner
from pidoc.collect import new_run_dir, write_json
from pidoc.redact import Redactor

AI_ARGV = {"claude": ["claude", "-p"], "codex": ["codex", "exec", "-"]}
AI_TIMEOUT_S = 600
AI_MAX_OUTPUT = 8 * 1024 * 1024
PLACEHOLDER_RE = re.compile(r"\{\{fact:[^}]*\}\}")

RULES = """\
아래 틀을 채워 기술문서 초안을 마크다운으로 써라.
- 버전·수치·명령 출력 같은 값은 직접 쓰지 말고 사실 자리표시자 {{fact:대상:키}} 로 쓴다.
- 사실 목록에 없는 값은 지어내지 말고 "TODO: 확인 필요" 로 남긴다.
- 틀의 머리글 구조는 그대로 둔다.
- 설명 없이 문서 본문만 낸다.
"""


def load_facts(cfg):
    """[(대상, 키, 값, 타입)]. 대상은 설정 순서, 키는 정렬."""
    rows = []
    for tname in cfg.targets:
        path = cfg.facts_dir / f"{tname}.json"
        if not path.is_file():
            continue
        facts = json.loads(path.read_text(encoding="utf-8"))
        for key in sorted(facts):
            rows.append((tname, key, facts[key].get("value"), facts[key].get("type")))
    return rows


def build_prompt(template_name, template, facts):
    lines = [RULES, "## 사실 목록 (대상:키 = 값  (타입))"]
    for tname, key, value, ftype in facts:
        lines.append(f"{tname}:{key} = {json.dumps(value, ensure_ascii=False)}  ({ftype})")
    if not facts:
        lines.append("(사실 없음)")
    lines += ["", f"## 틀 ({template_name})", ""]
    return "\n".join(lines) + template


def numeric_lines(text):
    """자리표시자를 뺀 뒤 숫자가 남은 줄 [(줄 번호, 줄)]."""
    return [(n, ln) for n, ln in enumerate(text.splitlines(), 1)
            if re.search(r"\d", PLACEHOLDER_RE.sub("", ln))]


def _rel(path, root):
    p = Path(path).resolve()
    try:
        return str(p.relative_to(root))
    except ValueError:
        return p.name


def draft(cfg, template, out, ai):
    if ai != "none" and not out:
        print(f"--ai {ai} 에는 --out 이 필요함", file=sys.stderr)
        return 2
    try:
        tpl = Path(template).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"틀을 읽지 못함: {template}: {e}", file=sys.stderr)
        return 2

    facts = load_facts(cfg)
    prompt = build_prompt(Path(template).name, tpl, facts)
    started = clock.now()
    ai_dir = cfg.docs / "ai"
    _, log_dir = new_run_dir(ai_dir, clock.run_stamp(started) + "-draft")
    (log_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    meta = {
        "tool": ai,
        "argv": AI_ARGV.get(ai),
        "template": _rel(template, cfg.root),
        "out": _rel(out, cfg.root) if out else None,
        "facts": len(facts),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "started_at": clock.iso(started),
        "exit_code": None,
    }
    red = Redactor.from_config(cfg)
    shown = _rel(log_dir, cfg.root)

    if ai == "none":
        write_json(log_dir / "meta.json", red.obj(meta))
        print(f"프롬프트만 저장함: {shown}/prompt.txt")
        return 0

    r = runner.run(AI_ARGV[ai], env=dict(os.environ), cwd=cfg.root, timeout_s=AI_TIMEOUT_S,
                   max_output=AI_MAX_OUTPUT, stdin_data=prompt.encode("utf-8"))
    (log_dir / "raw.txt").write_bytes(r.stdout)
    (log_dir / "stderr.txt").write_bytes(r.stderr)
    error = r.error
    if error is None and r.exit_code != 0:
        error = f"종료 코드 {r.exit_code}"
    if error is None and r.stdout_truncated:
        error = f"출력이 {AI_MAX_OUTPUT}바이트를 넘어 잘림"
    text = None
    if error is None:
        try:
            text = r.stdout.decode("utf-8")
        except UnicodeDecodeError:
            error = "출력이 UTF-8 이 아님"
    nums = numeric_lines(text) if text is not None else []
    meta.update({
        "finished_at": clock.iso(clock.now()),
        "duration_s": r.duration_s,
        "exit_code": r.exit_code,
        "timed_out": r.timed_out,
        "error": error,
        "ok": error is None,
        "raw_sha256": hashlib.sha256(r.stdout).hexdigest(),
        "numeric_lines": [n for n, _ in nums],
    })
    write_json(log_dir / "meta.json", red.obj(meta))

    if error is not None:
        print(f"AI 호출 실패({ai}): {error} — 기록: {shown}", file=sys.stderr)
        return 3
    Path(out).write_bytes(r.stdout)
    print(f"초안 저장: {out} (기록: {shown})")
    if nums:
        print(f"숫자 리터럴이 있는 줄 {len(nums)}개 — 사실 자리표시자로 바꿀지 볼 것:")
        for n, ln in nums:
            print(f"  {n}: {ln}")
    return 0
