"""collect·replay: 명령을 대상에서 실행 → 증거 저장 → 사실 추출 → facts 갱신."""

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from . import evidence, facts, redact, runner
from .util import COLLECT_FAILED, OK, PidocError, iso, now

SSH_OPTIONS = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10"]


def say(msg):
    print(msg, flush=True)


# 인라인 코드를 실행하는 옵션. allow_programs 를 무의미하게 만들므로 막는다(완전한 목록은 아니다).
INLINE_CODE_FLAGS = {
    "python": ("-c",), "perl": ("-e", "-E"), "ruby": ("-e",), "node": ("-e", "-p", "--eval", "--print"),
    "php": ("-r",), "lua": ("-e",),
}
SENSITIVE_RE = re.compile(r"^--?(?:[a-z0-9]+[-_])*(?:token|password|passwd|pass|secret|api[-_]?key|key|auth|credentials?)$",
                          re.IGNORECASE)


def check_program(cfg, argv, target):
    """allow_programs 안의 프로그램만 실행한다(이름만 비교, 경로 금지).

    이것은 보안 경계가 아니라 실수 방지 목록이다. python3 을 허용하면 python3 이 할 수 있는 일은 다 할 수 있다.
    그래도 흔한 우회(python3 -c, perl -e 같은 인라인 코드)는 막는다.
    로컬은 목록이 비어 있으면 검사하지 않는다. ssh 는 원격 셸이 명령 줄을 해석하므로 목록이 꼭 있어야 한다.
    """
    allowed = cfg.collect["allow_programs"]
    if not allowed:
        if target.kind == "ssh":
            raise PidocError("ssh 대상은 collect.allow_programs 가 꼭 있어야 합니다")
        return
    program = argv[0]
    if "/" in program or program not in allowed:
        raise PidocError(f"허용 목록(collect.allow_programs)에 없는 프로그램: {program}")
    family = re.sub(r"[\d.]+$", "", program)          # python3.11 → python
    flags = INLINE_CODE_FLAGS.get(family, ())
    for a in argv[1:]:
        if a == "-m" or not a.startswith("-"):
            break                    # 여기부터는 실행할 모듈·스크립트의 인자
        if any(a == f or (not a.startswith("--") and a.startswith(f)) for f in flags):
            raise PidocError(f"인라인 코드 실행({a})은 쓸 수 없습니다: {program} — 스크립트 파일로 만들어 저장소에 두세요")


def public_argv(argv):
    """공개 증거에 남길 argv: --token 값·--password=값 같은 민감한 값은 가린다."""
    out, hide_next = [], False
    for a in argv:
        if hide_next:
            out.append("<가림>")
            hide_next = False
            continue
        name, eq, _ = a.partition("=")
        if SENSITIVE_RE.match(name):
            if eq:
                out.append(f"{name}=<가림>")
                continue
            hide_next = True
        out.append(a)
    return out


def public_command(cmd):
    """manifest 에 남길 명령 정의 사본(argv 가림)."""
    return dict(cmd, argv=public_argv(cmd["argv"]))


def ssh_argv(cfg, cmd, target):
    """ssh 로 보낼 argv. 원격 명령은 shlex.join 으로 한 줄로 만든다.

    ssh 는 명령을 원격 셸에 문자열로 넘기므로 따옴표 처리는 shlex 에 맡기고,
    무엇을 실행할지는 allow_programs 로 막는다.
    """
    remote = list(cmd["argv"])
    env_set = cfg.collect["env_set"]
    if env_set:
        remote = ["env", *[f"{k}={v}" for k, v in sorted(env_set.items())], *remote]
    line = shlex.join(remote)
    cwd = cmd.get("cwd") or target.cwd
    if cwd:
        line = f"cd {shlex.quote(cwd)} && {line}"
    return ["ssh", *SSH_OPTIONS, "--", target.host, line]


def plan(cfg, cmd, target):
    """(실행할 argv, 로컬 작업 폴더, 환경변수)"""
    check_program(cfg, cmd["argv"], target)
    c = cfg.collect
    env = runner.build_env(c["env_allow"], c["env_set"])
    if target.kind == "ssh":
        if "SSH_AUTH_SOCK" in os.environ:          # ssh-agent 는 써야 하므로
            env["SSH_AUTH_SOCK"] = os.environ["SSH_AUTH_SOCK"]
        return ssh_argv(cfg, cmd, target), None, env
    cwd = cfg.inside(cmd.get("cwd") or target.cwd or ".", f"명령 {cmd['id']} 의 cwd")
    return list(cmd["argv"]), cwd, env


