"""사실이 증거와 맞는지 본다: 그 run 의 stdout 에서 같은 규칙으로 다시 뽑아 비교한다."""

import hashlib
import json

from pidoc.facts import ExtractError, extract, find_run


class FactsError(Exception):
    pass


def load_all(cfg):
    """{대상: {키: 기록}}. 파일이 깨졌으면 FactsError."""
    out = {}
    for tname in cfg.targets:
        path = cfg.facts_dir / f"{tname}.json"
        out[tname] = {}
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            raise FactsError(f"사실 파일을 읽지 못함: facts/{tname}.json: {e}")
        if not isinstance(data, dict) or not all(isinstance(v, dict) for v in data.values()):
            raise FactsError(f"사실 파일 형식이 올바르지 않음: facts/{tname}.json")
        out[tname] = data
    return out


def same(a, b):
    """타입까지 같은지(1, 1.0, True 를 가른다)."""
    if type(a) is not type(b):
        return False
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def _rule(cfg, tname, key, command):
    for cmd in cfg.commands:
        if cmd.id == command and tname in cmd.targets:
            for f in cmd.facts:
                if f.key == key:
                    return f
    return None


def _show(v):
    return json.dumps(v, ensure_ascii=False)


def verify(cfg, tname, key, rec, red):
    """맞으면 None, 아니면 까닭."""
    run, command = rec.get("run"), rec.get("command")
    if not isinstance(run, str) or not isinstance(command, str):
        return "run·command 기록이 없음"
    rule = _rule(cfg, tname, key, command)
    if rule is None:
        return f"설정에 이 사실을 뽑는 규칙이 없음(명령 {command})"
    if rec.get("type") != rule.type or rec.get("extract") != rule.extract:
        return "타입·추출 방식이 설정과 다름"
    run_dir = find_run(cfg, run)
    if run_dir is None:
        return f"증거 run 이 없음: {run}"
    rec_path = run_dir / tname / f"{command}.json"
    out_path = run_dir / tname / f"{command}.stdout"
    if not rec_path.is_file() or not out_path.is_file():
        return f"증거가 없음: {run}/{tname}/{command}"
    try:
        ev = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return f"증거 기록을 읽지 못함: {run}/{tname}/{command}.json"
    if not isinstance(ev, dict) or not ev.get("ok") or ev.get("stdout_truncated"):
        return f"실패했거나 잘린 실행의 증거임: {run}/{tname}/{command}"
    raw = out_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != rec.get("source_sha256"):
        return f"증거 stdout 의 sha256 이 사실 기록과 다름: {run}/{tname}/{command}"
    try:
        got = extract(rule, raw)
    except ExtractError as e:
        return f"증거에서 다시 뽑지 못함: {e}"
    value = rec.get("value")
    # 증거는 이미 가려져 있다. facts 때 한 번 더 가렸을 수 있으니 둘 다 받는다.
    if not (same(value, got) or same(value, red.obj(got))):
        return f"값이 증거와 다름: 사실 파일 {_show(value)}, 증거 {_show(red.obj(got))}"
    return None
