"""docs/pidoc.toml 읽기와 검사.

모르는 키는 오타일 가능성이 크므로 오류로 멈춘다(조용히 무시하지 않는다).
"""

import os
import re
import tomllib
from pathlib import Path

from .util import PidocError, sha256_file

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
KEY_RE = re.compile(r"^[a-z0-9_][a-z0-9_-]*(\.[a-z0-9_][a-z0-9_-]*)*$")

EXTRACTS = ("stdout_all", "stdout_line", "regex", "json")
TYPES = ("string", "int", "float", "list", "bool")

COLLECT_DEFAULTS = {
    "timeout_s": 20,
    "max_output": 1048576,
    "env_allow": ["PATH", "HOME", "LANG"],
    "env_set": {"LC_ALL": "C.UTF-8"},
    "allow_programs": [],
}


class Target:
    def __init__(self, name, kind, alias, host=None, cwd=None):
        self.name = name
        self.kind = kind
        self.alias = alias
        self.host = host
        self.cwd = cwd


class Config:
    """읽은 설정. 경로는 모두 절대 경로로 바꿔 둔다."""

    def __init__(self, path, data):
        self.path = Path(path).resolve()
        self.docs_dir = self.path.parent
        self.data = data
        project = data.get("project", {})
        self.name = project.get("name", "")
        self.root = (self.docs_dir / project.get("root", "..")).resolve()
        self.targets = {}
        self.commands = data.get("command", [])
        self.collect = dict(COLLECT_DEFAULTS, **data.get("collect", {}))
        self.default_target = project.get("default_target")
        self.redact = data.get("redact", {})
        self.extract = data.get("extract", {})
        self.ai = data.get("ai", {})

    # 자주 쓰는 폴더
    @property
    def runs_dir(self):
        return self.docs_dir / "evidence" / "runs"

    @property
    def facts_dir(self):
        return self.docs_dir / "facts"

    @property
    def src_dir(self):
        return self.docs_dir / "src"

    @property
    def out_dir(self):
        return self.docs_dir / "out"

    @property
    def ai_dir(self):
        return self.docs_dir / "ai"

    def sha256(self):
        return sha256_file(self.path)

    def rel(self, path):
        """보고용 경로: 대상 저장소 루트 기준 상대 경로."""
        path = Path(path).resolve()
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return str(path)

    def target(self, name):
        if name not in self.targets:
            known = ", ".join(self.targets) or "(없음)"
            raise PidocError(f"모르는 대상: {name} (설정된 대상: {known})")
        return self.targets[name]

    def commands_for(self, target_name):
        return [c for c in self.commands if target_name in c["targets"]]


def _keys(table, allowed, where):
    if not isinstance(table, dict):
        raise PidocError(f"설정 오류: {where} 는 [표] 여야 합니다")
    for key in table:
        if key not in allowed:
            raise PidocError(f"설정 오류: 모르는 설정 {where}.{key} (쓸 수 있는 것: {', '.join(allowed)})")


def _type(value, kind, where):
    ok = {
        "str": isinstance(value, str) and value != "",
        "int": isinstance(value, int) and not isinstance(value, bool),
        "num": isinstance(value, (int, float)) and not isinstance(value, bool),
        "bool": isinstance(value, bool),
        "strlist": isinstance(value, list) and all(isinstance(v, str) and v for v in value),
        "strdict": isinstance(value, dict) and all(isinstance(v, str) for v in value.values()),
    }[kind]
    if not ok:
        names = {"str": "비어 있지 않은 문자열", "int": "정수", "num": "숫자", "bool": "true/false",
                 "strlist": "문자열 목록", "strdict": "문자열 값의 표"}
        raise PidocError(f"설정 오류: {where} 는 {names[kind]} 여야 합니다: {value!r}")


