"""pidoc stale: render 때 남긴 원본 파일·사실 sha256 과 지금을 견줘 다시 볼 문서를 알린다."""

import hashlib
import json
import os
import sys

from pidoc.verify import FactsError, load_all

DEPS = ".deps.json"


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def fact_sha(rec):
    # run·시각은 빼고 값과 타입만 본다(다시 모아도 값이 같으면 낡지 않음)
    data = {"type": rec.get("type"), "value": rec.get("value")}
    return _sha(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _file_sha(path):
    try:
        return _sha(path.read_bytes())
    except OSError:
        return None


def doc_deps(cfg, text, files, used, facts):
    """문서 하나의 기록: 원본 문서·인용 파일·쓴 사실의 sha256."""
    return {
        "src": _sha(text.encode("utf-8")),
        "files": {rel: _file_sha(cfg.root / rel) for rel in sorted(files)},
        "facts": {f"{t}:{k}": fact_sha(facts[t][k]) for t, k in sorted(used)},
    }


def write_deps(cfg, deps):
    path = cfg.out_dir / DEPS
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(deps, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def _reasons(cfg, name, dep, facts):
    src = _file_sha(cfg.src_dir / name)
    if src is None:
        return ["원본 문서가 없어짐"]
    why = [] if src == dep.get("src") else ["원본 문서가 바뀜"]
    for rel, old in dep.get("files", {}).items():
        now = _file_sha(cfg.root / rel)
        if now is None:
            why.append(f"파일 {rel} 가 없어짐")
        elif now != old:
            why.append(f"파일 {rel} 가 바뀜")
    for ref, old in dep.get("facts", {}).items():
        t, _, k = ref.partition(":")
        rec = facts.get(t, {}).get(k)
        if rec is None:
            why.append(f"사실 {ref} 가 없어짐")
        elif fact_sha(rec) != old:
            why.append(f"사실 {ref} 값이 바뀜")
    return why


def stale(cfg):
    path = cfg.out_dir / DEPS
    if not path.is_file():
        print(f"렌더 기록이 없음: out/{DEPS} — pidoc render 를 먼저 할 것", file=sys.stderr)
        return 2
    try:
        deps = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(deps, dict) or not all(isinstance(v, dict) for v in deps.values()):
            raise ValueError("형식이 올바르지 않음")
    except (OSError, UnicodeDecodeError, ValueError) as e:
        print(f"렌더 기록을 읽지 못함: out/{DEPS}: {e} — pidoc render 를 다시 할 것", file=sys.stderr)
        return 2
    try:
        facts = load_all(cfg)
    except FactsError as e:
        print(e, file=sys.stderr)
        return 1
    names = set(deps)
    if cfg.src_dir.is_dir():
        names |= {p.name for p in cfg.src_dir.glob("*.md") if p.is_file()}
    n = 0
    for name in sorted(names):
        why = _reasons(cfg, name, deps[name], facts) if name in deps else ["렌더 기록에 없음(새 문서)"]
        if why:
            n += 1
            print(f"다시 볼 문서: out/{name}")
            for w in why:
                print(f"    - {w}")
    print(f"다시 볼 문서 {n}개 (문서 {len(names)}개)")
    return 1 if n else 0
