"""사실: 증거에서 추출 규칙으로 뽑은, 타입 있는 값.

facts/<target>.json
  {"schema": 1, "target": "pi", "alias": "pi4",
   "facts": {"system.kernel_release": {"value": ..., "type": "string", "run": ..., "command": ...,
             "extract": "stdout_line", "source_sha256": ..., "collected_at": ..., "max_age_days": null}}}
"""

import json
import re
from pathlib import Path

from .util import PidocError, age_days, read_json, write_json

TRUE = ("true", "yes", "on", "1")
FALSE = ("false", "no", "off", "0")


class FactError(ValueError):
    pass


def _json_path(data, path):
    node = data
    for part in path.split("."):
        if isinstance(node, list):
            if not part.isdigit() or int(part) >= len(node):
                raise FactError(f"json 경로 {path}: 목록에 {part} 번째가 없습니다")
            node = node[int(part)]
        elif isinstance(node, dict):
            if part not in node:
                raise FactError(f"json 경로 {path}: {part} 가 없습니다")
            node = node[part]
        else:
            raise FactError(f"json 경로 {path}: {part} 앞에서 더 들어갈 수 없습니다")
    return node


def extract_raw(rule, data):
    """규칙대로 출력(bytes)에서 값을 뽑는다(타입 변환 전)."""
    text = data.decode("utf-8", errors="replace")
    how = rule["extract"]
    if how == "stdout_all":
        return text.rstrip("\n")
    if how == "stdout_line":
        lines = text.splitlines()
        n = rule.get("line", 1)
        if not 1 <= n <= len(lines):
            raise FactError(f"{n} 번째 줄이 없습니다(출력 {len(lines)}줄)")
        return lines[n - 1].strip()
    if how == "regex":
        m = re.search(rule["pattern"], text, re.MULTILINE)
        if not m:
            raise FactError(f"정규식이 맞지 않습니다: {rule['pattern']}")
        return m.group(1) if m.groups() else m.group(0)
    if how == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise FactError(f"출력이 JSON 이 아닙니다: {e}")
        return _json_path(data, rule["path"])
    raise FactError(f"모르는 extract: {how}")


def convert(value, kind, sep=","):
    """정해진 타입으로만 바꾼다. 애매하면 실패."""
    try:
        if kind == "string":
            if isinstance(value, (dict, list)):
                raise FactError("목록·표는 string 이 될 수 없습니다")
            return value if isinstance(value, str) else json.dumps(value)
        if kind == "int":
            if isinstance(value, bool):
                raise FactError("true/false 는 int 가 아닙니다")
            if isinstance(value, float):
                if not value.is_integer():
                    raise FactError(f"정수가 아닙니다: {value}")
                return int(value)
            return int(value) if isinstance(value, int) else int(str(value).strip())
        if kind == "float":
            if isinstance(value, bool):
                raise FactError("true/false 는 float 가 아닙니다")
            return float(value) if isinstance(value, (int, float)) else float(str(value).strip())
        if kind == "bool":
            if isinstance(value, bool):
                return value
            text = str(value).strip().lower()
            if text in TRUE:
                return True
            if text in FALSE:
                return False
            raise FactError(f"true/false 로 읽을 수 없습니다: {value!r}")
        if kind == "list":
            if isinstance(value, list):
                return value
            return [part.strip() for part in str(value).split(sep) if part.strip()]
    except (TypeError, ValueError) as e:
        if isinstance(e, FactError):
            raise
        raise FactError(f"{kind} 로 바꿀 수 없습니다: {value!r}")
    raise FactError(f"모르는 type: {kind}")


def extract(rule, data):
    return convert(extract_raw(rule, data), rule.get("type", "string"), rule.get("sep", ","))


def type_of(value):
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "list"
    return "string"


# --- 사실 파일 ---

def path_for(facts_dir, target):
    return Path(facts_dir) / f"{target}.json"


def load_file(facts_dir, target):
    path = path_for(facts_dir, target)
    if not path.is_file():
        return {"schema": 1, "target": target, "alias": target, "facts": {}}
    data = read_json(path)
    if data.get("schema") != 1:
        raise PidocError(f"{path}: 모르는 사실 파일 형식(schema {data.get('schema')})")
    return data


def update_file(facts_dir, target, alias, new_facts):
    """새 사실을 덧씌워 저장한다. 이번에 뽑지 않은 키는 그대로 둔다."""
    data = load_file(facts_dir, target)
    data["alias"] = alias
    data["facts"].update(new_facts)
    write_json(path_for(facts_dir, target), data)
    return data


def load_all(facts_dir):
    """{대상: {키: 사실}}"""
    result = {}
    folder = Path(facts_dir)
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            data = read_json(path)
            result[data.get("target", path.stem)] = data.get("facts", {})
    return result


def is_expired(fact, at=None):
    days = fact.get("max_age_days")
    if days is None or not fact.get("collected_at"):
        return False
    return age_days(fact["collected_at"], at) > days


def make_fact(rule, value, *, run, command, source_sha256, collected_at):
    return {
        "value": value,
        "type": rule.get("type", "string"),
        "run": run,
        "command": command,
        "extract": rule["extract"],
        "source_sha256": source_sha256,
        "collected_at": collected_at,
        "max_age_days": rule.get("max_age_days"),
    }


def show_value(value):
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "(없음)"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
