"""docs/pidoc.toml 읽기와 검사."""

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
# [사용자@]호스트. '-' 로 시작하면 ssh 옵션으로 읽히므로 막는다.
HOST_RE = re.compile(r"^(?:[A-Za-z0-9_][\w.-]*@)?[A-Za-z0-9_][\w.-]*$", re.ASCII)
EXTRACTS = {"stdout_all", "stdout_line", "regex", "json"}
TYPES = {"string", "int", "float", "list", "bool"}
TARGET_KINDS = {"local", "ssh"}


class ConfigError(Exception):
    pass


@dataclass
class Fact:
    key: str
    extract: str
    type: str
    pattern: str | None = None
    group: int | None = None
    line: int | None = None
    path: str = ""


@dataclass
class Command:
    id: str
    argv: list[str]
    targets: list[str]
    facts: list[Fact] = field(default_factory=list)


@dataclass
class Target:
    name: str
    kind: str
    alias: str
    host: str | None = None
    known_hosts: Path | None = None
    allow_programs: list[str] = field(default_factory=list)


@dataclass
class Config:
    path: Path
    docs: Path
    root: Path
    name: str
    targets: dict[str, Target]
    timeout_s: float
    max_output: int
    env_allow: list[str]
    env_set: dict[str, str]
    commands: list[Command]

    @property
    def runs_dir(self):
        return self.docs / "evidence" / "runs"

    @property
    def facts_dir(self):
        return self.docs / "facts"

    @property
    def src_dir(self):
        return self.docs / "src"

    @property
    def out_dir(self):
        return self.docs / "out"


def _need(cond, msg):
    if not cond:
        raise ConfigError(msg)


def _is_str_list(v):
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def load(path):
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"설정 파일이 없음: {path}")
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"설정 파일을 읽지 못함: {path}: {e}")

    docs = path.resolve().parent
    project = data.get("project", {})
    _need(isinstance(project, dict), "[project] 가 표가 아님")
    name = project.get("name")
    _need(isinstance(name, str) and name, "project.name 이 필요함")
    root = project.get("root", "..")
    _need(isinstance(root, str), "project.root 는 문자열이어야 함")

    targets = {}
    raw_targets = data.get("targets", {})
    _need(isinstance(raw_targets, dict) and raw_targets, "[targets.*] 가 하나 이상 필요함")
    for tname, t in raw_targets.items():
        _need(ID_RE.match(tname), f"대상 이름이 올바르지 않음: {tname!r}")
        _need(isinstance(t, dict), f"targets.{tname} 가 표가 아님")
        kind = t.get("kind")
        _need(kind in TARGET_KINDS, f"targets.{tname}.kind 를 지원하지 않음: {kind!r}")
        alias = t.get("alias", tname)
        _need(isinstance(alias, str), f"targets.{tname}.alias 는 문자열이어야 함")
        target = Target(tname, kind, alias)
        if kind == "ssh":
            _load_ssh(target, t, docs)
        targets[tname] = target

    col = data.get("collect", {})
    _need(isinstance(col, dict), "[collect] 가 표가 아님")
    timeout_s = col.get("timeout_s", 20)
    _need(isinstance(timeout_s, (int, float)) and not isinstance(timeout_s, bool) and timeout_s > 0,
          "collect.timeout_s 는 0보다 큰 수여야 함")
    max_output = col.get("max_output", 1048576)
    _need(isinstance(max_output, int) and not isinstance(max_output, bool) and max_output > 0,
          "collect.max_output 은 0보다 큰 정수여야 함")
    env_allow = col.get("env_allow", ["PATH", "HOME", "LANG"])
    _need(_is_str_list(env_allow), "collect.env_allow 는 문자열 목록이어야 함")
    env_set = col.get("env_set", {})
    _need(isinstance(env_set, dict) and all(isinstance(v, str) for v in env_set.values()),
          "collect.env_set 은 문자열 값의 표여야 함")

    commands = []
    seen_ids = set()
    seen_keys = set()
    raw_cmds = data.get("command", [])
    _need(isinstance(raw_cmds, list), "[[command]] 형식이 올바르지 않음")
    for c in raw_cmds:
        _need(isinstance(c, dict), "[[command]] 형식이 올바르지 않음")
        cid = c.get("id")
        _need(isinstance(cid, str) and ID_RE.match(cid), f"명령 id 가 올바르지 않음: {cid!r}")
        _need(cid not in seen_ids, f"명령 id 가 겹침: {cid}")
        seen_ids.add(cid)
        argv = c.get("argv")
        _need(_is_str_list(argv) and argv, f"{cid}: argv 는 비어 있지 않은 문자열 목록이어야 함")
        ctargets = c.get("targets")
        _need(_is_str_list(ctargets) and ctargets, f"{cid}: targets 목록이 필요함")
        for t in ctargets:
            _need(t in targets, f"{cid}: 없는 대상: {t}")
        facts = []
        raw_facts = c.get("fact", [])
        _need(isinstance(raw_facts, list), f"{cid}: [[command.fact]] 형식이 올바르지 않음")
        for f in raw_facts:
            facts.append(_load_fact(cid, f))
        for t in ctargets:
            for f in facts:
                _need((t, f.key) not in seen_keys, f"{cid}: 사실 키가 겹침: {t}:{f.key}")
                seen_keys.add((t, f.key))
        commands.append(Command(cid, list(argv), list(ctargets), facts))

    return Config(
        path=path,
        docs=docs,
        root=(docs / root).resolve(),
        name=name,
        targets=targets,
        timeout_s=float(timeout_s),
        max_output=max_output,
        env_allow=list(env_allow),
        env_set=dict(env_set),
        commands=commands,
    )


