"""사실을 증거와 다시 맞춰 본다(render·check 가 사실을 쓰기 전에).

사실 파일은 손으로 고칠 수 있는 JSON 이다. 그래서 값만 믿지 않고:
  - 수집한 사실: 그 run 의 stdout sha256 이 맞는지, 같은 규칙으로 다시 뽑은 값이 같은지,
    그 명령의 더 최근 수집이 실패하거나 이 사실을 만들지 않았는지
  - 코드에서 뽑은 사실(code): 원본 파일의 sha256 이 그대로인지
git·test 사실은 pidoc 이 git log·JUnit 파일에서 바로 만들고 원본을 남기지 않으므로 다시 맞춰 보지 않는다.
"""

from pathlib import Path

from . import evidence, facts
from .util import PidocError, sha256_file

UNCHECKED_TARGETS = ("git", "test")


class Verifier:
    def __init__(self, cfg):
        self.cfg = cfg
        self.cache = {}

    def problem(self, target, key, fact):
        """문제가 있으면 메시지, 없으면 None."""
        name = f"{target}:{key}"
        if name not in self.cache:
            try:
                self.cache[name] = self._check(target, key, fact)
            except PidocError as e:
                self.cache[name] = str(e)
        return self.cache[name]

    def _check(self, target, key, fact):
        if target in UNCHECKED_TARGETS:
            return None
        if target == "code":
            return self._check_code(fact)
        return self._check_collected(target, key, fact)

    def _check_code(self, fact):
        source = fact.get("source")
        kind = str(fact.get("command", "extract:")).split(":", 1)[-1]
        if not source:
            return "출처(source)가 없는 코드 사실입니다"
        path = self.cfg.root / source
        if not path.is_file() or sha256_file(path) != fact.get("source_sha256"):
            return f"코드가 바뀌었습니다({source}) — pidoc extract {kind} 를 다시 돌리세요"
        return None

    def _check_collected(self, target, key, fact):
        cfg = self.cfg
        run_dir = cfg.runs_dir / str(fact.get("run", ""))
        cmd_id = fact.get("command")
        if not fact.get("run") or not (run_dir / "manifest.json").is_file():
            return f"증거 run 이 없습니다: {fact.get('run')} — pidoc collect"
        run = evidence.Run(run_dir)
        if not run.has(cmd_id):
            return f"증거 run {run.name} 에 명령 {cmd_id} 기록이 없습니다"
        record = run.record(cmd_id)
        if record["stdout"]["sha256"] != fact.get("source_sha256"):
            return "사실의 source_sha256 이 증거와 다릅니다(사실 파일을 손으로 고쳤나요?)"
        data = run.stdout(cmd_id)                     # 저장된 stdout 자체의 sha256 도 확인
        rule = self._rule(run, target, cmd_id, key)
        if rule is None:
            return f"설정에도 manifest 에도 {key} 를 만드는 규칙이 없습니다"
        try:
            value = facts.extract(rule, data)
        except facts.FactError as e:
            return f"증거에서 다시 뽑지 못했습니다: {e}"
        if value != fact["value"] or rule.get("type", "string") != fact["type"]:
            return "증거에서 다시 뽑은 값과 다릅니다(사실 파일을 손으로 고쳤거나 규칙이 바뀜 — pidoc replay)"
        latest = evidence.latest_attempt(cfg.runs_dir, target, cmd_id)
        if latest is not None and latest.name != run.name:
            if not evidence.run_ok(latest, cmd_id):
                return f"더 최근 수집({latest.name})이 실패했습니다 — 옛 사실을 쓰지 않습니다"
            return f"더 최근 수집({latest.name})이 이 사실을 만들지 않았습니다 — 규칙을 확인하세요"
        return None

    def _rule(self, run, target, cmd_id, key):
        for c in self.cfg.commands:
            if c["id"] == cmd_id and target in c["targets"]:
                return next((r for r in c["fact"] if r["key"] == key), None)
        copy = run.command(cmd_id) or {}
        return next((r for r in copy.get("fact", []) if r["key"] == key), None)
