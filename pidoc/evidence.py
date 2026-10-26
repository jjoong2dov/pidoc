"""실행 증거: docs/evidence/runs/<run-id>/ 에 손대지 않은 출력과 기록을 남긴다.

    manifest.json        명령 정의 사본, 대상, 시작·끝 시각, 수집기 버전, pidoc.toml sha256
    <cmd>.stdout/.stderr 원시 바이트
    <cmd>.json           argv, cwd, 종료 코드, 걸린 시간, 시간 초과·잘림 여부, sha256·바이트 수
"""

from pathlib import Path

from . import __version__
from .util import COLLECT_FAILED, PidocError, iso, read_json, sha256_bytes, write_json


def new_run_dir(runs_dir, target, started):
    """<시각>-<대상> 폴더를 만든다. 같은 초에 또 돌리면 -2, -3 을 붙인다."""
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    base = f"{started.strftime('%Y%m%dT%H%M%S')}-{target}"
    name, n = base, 1
    while (runs_dir / name).exists():
        n += 1
        name = f"{base}-{n}"
    path = runs_dir / name
    path.mkdir()
    return path


def save_result(run_dir, cmd_id, result, finished, extra=None):
    """명령 하나의 결과를 저장하고 기록(dict)을 돌려준다."""
    run_dir = Path(run_dir)
    (run_dir / f"{cmd_id}.stdout").write_bytes(result.stdout)
    (run_dir / f"{cmd_id}.stderr").write_bytes(result.stderr)
    record = {
        "id": cmd_id,
        "argv": result.argv,
        "cwd": result.cwd,
        "exit": result.exit,
        "error": result.error,
        "duration_ms": result.duration_ms,
        "timed_out": result.timed_out,
        "finished_at": iso(finished),
        "stdout": {"bytes": len(result.stdout), "sha256": sha256_bytes(result.stdout),
                   "truncated": result.stdout_truncated},
        "stderr": {"bytes": len(result.stderr), "sha256": sha256_bytes(result.stderr),
                   "truncated": result.stderr_truncated},
    }
    if extra:
        record.update(extra)
    write_json(run_dir / f"{cmd_id}.json", record)
    return record


def write_manifest(run_dir, *, target, alias, kind, started, finished, commands, config_sha256, results):
    write_json(Path(run_dir) / "manifest.json", {
        "schema": 1,
        "run": Path(run_dir).name,
        "target": target,
        "alias": alias,
        "kind": kind,
        "started_at": iso(started),
        "finished_at": iso(finished),
        "pidoc_version": __version__,
        "config_sha256": config_sha256,
        "commands": commands,
        "results": results,
    })


class Run:
    """저장된 run 폴더 하나를 읽는다."""

    def __init__(self, path):
        self.path = Path(path)
        manifest = self.path / "manifest.json"
        if not manifest.is_file():
            raise PidocError(f"run 폴더가 아닙니다(manifest.json 없음): {self.path}")
        self.manifest = read_json(manifest)
        self.name = self.manifest.get("run", self.path.name)
        self.target = self.manifest["target"]

    def has(self, cmd_id):
        return (self.path / f"{cmd_id}.json").is_file()

    def record(self, cmd_id):
        return read_json(self.path / f"{cmd_id}.json")

    def stdout(self, cmd_id):
        data = (self.path / f"{cmd_id}.stdout").read_bytes()
        expected = self.record(cmd_id)["stdout"]["sha256"]
        if sha256_bytes(data) != expected:
            raise PidocError(f"{self.path.name}/{cmd_id}.stdout 가 기록된 sha256 과 다릅니다(손댄 증거?)", COLLECT_FAILED)
        return data

    def command(self, cmd_id):
        for c in self.manifest.get("commands", []):
            if c["id"] == cmd_id:
                return c
        return None


def list_runs(path):
    """run 폴더 하나 또는 runs 폴더를 받아 Run 목록(오래된 것부터)."""
    path = Path(path)
    if (path / "manifest.json").is_file():
        return [Run(path)]
    if not path.is_dir():
        return []
    runs = [Run(p) for p in sorted(path.iterdir()) if (p / "manifest.json").is_file()]
    runs.sort(key=lambda r: (r.manifest.get("started_at", ""), r.name))
    return runs


def latest_with(runs_dir, target, cmd_id, ok_only=True):
    """대상 target 에서 cmd_id 를 실행한 가장 최근 run(성공한 것)."""
    for run in reversed(list_runs(runs_dir)):
        if run.target != target or not run.has(cmd_id):
            continue
        if ok_only and not run.manifest.get("results", {}).get(cmd_id, {}).get("ok"):
            continue
        return run
    return None


def latest_attempt(runs_dir, target, cmd_id):
    """대상 target 에서 cmd_id 를 실행한 가장 최근 run(성공·실패 상관없이)."""
    return latest_with(runs_dir, target, cmd_id, ok_only=False)


def run_ok(run, cmd_id):
    return bool(run.manifest.get("results", {}).get(cmd_id, {}).get("ok"))
