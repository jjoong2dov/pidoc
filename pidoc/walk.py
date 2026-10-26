"""walk: 따라 하기 문서 자체를 시험한다(13장 파이 실기용).

렌더된 문서에서 ```sh pidoc-step 펜스만 골라 차례로 대상에서 실행한다. 블록 하나가 한 단계다.
독자는 문서에 쓴 그대로 셸에 칠 것이므로, 이 기능만은 셸을 쓴다:
    bash -e -o pipefail -c '<블록 전체>'
그래서 collect.allow_programs 를 적용하지 않는다(문서에 적힌 명령이 곧 시험 대상이다).
믿을 수 있는 문서만, 시험용 장비·계정에서 돌릴 것.

- 단계 사이에 작업 폴더(cd)는 이어진다. 환경변수(export)는 이어지지 않으니 단계마다 적는다.
- 단계마다 docs/evidence/walks/<id>/ 에 스크립트·stdout·stderr·종료 코드·시간을 남긴다(가리기 적용).
- 실패하면 거기서 멈추고 "N단계 실패" 와 마지막 출력을 보여 주고 종료 3.
"""

import os
import shlex
from pathlib import Path

from . import doc as docmod
from . import evidence, redact, runner
from .collect import cut_partial_line, ssh_options
from .util import COLLECT_FAILED, OK, PidocError, iso, now, sha256_bytes, sha256_file, write_json

CWD_MARK = "__PIDOC_WALK_CWD__="
TAIL_LINES = 10


def steps_of(d):
    """(문서 줄 번호, 블록 글) 목록."""
    return [(f.start, "\n".join(f.body)) for f in d.fences
            if f.lang in ("sh", "bash", "console") and "pidoc-step" in f.info.split()]


def script_for(block, cwd):
    """단계 하나의 스크립트: 앞 단계가 끝난 폴더로 가서 블록을 돌리고, 끝난 폴더를 stderr 끝에 알린다."""
    head = f"cd -- {shlex.quote(cwd)}\n" if cwd else ""
    return f'{head}{block}\nprintf "\\n{CWD_MARK}%s\\n" "$PWD" >&2\n'


def split_cwd(stderr):
    """stderr 끝의 작업 폴더 표시를 떼어 낸다. (stderr, 폴더 또는 None)"""
    text = stderr.decode("utf-8", errors="surrogateescape")
    head, sep, tail = text.rpartition("\n" + CWD_MARK)
    if not sep:
        return stderr, None
    return head.encode("utf-8", errors="surrogateescape"), tail.strip()


def plan(cfg, target, script, cwd):
    """(argv, 로컬 작업 폴더, 환경변수)"""
    c = cfg.collect
    env = runner.build_env(c["env_allow"], c["env_set"])
    bash = ["bash", "-e", "-o", "pipefail", "-c", script]
    if target.kind == "ssh":
        if "SSH_AUTH_SOCK" in os.environ:
            env["SSH_AUTH_SOCK"] = os.environ["SSH_AUTH_SOCK"]
        return ["ssh", *ssh_options(target), "--", target.host, shlex.join(bash)], None, env
    return bash, cwd, env


def walk(cfg, path, target_name, start=1, dry_run=False):
    path = Path(path)
    if not path.is_file():
        raise PidocError(f"문서가 없습니다: {path}")
    target = cfg.target(target_name)
    d = docmod.load(path, cfg.default_target)
    steps = steps_of(d)
    if not steps:
        raise PidocError(f"{path}: ```sh pidoc-step 블록이 없습니다")
    if not 1 <= start <= len(steps):
        raise PidocError(f"--from 은 1~{len(steps)} 이어야 합니다")
    name = cfg.rel(path)
    if dry_run:
        for i, (line, block) in enumerate(steps, 1):
            mark = "건너뜀" if i < start else "실행"
            print(f"[{i}단계 · {name}:{line} · {mark}]")
            for cmd in block.splitlines():
                print(f"  $ {cmd}")
        print(f"(--dry-run: 실행하지 않았습니다. 대상 {target.name}, {len(steps)}단계)")
        return OK

    started = now()
    walk_dir = evidence.new_run_dir(cfg.docs_dir / "evidence" / "walks", target.name, started)
    timeout = cfg.walk.get("timeout_s", 600)
    rules = redact.rules_for(cfg, target)
    if target.kind == "local":
        local_cwd = cfg.inside(target.cwd or ".", f"targets.{target.name}.cwd")
        remote_cwd = None
    else:
        local_cwd, remote_cwd = None, target.cwd
    print(f"[{target.name}] walk {walk_dir.name}: {name} ({len(steps)}단계)")
    records, failed_at = [], None
    for i, (line, block) in enumerate(steps, 1):
        if i < start:
            records.append({"step": i, "line": line, "skipped": True})
            continue
        script = script_for(block, remote_cwd)
        argv, cwd, env = plan(cfg, target, script, local_cwd)
        result = runner.run(argv, cwd=cwd, env=env, timeout=timeout, max_output=cfg.collect["max_output"])
        stderr, new_cwd = split_cwd(result.stderr)
        if new_cwd:
            if target.kind == "local":
                local_cwd = new_cwd
            else:
                remote_cwd = new_cwd
        stdout = cut_partial_line(result.stdout) if result.stdout_truncated else result.stdout
        stdout, n1 = redact.apply_bytes(rules, stdout)
        stderr, n2 = redact.apply_bytes(rules, stderr)
        ok = result.error is None and not result.timed_out and result.exit == 0
        stem = f"step{i:02d}"
        (walk_dir / f"{stem}.sh").write_text(block + "\n", encoding="utf-8")
        (walk_dir / f"{stem}.stdout").write_bytes(stdout)
        (walk_dir / f"{stem}.stderr").write_bytes(stderr)
        record = {
            "step": i, "line": line, "ok": ok, "exit": result.exit, "error": result.error,
            "timed_out": result.timed_out, "duration_ms": result.duration_ms, "finished_at": iso(now()),
            "redacted": n1 + n2,
            "stdout": {"bytes": len(stdout), "sha256": sha256_bytes(stdout), "truncated": result.stdout_truncated},
            "stderr": {"bytes": len(stderr), "sha256": sha256_bytes(stderr), "truncated": result.stderr_truncated},
        }
        write_json(walk_dir / f"{stem}.json", record)
        records.append(record)
        if ok:
            print(f"  {i}단계 통과 ({name}:{line}, {result.duration_ms} ms)")
            continue
        why = result.error or ("시간 초과" if result.timed_out else f"종료 코드 {result.exit}")
        print(f"  {i}단계 실패 ({name}:{line}): {why}")
        tail = (stdout + b"\n" + stderr).decode("utf-8", errors="replace").strip().splitlines()[-TAIL_LINES:]
        for t in tail:
            print(f"    | {t}")
        failed_at = i
        break
    write_json(walk_dir / "manifest.json", {
        "schema": 1, "walk": walk_dir.name, "doc": name, "doc_sha256": sha256_file(path),
        "target": target.name, "alias": target.alias, "kind": target.kind,
        "started_at": iso(started), "finished_at": iso(now()), "from": start,
        "steps": records, "result": "failed" if failed_at else "passed", "failed_step": failed_at,
    })
    if failed_at:
        print(f"{failed_at}단계 실패 — 기록: {cfg.rel(walk_dir)} (고친 뒤 --from {failed_at} 로 이어서)")
        return COLLECT_FAILED
    print(f"모든 단계 통과 — 기록: {cfg.rel(walk_dir)}")
    return OK