def cut_partial_line(data):
    """잘린 출력은 마지막 줄바꿈까지만 남긴다(끝나지 않은 줄에 비밀 일부가 남지 않게)."""
    end = data.rfind(b"\n")
    return data[:end + 1] if end >= 0 else b""


def execute(cfg, cmd, target):
    """명령 하나를 실행한다. (가린 결과, 원본 stdout, 원본 stderr, 바꾼 개수)

    result.argv 는 실제로 실행한 ssh argv 가 아니라 공개용 argv(설정의 argv, 민감한 값 가림)다.
    """
    c = cfg.collect
    try:
        argv, cwd, env = plan(cfg, cmd, target)
    except PidocError as e:
        result = runner.Result(cmd["argv"])
        result.error = str(e)
    else:
        result = runner.run(argv, cwd=cwd, env=env, timeout=cmd.get("timeout_s", c["timeout_s"]),
                            max_output=c["max_output"])
    # 기록에는 실제 ssh 주소·내 PC 의 절대 경로 대신 정의된 명령과 상대 폴더만 남긴다
    result.argv = public_argv(cmd["argv"])
    result.cwd = cmd.get("cwd") or target.cwd or "."
    if result.stdout_truncated:
        result.stdout = cut_partial_line(result.stdout)
    if result.stderr_truncated:
        result.stderr = cut_partial_line(result.stderr)
    raw_out, raw_err = result.stdout, result.stderr
    rules = redact.rules_for(cfg, target)
    result.stdout, n1 = redact.apply_bytes(rules, raw_out)
    result.stderr, n2 = redact.apply_bytes(rules, raw_err)
    return result, raw_out, raw_err, n1 + n2


def extract_facts(rules, data, *, cmd_id, run_name, sha, collected_at):
    """출력 하나에서 사실들을 뽑는다. (사실 dict, 오류 목록)"""
    found, errors = {}, []
    for rule in rules:
        try:
            value = facts.extract(rule, data)
        except facts.FactError as e:
            errors.append(f"{rule['key']}: {e}")
            continue
        found[rule["key"]] = facts.make_fact(rule, value, run=run_name, command=cmd_id,
                                             source_sha256=sha, collected_at=collected_at)
    return found, errors


def failure(result, ok_exit):
    """실패 이유 또는 None. 출력이 잘렸으면 실패다(잘린 숫자·JSON 이 사실이 되지 않게)."""
    if result.error:
        return result.error
    if result.timed_out:
        return "시간 초과"
    if result.exit not in ok_exit:
        return f"종료 코드 {result.exit}"
    if result.stdout_truncated or result.stderr_truncated:
        return "출력이 collect.max_output 을 넘어 잘림"
    return None


def describe_failure(record):
    if record["error"]:
        return record["error"]
    if record["timed_out"]:
        return "시간 초과"
    if record["stdout"].get("truncated") or record["stderr"].get("truncated"):
        return "출력이 잘림"
    return f"종료 코드 {record['exit']}"


def warn_if_not_ignored(cfg, path):
    """--keep-raw 원본이 git 에 들어가지 않는지 확인한다."""
    try:
        proc = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=cfg.root, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return
    if proc.returncode == 1:
        say(f"  경고: {cfg.rel(path)} 가 .gitignore 에 없습니다 — docs/.gitignore 에 evidence/private/ 를 넣으세요")


