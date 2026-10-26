"""check: 문서 시험. 검사마다 모듈 하나, run(ctx) → [Finding].

결과 형식: `파일:줄: [검사] 메시지`, 경고는 메시지 앞에 '경고:'. 오류가 하나라도 있으면 종료 1.
"""

import importlib
import json

from .. import doc as docmod
from ..facts import load_all as load_facts
from ..util import CHECK_FAILED, OK, PidocError, now

NAMES = ("facts", "numbers")


class Finding:
    def __init__(self, file, line, check, message, level="error"):
        self.file = file
        self.line = line
        self.check = check
        self.message = message
        self.level = level

    def text(self):
        where = f"{self.file}:{self.line}:" if self.line else f"{self.file}:"
        warn = "경고: " if self.level == "warn" else ""
        return f"{where} [{self.check}] {warn}{self.message}"

    def as_dict(self):
        return {"file": self.file, "line": self.line, "check": self.check,
                "level": self.level, "message": self.message}


class Context:
    """검사들이 같이 보는 것."""

    def __init__(self, cfg, files, all_files, rerun=False):
        self.cfg = cfg
        self.docs = [docmod.load(f, cfg.default_target) for f in files]
        self.all_files = all_files      # 파일을 고르지 않고 전부 검사하는가
        self.facts = load_facts(cfg.facts_dir)
        self.now = now()
        self.rerun = rerun


def run_checks(ctx, only=None):
    names = only or NAMES
    for name in names:
        if name not in NAMES:
            raise PidocError(f"모르는 검사: {name} (있는 것: {', '.join(NAMES)})")
    findings = []
    for name in names:
        module = importlib.import_module(f".{name}", __name__)
        findings += module.run(ctx)
    return findings


def check(cfg, names=None, only=None, as_json=False, rerun=False):
    files = docmod.src_files(cfg, names)
    ctx = Context(cfg, files, all_files=not names, rerun=rerun)
    findings = run_checks(ctx, only)
    errors = [f for f in findings if f.level == "error"]
    warns = [f for f in findings if f.level == "warn"]
    if as_json:
        print(json.dumps({"files": [cfg.rel(f) for f in files], "errors": len(errors), "warnings": len(warns),
                          "findings": [f.as_dict() for f in findings]},
                         ensure_ascii=False, sort_keys=True, indent=2))
    else:
        for f in findings:
            print(f.text())
        print(f"문서 {len(files)}개 검사: 오류 {len(errors)}, 경고 {len(warns)}")
    return CHECK_FAILED if errors else OK
