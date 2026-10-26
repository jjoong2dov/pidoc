"""notes: git 커밋 목록을 사실(대상 "git")로 만들고 틀로 릴리스 노트 초안을 쓴다.

초안에 적힌 커밋 해시가 정말 그 범위 안에 있는지 검사한다(AI 가 해시를 지어내는 것을 막는다).
"""

import re
import subprocess
from pathlib import Path

from . import ai, facts
from .checks import numbers
from .draft import RULES
from .util import CHECK_FAILED, OK, PidocError, iso, now, sha256_bytes, write_json

TEMPLATE = """\
# 릴리스 노트 ({{fact:git:git.range}})

## 새 기능

## 고친 것

## 그 밖의 것
"""

NOTES_RULES = """\
5. 각 항목 끝에 근거가 된 커밋의 짧은 해시를 괄호로 적어라. 예: (a1b2c3d)
   아래 '커밋 목록'에 없는 해시는 절대 쓰지 마라. 목록에 없는 변경은 쓰지 마라.
"""

HASH_RE = re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{7,40}(?![0-9A-Za-z])")


def git_log(cfg, rev_range):
    try:
        proc = subprocess.run(["git", "log", "--no-color", "--format=%H%x1f%h%x1f%s%x1f%aI", rev_range, "--"],
                              cwd=cfg.root, capture_output=True, timeout=60)
    except FileNotFoundError:
        raise PidocError("git 이 없습니다")
    if proc.returncode != 0:
        raise PidocError(f"git log 실패: {proc.stderr.decode('utf-8', 'replace').strip()}")
    commits = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        full, short, subject, date = line.split("\x1f")
        commits.append({"hash": full, "short": short, "subject": subject, "date": date})
    return commits, proc.stdout


def save_facts(cfg, rev_range, commits, raw):
    at = iso(now())
    common = {"run": f"git-log {rev_range}", "command": "git log", "extract": "git",
              "source_sha256": sha256_bytes(raw), "collected_at": at, "max_age_days": None}
    values = {
        "git.range": rev_range,
        "git.count": len(commits),
        "git.commits": [f"{c['short']} {c['subject']}" for c in commits],
        "git.hashes": [c["hash"] for c in commits],
    }
    new = {k: dict(common, value=v, type=facts.type_of(v)) for k, v in values.items()}
    # 범위가 바뀌면 옛 목록은 의미가 없으므로 통째로 바꾼다
    write_json(facts.path_for(cfg.facts_dir, "git"), {"schema": 1, "target": "git", "alias": "git", "facts": new})


def bad_hashes(text, commits):
    """범위 밖 해시: (줄 번호, 해시). 숫자가 하나도 없는 낱말(예: 'deadbeef' 아닌 'facade')은 해시로 보지 않는다."""
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        for m in HASH_RE.finditer(line):
            h = m.group(0)
            if not re.search(r"\d", h):
                continue
            if not any(c["hash"].startswith(h) for c in commits):
                found.append((n, h))
    return found


def build_prompt(template, commits):
    lines = [RULES + NOTES_RULES, "## 커밋 목록"]
    lines += [f"- {c['short']} {c['subject']}" for c in commits] or ["(없음)"]
    lines += ["", "## 틀", template]
    return "\n".join(lines) + "\n"


def report_problems(cfg, out, text, commits):
    problems = 0
    for n, h in bad_hashes(text, commits):
        print(f"{cfg.rel(out)}:{n}: [notes] 범위 밖 커밋 해시: {h}")
        problems += 1
    # 범위 안 해시는 숫자로 세지 않는다(숫자로만 된 짧은 해시 '8518830' 도 있다)
    def blank(m):
        ok = any(c["hash"].startswith(m.group(0)) for c in commits)
        return " " * len(m.group(0)) if ok else m.group(0)
    plain = HASH_RE.sub(blank, text)
    for n, level, msg in numbers.scan_text(plain, cfg.check.get("number_allow", [])):
        if level == "error":
            print(f"{cfg.rel(out)}:{n}: [numbers] {msg}")
            problems += 1
    return problems


def notes(cfg, rev_range, template=None, out=None, provider=None, check_file=None):
    commits, raw = git_log(cfg, rev_range)
    save_facts(cfg, rev_range, commits, raw)
    print(f"[git] {rev_range}: 커밋 {len(commits)}개 → {cfg.rel(facts.path_for(cfg.facts_dir, 'git'))}")
    if check_file:
        path = Path(check_file)
        problems = report_problems(cfg, path, path.read_text(encoding="utf-8"), commits)
        return CHECK_FAILED if problems else OK
    template_text = Path(template).read_text(encoding="utf-8") if template else TEMPLATE
    text, record = ai.call(cfg, provider, build_prompt(template_text, commits), "notes")
    if text is None:
        print(f"AI 를 부르지 않고 프롬프트만 저장했습니다: {cfg.rel(record / 'prompt.txt')}")
        return OK
    out = cfg.inside(out, "--out", base=Path.cwd()) if out else cfg.src_dir / "release-notes.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    text = ai.strip_fence(text)
    out.write_text(text, encoding="utf-8")
    print(f"초안: {cfg.rel(out)} (호출 기록 {cfg.rel(record)})")
    return CHECK_FAILED if report_problems(cfg, out, text, commits) else OK
