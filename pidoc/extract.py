"""extract: 코드에서 레퍼런스 사실을 만든다(실행하지 않고 읽기만). 결과는 facts/code.json.

  cli     argparse 호출(ArgumentParser·add_argument·add_parser)을 ast 로 읽기
  config  설정 견본 TOML(값·주석) + 설정 모듈의 기본값 딕셔너리(ast.literal_eval)
  http    do_GET 같은 처리기 안의 경로 비교(path == "/status", path in ("/a", "/b"))
  py      모듈·공개 함수·클래스 docstring 첫 줄

도움말 출력 그 자체는 실행 결과이므로 collect 로 모은다(설계 원칙: 출력은 실행 증거로).
"""

import ast
import re
import tomllib
from pathlib import Path

from . import facts
from .config import KEY_RE
from .util import PidocError, iso, now, sha256_file, write_json

KINDS = ("cli", "config", "http", "py")
TARGET = "code"


def _part(text):
    """키 한 마디로 쓸 수 있게: 소문자, 허용 글자 밖은 _."""
    text = re.sub(r"[^a-z0-9_-]", "_", text.lower()).strip("-")
    return text or "_"


def _first_line(doc):
    return doc.strip().splitlines()[0].strip() if doc and doc.strip() else None


def _const(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None


def _call_name(node):
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


class Collector:
    """뽑은 사실을 모은다. 키마다 어느 파일에서 왔는지 남긴다."""

    def __init__(self, cfg, kind):
        self.cfg = cfg
        self.kind = kind
        self.items = {}
        self.at = iso(now())

    def add(self, key, value, source, how):
        if value is None or value == [] or value == "":
            return
        if not KEY_RE.match(key):
            return
        self.items[key] = {
            "value": value,
            "type": facts.type_of(value),
            "run": f"extract-{self.kind}",
            "command": f"extract:{self.kind}",
            "extract": how,
            "source": self.cfg.rel(source),
            "source_sha256": sha256_file(source),
            "collected_at": self.at,
            "max_age_days": None,
        }


def python_files(cfg):
    paths = cfg.extract.get("paths") or ["."]
    files = []
    for p in paths:
        path = cfg.root / p
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files += sorted(f for f in path.rglob("*.py") if "tests" not in f.relative_to(cfg.root).parts)
        else:
            raise PidocError(f"extract.paths 에 적은 곳이 없습니다: {p}")
    return files


def module_name(cfg, path):
    rel = path.resolve().relative_to(cfg.root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def parse(path):
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as e:
        raise PidocError(f"{path}: 파이썬 문법 오류: {e}")


# --- cli ---

def extract_cli(cfg, out):
    for path in python_files(cfg):
        tree = parse(path)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        parsers = [c for c in calls if _call_name(c) == "ArgumentParser"]
        if not parsers:
            continue
        kw = {k.arg: _const(k.value) for k in parsers[0].keywords if k.arg}
        prog = _part(kw.get("prog") or module_name(cfg, path).split(".")[0])
        base = f"cli.{prog}"
        out.add(f"{base}.description", kw.get("description"), path, "ast")
        options, commands = [], []
        for call in calls:
            name = _call_name(call)
            args = [_const(a) for a in call.args]
            kws = {k.arg: _const(k.value) for k in call.keywords if k.arg}
            if name == "add_parser" and args and isinstance(args[0], str):
                commands.append(args[0])
                out.add(f"{base}.command.{_part(args[0])}.help", kws.get("help"), path, "ast")
            if name != "add_argument" or not args or not all(isinstance(a, str) for a in args):
                continue
            flags = [a for a in args if a.startswith("-")]
            if not flags:                      # 위치 인자: choices 가 있으면 하위 명령으로 본다
                if isinstance(kws.get("choices"), (list, tuple)):
                    commands += list(kws["choices"])
                continue
            long = max(flags, key=len)
            options.append(long)
            opt = f"{base}.option.{_part(long.lstrip('-'))}"
            out.add(f"{opt}.help", kws.get("help"), path, "ast")
            default = kws.get("default")
            if isinstance(default, (str, int, float, bool)):
                out.add(f"{opt}.default", default, path, "ast")
            if isinstance(kws.get("choices"), (list, tuple)):
                out.add(f"{opt}.choices", [str(c) for c in kws["choices"]], path, "ast")
        out.add(f"{base}.options", options, path, "ast")
        out.add(f"{base}.commands", [str(c) for c in commands], path, "ast")


# --- config ---

def _flatten(data, prefix=""):
    for key, value in data.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            yield from _flatten(value, f"{name}.")
        else:
            yield name, value


def toml_comments(text):
    """'key = 값  # 설명' 줄에서 {점.키: 설명}. 이어지는 주석만 있는 줄은 덧붙인다."""
    comments, table, last = {}, "", None
    for line in text.splitlines():
        stripped = line.strip()
        m = re.match(r"^\[([A-Za-z0-9_.-]+)\]", stripped)
        if m:
            table, last = m.group(1) + ".", None
            continue
        m = re.match(r'^([A-Za-z0-9_-]+)\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^#])*#\s*(.+)$', stripped)
        if m:
            last = table + m.group(1)
            comments[last] = m.group(2).strip()
        elif stripped.startswith("#") and last and line[:1].isspace():
            comments[last] += " " + stripped.lstrip("# ").strip()
        else:
            last = None
    return comments


def extract_config(cfg, out):
    ex = cfg.extract
    example = ex.get("config_example")
    module = ex.get("config_module")
    if not example and not module:
        raise PidocError("extract config: [extract] 에 config_example 이나 config_module 을 적으세요")
    keys = []
    if module:
        path = cfg.root / module
        if not path.is_file():
            raise PidocError(f"extract.config_module 이 없습니다: {module}")
        name = ex.get("config_defaults", "DEFAULTS")
        found = None
        for node in parse(path).body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                found = _const(node.value)
        if not isinstance(found, dict):
            raise PidocError(f"{module}: {name} 딕셔너리를 찾지 못했습니다(상수만 쓴 딕셔너리여야 함)")
        for key, value in _flatten(found):
            keys.append(key)
            out.add(f"config.{key}.default", value if not isinstance(value, tuple) else list(value), path, "ast")
    if example:
        path = cfg.root / example
        if not path.is_file():
            raise PidocError(f"extract.config_example 이 없습니다: {example}")
        text = path.read_text(encoding="utf-8")
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            raise PidocError(f"{example}: TOML 문법 오류: {e}")
        comments = toml_comments(text)
        for key, value in _flatten(data):
            if key not in keys:
                keys.append(key)
            out.add(f"config.{key}.example", value, path, "toml")
            out.add(f"config.{key}.comment", comments.get(key), path, "toml")
    out.add("config.keys", keys, cfg.root / (module or example), "ast")


# --- http ---

def _paths_in(func):
    found = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Compare):
            continue
        for comp in [node.left, *node.comparators]:
            value = _const(comp)
            values = value if isinstance(value, (tuple, list, set)) else [value]
            for v in values:
                if isinstance(v, str) and v.startswith("/") and v not in found:
                    found.append(v)
    return found


def extract_http(cfg, out):
    for path in python_files(cfg):
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.FunctionDef) and re.match(r"^do_[A-Z]+$", node.name):
                out.add(f"http.{node.name[3:].lower()}.paths", _paths_in(node), path, "ast")


