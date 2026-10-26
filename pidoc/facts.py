"""pidoc facts: run 의 증거에서 사실을 뽑아 docs/facts/<대상>.json 을 갱신한다."""

import hashlib
import json
import math
import re
import sys

from pidoc.collect import write_json
from pidoc.redact import Redactor

TRUE = {"true", "yes", "on", "1"}
FALSE = {"false", "no", "off", "0"}
INT_RE = re.compile(r"^[+-]?\d+$")


class ExtractError(Exception):
    pass


def _run_key(d, manifest):
    base, _, suffix = d.name.partition("-")
    return (manifest.get("created_at", ""), base, int(suffix) if suffix.isdigit() else 1)


def find_run(cfg, run_id=None):
    """run 폴더를 고른다. 없으면 None. 지정이 없으면 manifest 가 있는 가장 최근 run."""
    if run_id is not None:
        d = cfg.runs_dir / run_id
        if "/" in run_id or run_id in ("", ".", "..") or not (d / "manifest.json").is_file():
            return None
        return d
    best = None
    if cfg.runs_dir.is_dir():
        for d in cfg.runs_dir.iterdir():
            m = d / "manifest.json"
            if not m.is_file():
                continue
            key = _run_key(d, json.loads(m.read_text(encoding="utf-8")))
            if best is None or key > best[0]:
                best = (key, d)
    return best[1] if best else None


def extract(fact, raw):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ExtractError("stdout 이 UTF-8 이 아님")
    if fact.extract == "stdout_all":
        value = text.strip()
    elif fact.extract == "stdout_line":
        lines = text.splitlines()
        if fact.line > len(lines):
            raise ExtractError(f"{fact.line}번째 줄이 없음")
        value = lines[fact.line - 1].strip()
    elif fact.extract == "regex":
        m = re.search(fact.pattern, text, re.MULTILINE)
        if not m:
            raise ExtractError("정규식이 맞지 않음")
        value = m.group(fact.group)
    elif fact.extract == "json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError as e:
            raise ExtractError(f"JSON 이 아님: {e}")
        for part in fact.path.split(".") if fact.path else []:
            if isinstance(value, dict) and part in value:
                value = value[part]
            elif isinstance(value, list) and INT_RE.match(part) and -len(value) <= int(part) < len(value):
                value = value[int(part)]
            else:
                raise ExtractError(f"경로가 없음: {fact.path}")
    return convert(value, fact.type)


def convert(v, t):
    is_num = isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "string":
        if isinstance(v, str):
            return v
        if is_num:
            return str(v)
    elif t == "int":
        if isinstance(v, int) and not isinstance(v, bool):
            return v
        if isinstance(v, str) and INT_RE.match(v.strip()):
            return int(v.strip())
    elif t == "float":
        if is_num:
            return float(v)
        if isinstance(v, str):
            try:
                f = float(v.strip())
            except ValueError:
                f = None
            if f is not None and math.isfinite(f):
                return f
    elif t == "list":
        if isinstance(v, list) and all(isinstance(x, (str, int, float, bool)) for x in v):
            return v
        if isinstance(v, str):
            return [ln.strip() for ln in v.splitlines() if ln.strip()]
    elif t == "bool":
        if isinstance(v, bool):
            return v
        if isinstance(v, str) and v.strip().lower() in TRUE | FALSE:
            return v.strip().lower() in TRUE
    raise ExtractError(f"{t} 로 바꿀 수 없음: {v!r}")


def build_facts(cfg, run_id=None):
    run_dir = find_run(cfg, run_id)
    if run_dir is None:
        print("쓸 수 있는 run 이 없음" + (f": {run_id}" if run_id else ""), file=sys.stderr)
        return 3
    red = Redactor.from_config(cfg)
    problems = 0
    updated = 0
    for tname in cfg.targets:
        path = cfg.facts_dir / f"{tname}.json"
        facts = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        # 이미 있는 사실도 가린다(가리기 전에 만든 파일 대비)
        clean = red.obj(facts)
        changed = clean != facts
        facts = clean
        for cmd in cfg.commands:
            if tname not in cmd.targets or not cmd.facts:
                continue
            where = f"{tname}:{cmd.id}"
            rec_path = run_dir / tname / f"{cmd.id}.json"
            if not rec_path.is_file():
                print(f"건너뜀  {where} — 이 run 에 증거가 없음", file=sys.stderr)
                problems += 1
                continue
            rec = json.loads(rec_path.read_text(encoding="utf-8"))
            if not rec.get("ok"):
                why = rec.get("error") or f"종료 코드 {rec.get('exit_code')}"
                print(f"건너뜀  {where} — 실패한 명령({why}), 사실을 갱신하지 않음", file=sys.stderr)
                problems += 1
                continue
            if rec.get("stdout_truncated"):
                print(f"건너뜀  {where} — 잘린 출력, 사실을 만들지 않음", file=sys.stderr)
                problems += 1
                continue
            raw = (run_dir / tname / f"{cmd.id}.stdout").read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            for fact in cmd.facts:
                try:
                    value = extract(fact, raw)
                except ExtractError as e:
                    print(f"실패    {where} {fact.key} — {e}", file=sys.stderr)
                    problems += 1
                    continue
                facts[fact.key] = {
                    "value": red.obj(value),
                    "type": fact.type,
                    "run": run_dir.name,
                    "command": cmd.id,
                    "extract": fact.extract,
                    "source_sha256": sha,
                    "collected_at": rec["started_at"],
                }
                changed = True
                updated += 1
        if changed:
            cfg.facts_dir.mkdir(parents=True, exist_ok=True)
            write_json(path, facts)
    print(f"run {run_dir.name}: 사실 {updated}개 갱신, 문제 {problems}개")
    return 3 if problems else 0
