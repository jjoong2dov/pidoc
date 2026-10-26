"""collect: 설정의 명령을 대상에서 실행 → 증거 저장 → 사실 추출 → facts 갱신."""

import sys
from pathlib import Path

from . import evidence, facts, runner
from .util import COLLECT_FAILED, OK, PidocError, iso, now


def say(msg):
    print(msg, flush=True)


def check_program(cfg, argv):
    """allow_programs 가 있으면 그 안의 프로그램만 실행한다(이름만 비교, 경로 금지)."""
    allowed = cfg.collect["allow_programs"]
    if not allowed:
        return
    program = argv[0]
    if "/" in program or program not in allowed:
        raise PidocError(f"허용 목록(collect.allow_programs)에 없는 프로그램: {program}")


def local_argv(cfg, cmd, target):
    check_program(cfg, cmd["argv"])
    return list(cmd["argv"])


def local_cwd(cfg, cmd, target):
    cwd = cmd.get("cwd") or target.cwd or "."
    return (cfg.root / cwd).resolve()


def run_command(cfg, cmd, target):
    """명령 하나를 대상에서 실행해 runner.Result 를 돌려준다."""
    c = cfg.collect
    timeout = cmd.get("timeout_s", c["timeout_s"])
    try:
        if target.kind != "local":
            raise PidocError("ssh 대상은 아직 지원하지 않습니다")
        argv = local_argv(cfg, cmd, target)
    except PidocError as e:
        result = runner.Result(cmd["argv"])
        result.error = str(e)
        return result
    env = runner.build_env(c["env_allow"], c["env_set"])
    return runner.run(argv, cwd=local_cwd(cfg, cmd, target), env=env,
                      timeout=timeout, max_output=c["max_output"])


def extract_facts(cfg, cmd, data, *, run_name, sha, collected_at):
    """명령 하나의 출력에서 사실들을 뽑는다. (사실 dict, 오류 목록)"""
    found, errors = {}, []
    for rule in cmd["fact"]:
        try:
            value = facts.extract(rule, data)
        except facts.FactError as e:
            errors.append(f"{rule['key']}: {e}")
            continue
        found[rule["key"]] = facts.make_fact(rule, value, run=run_name, command=cmd["id"],
                                             source_sha256=sha, collected_at=collected_at)
    return found, errors


def describe_failure(record):
    if record["error"]:
        return record["error"]
    if record["timed_out"]:
        return "시간 초과"
    return f"종료 코드 {record['exit']}"


def collect_target(cfg, target, only=None):
    """대상 하나를 수집한다. 실패가 있었으면 False."""
    commands = cfg.commands_for(target.name)
    if only:
        commands = [c for c in commands if c["id"] in only]
    if not commands:
        say(f"[{target.name}] 실행할 명령이 없습니다")
        return True

    started = now()
    run_dir = evidence.new_run_dir(cfg.runs_dir, target.name, started)
    say(f"[{target.name}] run {run_dir.name}")
    results, new_facts, all_ok = {}, {}, True
    for cmd in commands:
        result = run_command(cfg, cmd, target)
        finished = now()
        record = evidence.save_result(run_dir, cmd["id"], result, finished)
        ok = result.ok(cmd["ok_exit"])
        problems = []
        if ok:
            found, problems = extract_facts(cfg, cmd, result.stdout, run_name=run_dir.name,
                                            sha=record["stdout"]["sha256"], collected_at=iso(finished))
            new_facts.update(found)
        results[cmd["id"]] = {"ok": ok and not problems, "exit": result.exit}
        if not ok:
            all_ok = False
            say(f"  실패 {cmd['id']}: {describe_failure(record)} — 이 명령의 사실은 갱신하지 않습니다")
            tail = result.stderr.decode("utf-8", errors="replace").strip().splitlines()[-3:]
            for line in tail:
                say(f"    | {line}")
        elif problems:
            all_ok = False
            for p in problems:
                say(f"  추출 실패 {cmd['id']}: {p}")
        else:
            note = " (출력이 잘림)" if result.stdout_truncated else ""
            say(f"  성공 {cmd['id']} ({result.duration_ms} ms, 사실 {len(cmd['fact'])}개){note}")

    evidence.write_manifest(
        run_dir, target=target.name, alias=target.alias, kind=target.kind,
        started=started, finished=now(), commands=commands,
        config_sha256=cfg.sha256(), results=results)
    if new_facts:
        facts.update_file(cfg.facts_dir, target.name, target.alias, new_facts)
    say(f"[{target.name}] 사실 {len(new_facts)}개 갱신 → {cfg.rel(facts.path_for(cfg.facts_dir, target.name))}")
    return all_ok


def collect(cfg, target_name=None, only=None):
    names = [target_name] if target_name else list(cfg.targets)
    if only:
        known = {c["id"] for c in cfg.commands}
        unknown = [o for o in only if o not in known]
        if unknown:
            raise PidocError(f"모르는 명령 id: {', '.join(unknown)}")
    ok = True
    for name in names:
        ok = collect_target(cfg, cfg.target(name), only) and ok
    if not ok:
        print("일부 명령이 실패했습니다(종료 코드 3)", file=sys.stderr)
        return COLLECT_FAILED
    return OK