def _host_env_name(tname):
    return "PIDOC_TARGET_" + re.sub(r"[^A-Za-z0-9]", "_", tname).upper()


def _load_ssh(target, t, docs):
    where = f"targets.{target.name}"
    env_name = _host_env_name(target.name)
    host = os.environ.get(env_name) or t.get("host")
    _need(isinstance(host, str) and HOST_RE.match(host),
          f"{where}.host(또는 {env_name}) 가 올바르지 않음: {host!r}")
    kh = t.get("known_hosts")
    _need(isinstance(kh, str) and kh, f"{where}.known_hosts 가 필요함")
    kh_path = (docs / Path(kh).expanduser()).resolve()
    # ssh -o 값 안에서 공백·따옴표·% 는 따로 해석되므로 받지 않는다
    _need(not re.search(r"[\s\"'%]", str(kh_path)),
          f"{where}.known_hosts 경로에 공백·따옴표·% 를 쓸 수 없음: {kh_path}")
    allow = t.get("allow_programs", [])
    _need(_is_str_list(allow), f"{where}.allow_programs 는 문자열 목록이어야 함")
    target.host, target.known_hosts, target.allow_programs = host, kh_path, list(allow)


def _load_fact(cid, f):
    _need(isinstance(f, dict), f"{cid}: fact 가 표가 아님")
    key = f.get("key")
    _need(isinstance(key, str) and key, f"{cid}: fact.key 가 필요함")
    where = f"{cid}/{key}"
    extract = f.get("extract")
    _need(extract in EXTRACTS, f"{where}: extract 를 지원하지 않음: {extract!r}")
    ftype = f.get("type", "string")
    _need(ftype in TYPES, f"{where}: type 을 지원하지 않음: {ftype!r}")
    fact = Fact(key, extract, ftype)
    if extract == "regex":
        pattern = f.get("pattern")
        _need(isinstance(pattern, str), f"{where}: regex 에는 pattern 이 필요함")
        try:
            rx = re.compile(pattern)
        except re.error as e:
            raise ConfigError(f"{where}: pattern 이 올바르지 않음: {e}")
        group = f.get("group", 1 if rx.groups else 0)
        _need(isinstance(group, int) and 0 <= group <= rx.groups, f"{where}: group 이 올바르지 않음")
        fact.pattern, fact.group = pattern, group
    elif extract == "stdout_line":
        line = f.get("line", 1)
        _need(isinstance(line, int) and not isinstance(line, bool) and line >= 1,
              f"{where}: line 은 1 이상의 정수여야 함")
        fact.line = line
    elif extract == "json":
        p = f.get("path", "")
        _need(isinstance(p, str), f"{where}: path 는 문자열이어야 함")
        fact.path = p
    return fact