# --- py ---

def extract_py(cfg, out):
    for path in python_files(cfg):
        tree = parse(path)
        mod = module_name(cfg, path)
        if not mod:
            continue
        base = "py." + ".".join(_part(p) for p in mod.split("."))
        out.add(f"{base}.doc", _first_line(ast.get_docstring(tree)), path, "ast")
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
                out.add(f"{base}.{_part(node.name)}.doc", _first_line(ast.get_docstring(node)), path, "ast")


RUNNERS = {"cli": extract_cli, "config": extract_config, "http": extract_http, "py": extract_py}


def extract(cfg, kinds):
    data = facts.load_file(cfg.facts_dir, TARGET)
    data["alias"] = TARGET
    for kind in kinds:
        out = Collector(cfg, kind)
        RUNNERS[kind](cfg, out)
        prefix = f"{kind}."
        # 다시 뽑으면 그 종류의 옛 키는 지운다(코드에서 사라진 옵션이 사실로 남지 않게)
        data["facts"] = {k: v for k, v in data["facts"].items() if not k.startswith(prefix)}
        data["facts"].update(out.items)
        print(f"[code] {kind}: 사실 {len(out.items)}개")
    write_json(facts.path_for(cfg.facts_dir, TARGET), data)
    print(f"→ {cfg.rel(facts.path_for(cfg.facts_dir, TARGET))}")
    return 0
