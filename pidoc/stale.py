"""stale: 코드가 바뀌어 다시 봐야 할 문서 찾기.

- 기본: render 때 docs/out/.deps.json 에 남긴 sha256 과 지금 파일·사실·run 을 비교
- --since REV: git diff 로 바뀐 파일 목록을 얻어, 그 파일에 기대는 문서를 고른다(CI 에서 PR 마다)
종료 코드: 0 낡은 문서 없음, 1 있음.
"""

import subprocess

from . import doc as docmod
from . import evidence, facts
from .render import fact_hash, load_deps
from .util import CHECK_FAILED, OK, PidocError, sha256_file


def git_changed(cfg, since):
    try:
        proc = subprocess.run(["git", "diff", "--name-only", since, "--"], cwd=cfg.root,
                              capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        raise PidocError("git 이 없습니다 (--since 는 git 이 필요)")
    if proc.returncode != 0:
        raise PidocError(f"git diff 실패: {proc.stderr.strip()}")
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def doc_deps(cfg, rel, info):
    """문서 하나가 기대는 파일들(렌더 기록 + 설정 + 머리말)."""
    deps = set(info.get("deps", {})) if info else set()
    deps.update(cfg.check.get("stale_deps", {}).get(rel, []))
    src = cfg.root / rel
    if src.is_file():
        deps.update(docmod.load(src, cfg.default_target).deps)
    return deps


def changed_facts_and_runs(cfg, info, all_facts):
    """렌더 뒤에 값·출처가 바뀐 사실, 더 새 출력이 생긴 run."""
    reasons = []
    used = info.get("facts", {})
    for full in sorted(used if isinstance(used, dict) else {}):
        target, _, key = full.partition(":")
        fact = all_facts.get(target, {}).get(key)
        if fact is None:
            reasons.append(f"사실 {full} 없어짐")
        elif fact_hash(fact) != used[full]:
            reasons.append(f"사실 {full} 바뀜")
    runs = info.get("runs", {})
    for name in sorted(runs if isinstance(runs, dict) else {}):
        target, _, cmd_id = name.partition(":")
        latest = evidence.latest_attempt(cfg.runs_dir, target, cmd_id)
        if latest is None:
            reasons.append(f"run {name} 없어짐")
        elif latest.name != runs[name]["run"] and (
                not evidence.run_ok(latest, cmd_id)
                or latest.record(cmd_id)["stdout"]["sha256"] != runs[name]["stdout_sha256"]):
            reasons.append(f"run {name} 바뀜({latest.name})")
    return reasons


def stale(cfg, since=None):
    records = load_deps(cfg)
    names = sorted(set(records) | set(cfg.check.get("stale_deps", {}))
                   | {cfg.rel(p) for p in docmod.src_files(cfg)})
    changed = git_changed(cfg, since) if since else None
    all_facts = facts.load_all(cfg.facts_dir)
    found = 0
    for rel in names:
        info = records.get(rel)
        reasons = []
        if changed is not None:
            hit = sorted(doc_deps(cfg, rel, info) & changed)
            reasons += [f"{f} 바뀜({since} 이후)" for f in hit]
            if rel in changed:
                reasons.append(f"원본이 바뀜({since} 이후)")
        else:
            if info is None:
                reasons.append("렌더 기록이 없습니다(pidoc render)")
            else:
                for dep, sha in sorted(info.get("deps", {}).items()):
                    path = cfg.root / dep
                    if not path.is_file():
                        reasons.append(f"{dep} 없어짐")
                    elif sha256_file(path) != sha:
                        reasons.append(f"{dep} 바뀜")
                reasons += changed_facts_and_runs(cfg, info, all_facts)
                src = cfg.root / rel
                if info.get("src_sha256") and src.is_file() and sha256_file(src) != info["src_sha256"]:
                    reasons.append("원본이 렌더 뒤에 바뀜")
        if reasons:
            found += 1
            print(f"{rel}: {', '.join(reasons)}")
    if found:
        print(f"다시 볼 문서 {found}개")
        return CHECK_FAILED
    print("낡은 문서 없음")
    return OK