def collect_target(cfg, target, only=None, keep_raw=False):
    """대상 하나를 수집한다. 실패가 있었으면 False."""
    commands = cfg.commands_for(target.name)
    if only:
        commands = [c for c in commands if c["id"] in only]
    if not commands:
        say(f"[{target.name}] 실행할 명령이 없습니다")
        return True

    started = now()
    run_dir = evidence.new_run_dir(cfg.runs_dir, target.name, started)
    private = cfg.docs_dir / "evidence" / "private" / run_dir.name
    say(f"[{target.name}] run {run_dir.name}")
    results, new_facts, all_ok = {}, {}, True
    for cmd in commands:
        result, raw_out, raw_err, replaced = execute(cfg, cmd, target)
        finished = now()
        record = evidence.save_result(run_dir, cmd["id"], result, finished,
                                      extra={"transport": target.kind, "redacted": replaced})
        if keep_raw:
            private.mkdir(parents=True, exist_ok=True)
            (private / f"{cmd['id']}.stdout").write_bytes(raw_out)
            (private / f"{cmd['id']}.stderr").write_bytes(raw_err)
        why = failure(result, cmd["ok_exit"])
        problems = []
        if why is None:
            found, problems = extract_facts(cmd["fact"], result.stdout, cmd_id=cmd["id"], run_name=run_dir.name,
                                            sha=record["stdout"]["sha256"], collected_at=iso(finished))
            if not problems:                    # 한 명령의 사실은 모두 갱신하거나 하나도 안 한다
                new_facts.update(found)
        results[cmd["id"]] = {"ok": why is None and not problems, "exit": result.exit}
        if why:
            all_ok = False
            say(f"  실패 {cmd['id']}: {why} — 이 명령의 사실은 갱신하지 않습니다")
            for line in result.stderr.decode("utf-8", errors="replace").strip().splitlines()[-3:]:
                say(f"    | {line}")
        elif problems:
            all_ok = False
            for p in problems:
                say(f"  추출 실패 {cmd['id']}: {p}")
            say(f"  → {cmd['id']} 의 사실은 하나도 갱신하지 않습니다")
        else:
            note = f" (가림 {replaced}곳)" if replaced else ""
            say(f"  성공 {cmd['id']} ({result.duration_ms} ms, 사실 {len(cmd['fact'])}개){note}")

    evidence.write_manifest(
        run_dir, target=target.name, alias=target.alias, kind=target.kind,
        started=started, finished=now(), commands=[public_command(c) for c in commands],
        config_sha256=cfg.sha256(), results=results)
    if new_facts:
        facts.update_file(cfg.facts_dir, target.name, target.alias, new_facts)
    say(f"[{target.name}] 사실 {len(new_facts)}개 갱신 → {cfg.rel(facts.path_for(cfg.facts_dir, target.name))}")
    if keep_raw:
        say(f"  원본(가리기 전)은 {cfg.rel(private)} 에 — 공개 저장소에 넣지 마세요")
        warn_if_not_ignored(cfg, private)
    return all_ok


def collect(cfg, target_name=None, only=None, keep_raw=False):
    names = [target_name] if target_name else list(cfg.targets)
    if only:
        known = {c["id"] for c in cfg.commands}
        unknown = [o for o in only if o not in known]
        if unknown:
            raise PidocError(f"모르는 명령 id: {', '.join(unknown)}")
    ok = True
    for name in names:
        ok = collect_target(cfg, cfg.target(name), only, keep_raw) and ok
    if not ok:
        print("일부 명령이 실패했습니다(종료 코드 3)", file=sys.stderr)
        return COLLECT_FAILED
    return OK


def replay(cfg, path):
    """저장된 증거에서 사실만 다시 뽑는다(실행하지 않음).

    추출 규칙은 지금 설정의 것을 쓰고, 설정에 없는 명령이면 manifest 에 남은 사본을 쓴다.
    오래된 run 부터 차례로 덮어쓰므로 결과는 가장 최근 증거를 따른다.
    """
    runs = evidence.list_runs(path)
    if not runs:
        raise PidocError(f"run 이 없습니다: {path}")
    all_ok = True
    for run in runs:
        found_all = {}
        for cmd_id in run.manifest.get("results", {}):
            if not run.has(cmd_id):
                continue
            current = next((c for c in cfg.commands if c["id"] == cmd_id and run.target in c["targets"]), None)
            cmd = current or run.command(cmd_id)
            if cmd is None:
                continue
            record = run.record(cmd_id)
            if (record["error"] or record["timed_out"] or record["exit"] not in cmd.get("ok_exit", [0])
                    or record["stdout"].get("truncated") or record["stderr"].get("truncated")):
                continue
            found, problems = extract_facts(cmd.get("fact", []), run.stdout(cmd_id), cmd_id=cmd_id,
                                            run_name=run.name, sha=record["stdout"]["sha256"],
                                            collected_at=record["finished_at"])
            if not problems:
                found_all.update(found)
            for p in problems:
                all_ok = False
                say(f"  추출 실패 {run.name}/{cmd_id}: {p}")
        if found_all:
            facts.update_file(cfg.facts_dir, run.target, run.manifest.get("alias", run.target), found_all)
        say(f"[{run.target}] {run.name}: 사실 {len(found_all)}개")
    return OK if all_ok else COLLECT_FAILED