def _check_targets(cfg, data):
    targets = data.get("targets", {})
    if not isinstance(targets, dict) or not targets:
        raise PidocError("설정 오류: [targets.이름] 을 하나 이상 적으세요")
    for name, t in targets.items():
        where = f"targets.{name}"
        if not ID_RE.match(name):
            raise PidocError(f"설정 오류: 대상 이름은 소문자·숫자·_·- 만: {name!r}")
        _keys(t, ("kind", "host", "alias", "cwd"), where)
        kind = t.get("kind", "local")
        if kind not in ("local", "ssh"):
            raise PidocError(f"설정 오류: {where}.kind 는 local 또는 ssh: {kind!r}")
        alias = t.get("alias", name)
        _type(alias, "str", f"{where}.alias")
        # 비공개 주소는 설정 파일 대신 환경변수로 줄 수 있다: PIDOC_TARGET_PI
        host = os.environ.get(f"PIDOC_TARGET_{name.upper().replace('-', '_')}") or t.get("host")
        if kind == "ssh":
            if not host:
                raise PidocError(f"설정 오류: {where}.host 가 없습니다 (또는 PIDOC_TARGET_{name.upper()} 환경변수)")
            _type(host, "str", f"{where}.host")
            if host.startswith("-"):
                raise PidocError(f"설정 오류: {where}.host 는 - 로 시작할 수 없습니다")
        if "cwd" in t:
            _type(t["cwd"], "str", f"{where}.cwd")
        cfg.targets[name] = Target(name, kind, alias, host, t.get("cwd"))
    default = cfg.default_target or next(iter(cfg.targets))
    if default not in cfg.targets:
        raise PidocError(f"설정 오류: project.default_target 이 없는 대상입니다: {default!r}")
    cfg.default_target = default


def _check_collect(cfg):
    c = cfg.collect
    _keys(c, tuple(COLLECT_DEFAULTS), "collect")
    _type(c["timeout_s"], "num", "collect.timeout_s")
    _type(c["max_output"], "int", "collect.max_output")
    if c["timeout_s"] <= 0 or c["max_output"] <= 0:
        raise PidocError("설정 오류: collect.timeout_s·max_output 은 0 보다 커야 합니다")
    _type(c["env_allow"], "strlist", "collect.env_allow")
    _type(c["env_set"], "strdict", "collect.env_set")
    _type(c["allow_programs"], "strlist", "collect.allow_programs")


def _check_fact(rule, where):
    _keys(rule, ("key", "extract", "pattern", "line", "path", "sep", "type", "max_age_days"), where)
    key = rule.get("key")
    if not isinstance(key, str) or not KEY_RE.match(key):
        raise PidocError(f"설정 오류: {where}.key 는 소문자.점.구분 형식: {key!r}")
    extract = rule.get("extract")
    if extract not in EXTRACTS:
        raise PidocError(f"설정 오류: {where}.extract 는 {' | '.join(EXTRACTS)}: {extract!r}")
    if extract == "regex":
        _type(rule.get("pattern"), "str", f"{where}.pattern")
        try:
            re.compile(rule["pattern"])
        except re.error as e:
            raise PidocError(f"설정 오류: {where}.pattern 정규식 오류: {e}")
    if extract == "json":
        _type(rule.get("path"), "str", f"{where}.path")
    if "line" in rule:
        _type(rule["line"], "int", f"{where}.line")
    rule.setdefault("type", "string")
    if rule["type"] not in TYPES:
        raise PidocError(f"설정 오류: {where}.type 은 {' | '.join(TYPES)}: {rule['type']!r}")
    if rule.get("max_age_days") is not None:
        _type(rule["max_age_days"], "num", f"{where}.max_age_days")


