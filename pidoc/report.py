"""report: pytest JUnit XML → 사실(대상 "test") → 보고서 틀을 render.

  pytest --junitxml=docs/evidence/junit.xml
  pidoc report docs/evidence/junit.xml
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from . import doc as docmod
from . import facts
from .render import render_doc
from .util import CHECK_FAILED, OK, PidocError, iso, now, sha256_bytes, write_json

TEMPLATE = """\
<!-- pidoc-target: test -->
# 시험 보고서

- 시험 {{fact:test.tests}}개 중 통과 {{fact:test.passed}}개
- 실패 {{fact:test.failures}}개, 오류 {{fact:test.errors}}개, 건너뜀 {{fact:test.skipped}}개
- 걸린 시간 {{fact:test.time|round1}}초
- 실패한 시험: {{fact:test.failed_cases|join}}
- 원본: {{fact:test.source|code}}
"""


def parse_junit(data):
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise PidocError(f"JUnit XML 이 아닙니다: {e}")
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    if root.tag not in ("testsuite", "testsuites"):
        raise PidocError(f"JUnit XML 이 아닙니다(맨 위가 {root.tag})")
    total = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    time = 0.0
    failed = []
    for suite in suites:
        for key in total:
            total[key] += int(suite.get(key, 0))
        time += float(suite.get("time", 0))
        for case in suite.iter("testcase"):
            if case.find("failure") is not None or case.find("error") is not None:
                failed.append(f"{case.get('classname', '')}::{case.get('name', '')}".lstrip(":"))
    total["passed"] = total["tests"] - total["failures"] - total["errors"] - total["skipped"]
    return total, round(time, 3), failed


def report(cfg, junit, template=None, out=None):
    junit = Path(junit)
    if not junit.is_file():
        raise PidocError(f"파일이 없습니다: {junit}")
    data = junit.read_bytes()
    total, time, failed = parse_junit(data)
    common = {"run": f"junit {junit.name}", "command": "pytest", "extract": "junit",
              "source_sha256": sha256_bytes(data), "collected_at": iso(now()), "max_age_days": None}
    values = {f"test.{k}": v for k, v in total.items()}
    values.update({"test.time": time, "test.failed_cases": failed, "test.source": junit.name})
    new = {k: dict(common, value=v, type=facts.type_of(v)) for k, v in values.items()}
    write_json(facts.path_for(cfg.facts_dir, "test"), {"schema": 1, "target": "test", "alias": "test", "facts": new})
    print(f"[test] 시험 {total['tests']}개, 실패 {total['failures']}, 오류 {total['errors']}")

    tpath = Path(template) if template else cfg.docs_dir / "report-template.md"
    text = tpath.read_text(encoding="utf-8") if template else TEMPLATE
    d = docmod.Doc(tpath, text, "test")
    rendered, errors, _ = render_doc(cfg, d, facts.load_all(cfg.facts_dir))
    if errors:
        for n, msg in errors:
            print(f"{cfg.rel(tpath)}:{n}: [render] {msg}")
        return CHECK_FAILED
    out = cfg.inside(out, "--out", base=Path.cwd()) if out else cfg.out_dir / "test-report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rendered, encoding="utf-8")
    print(f"보고서: {cfg.rel(out)}")
    return OK
