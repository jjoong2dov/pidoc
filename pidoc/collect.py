"""pidoc collect: 명령을 돌려 docs/evidence/runs/<run-id>/ 에 증거를 남긴다."""

import hashlib
import json
import os
import sys

from pidoc import clock, runner


def write_json(path, data):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def _new_run_dir(runs_dir, stamp):
    runs_dir.mkdir(parents=True, exist_ok=True)
    n = 1
    while True:
        run_id = stamp if n == 1 else f"{stamp}-{n}"
        d = runs_dir / run_id
        try:
            d.mkdir()
            return run_id, d
        except FileExistsError:
            n += 1


def _env(cfg):
    env = {k: os.environ[k] for k in cfg.env_allow if k in os.environ}
    env.update(cfg.env_set)
    return env


def collect(cfg):
    created = clock.now()
    run_id, run_dir = _new_run_dir(cfg.runs_dir, clock.run_stamp(created))
    env = _env(cfg)
    entries = []
    failed = 0
    for cmd in cfg.commands:
        for tname in cmd.targets:
            tdir = run_dir / tname
            tdir.mkdir(exist_ok=True)
            started = clock.now()
            r = runner.run(cmd.argv, env=env, cwd=cfg.root,
                           timeout_s=cfg.timeout_s, max_output=cfg.max_output)
            (tdir / f"{cmd.id}.stdout").write_bytes(r.stdout)
            (tdir / f"{cmd.id}.stderr").write_bytes(r.stderr)
            ok = r.exit_code == 0 and not r.timed_out and r.error is None
            write_json(tdir / f"{cmd.id}.json", {
                "command": cmd.id,
                "target": tname,
                "argv": cmd.argv,
                "exit_code": r.exit_code,
                "timed_out": r.timed_out,
                "error": r.error,
                "ok": ok,
                "started_at": clock.iso(started),
                "finished_at": clock.iso(clock.now()),
                "duration_s": r.duration_s,
                "timeout_s": cfg.timeout_s,
                "max_output": cfg.max_output,
                "stdout_bytes": r.stdout_bytes,
                "stderr_bytes": r.stderr_bytes,
                "stdout_truncated": r.stdout_truncated,
                "stderr_truncated": r.stderr_truncated,
                "stdout_sha256": hashlib.sha256(r.stdout).hexdigest(),
                "stderr_sha256": hashlib.sha256(r.stderr).hexdigest(),
            })
            entries.append({"command": cmd.id, "target": tname, "ok": ok,
                            "stdout_truncated": r.stdout_truncated})
            if ok:
                note = " (출력 잘림)" if r.stdout_truncated or r.stderr_truncated else ""
                print(f"성공  {tname}:{cmd.id}{note}")
            else:
                failed += 1
                why = r.error or f"종료 코드 {r.exit_code}"
                print(f"실패  {tname}:{cmd.id} — {why}", file=sys.stderr)
    # manifest 는 끝에 쓴다. manifest 가 없는 run 은 미완성으로 본다.
    write_json(run_dir / "manifest.json", {
        "run_id": run_id,
        "project": cfg.name,
        "created_at": clock.iso(created),
        "targets": {t.name: {"kind": t.kind, "alias": t.alias} for t in cfg.targets.values()},
        "entries": entries,
    })
    print(f"run {run_id}: 명령 {len(entries)}개, 실패 {failed}개")
    return 3 if failed else 0