def _check_commands(cfg):
    if not isinstance(cfg.commands, list):
        raise PidocError("설정 오류: 명령은 [[command]] 로 적습니다")
    seen = set()
    keys = {}
    for i, cmd in enumerate(cfg.commands):
        where = f"command[{cmd.get('id', i)}]"
        _keys(cmd, ("id", "argv", "targets", "cwd", "timeout_s", "ok_exit", "fact"), where)
        cid = cmd.get("id")
        if not isinstance(cid, str) or not ID_RE.match(cid):
            raise PidocError(f"설정 오류: {where}.id 는 소문자·숫자·_·- 만: {cid!r}")
        if cid in seen:
            raise PidocError(f"설정 오류: 명령 id 가 겹칩니다: {cid}")
        seen.add(cid)
        argv = cmd.get("argv")
        _type(argv, "strlist", f"{where}.argv")
        if not argv:
            raise PidocError(f"설정 오류: {where}.argv 가 비었습니다")
        cmd.setdefault("targets", [cfg.default_target])
        _type(cmd["targets"], "strlist", f"{where}.targets")
        for t in cmd["targets"]:
            cfg.target(t)
        if "cwd" in cmd:
            _type(cmd["cwd"], "str", f"{where}.cwd")
        if "timeout_s" in cmd:
            _type(cmd["timeout_s"], "num", f"{where}.timeout_s")
        cmd.setdefault("ok_exit", [0])
        if not isinstance(cmd["ok_exit"], list) or not all(
                isinstance(v, int) and not isinstance(v, bool) for v in cmd["ok_exit"]):
            raise PidocError(f"설정 오류: {where}.ok_exit 는 정수 목록: {cmd['ok_exit']!r}")
        cmd.setdefault("fact", [])
        for j, rule in enumerate(cmd["fact"]):
            _check_fact(rule, f"{where}.fact[{j}]")
            for t in cmd["targets"]:
                if (t, rule["key"]) in keys:
                    raise PidocError(f"설정 오류: 사실 키 {rule['key']} 를 {keys[(t, rule['key'])]} 와 {cid} 가 같이 만듭니다")
                keys[(t, rule["key"])] = cid


def _check_patterns(items, where):
    if not isinstance(items, list):
        raise PidocError(f"설정 오류: {where} 는 [{{ re = '...', to = '...' }}] 목록이어야 합니다")
    for i, item in enumerate(items):
        _keys(item, ("re", "to"), f"{where}[{i}]")
        _type(item.get("re"), "str", f"{where}[{i}].re")
        if not isinstance(item.get("to"), str):
            raise PidocError(f"설정 오류: {where}[{i}].to 는 문자열이어야 합니다")
        try:
            re.compile(item["re"])
        except re.error as e:
            raise PidocError(f"설정 오류: {where}[{i}].re 정규식 오류: {e}")


def _check_redact(cfg):
    r = cfg.redact
    _keys(r, ("patterns", "hostname", "names"), "redact")
    _check_patterns(r.get("patterns", []), "redact.patterns")
    _type(r.get("hostname", True), "bool", "redact.hostname")
    _type(r.get("names", []), "strlist", "redact.names")


def _check_extract(cfg):
    e = cfg.extract
    _keys(e, ("paths", "config_example", "config_module", "config_defaults"), "extract")
    _type(e.get("paths", ["."]), "strlist", "extract.paths")
    for key in ("config_example", "config_module", "config_defaults"):
        if key in e:
            _type(e[key], "str", f"extract.{key}")


def _check_ai(cfg):
    a = cfg.ai
    _keys(a, ("provider", "model", "timeout_s"), "ai")
    if a.get("provider", "none") not in ("claude", "codex", "none"):
        raise PidocError(f"설정 오류: ai.provider 는 claude | codex | none: {a['provider']!r}")
    if "model" in a:
        _type(a["model"], "str", "ai.model")
    if "timeout_s" in a:
        _type(a["timeout_s"], "num", "ai.timeout_s")


SECTIONS = ("project", "targets", "collect", "command", "redact", "extract", "ai")


def load(path):
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PidocError(f"설정 파일이 없습니다: {path}")
    except tomllib.TOMLDecodeError as e:
        raise PidocError(f"{path}: TOML 문법 오류: {e}")
    except UnicodeDecodeError:
        raise PidocError(f"{path}: UTF-8 로 저장해야 합니다")
    _keys(data, SECTIONS, "(맨 위)")
    _keys(data.get("project", {}), ("name", "root", "default_target"), "project")
    cfg = Config(path, data)
    _check_targets(cfg, data)
    _check_collect(cfg)
    _check_commands(cfg)
    _check_redact(cfg)
    _check_extract(cfg)
    _check_ai(cfg)
    return cfg


def find(start=None):
    """지금 폴더부터 위로 올라가며 docs/pidoc.toml 또는 pidoc.toml 을 찾는다."""
    here = Path(start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        for candidate in (folder / "docs" / "pidoc.toml", folder / "pidoc.toml"):
            if candidate.is_file():
                return candidate
    raise PidocError("pidoc.toml 을 찾지 못했습니다. 대상 저장소에서 `pidoc init` 으로 만들거나 --config 로 알려 주세요")
