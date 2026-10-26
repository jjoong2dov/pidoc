"""명령줄: pidoc <명령> ...

종료 코드: 0 성공, 1 검사 실패(문서 문제), 2 사용법·설정 오류, 3 수집 실패.
"""

import argparse
import json
import sys

from . import __version__, config, facts
from .util import PidocError, USAGE, age_days


def load_config(args):
    path = args.config or config.find()
    return config.load(path)


# --- 명령들 ---

def cmd_init(args):
    from .init import init
    return init(args.dir)


def cmd_collect(args):
    from .collect import collect
    cfg = load_config(args)
    return collect(cfg, args.target, args.only, args.keep_raw)


def cmd_replay(args):
    from .collect import replay
    cfg = load_config(args)
    return replay(cfg, args.runs)


def cmd_facts(args):
    cfg = load_config(args)
    every = facts.load_all(cfg.facts_dir)
    if args.target:
        every = {args.target: every.get(args.target, {})}
    if args.json:
        print(json.dumps(every, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    if not any(every.values()):
        print("사실이 없습니다. 먼저 `pidoc collect`")
        return 0
    for target, items in every.items():
        print(f"[{target}]")
        for key in sorted(items):
            f = items[key]
            age = f"{age_days(f['collected_at']):.1f}일 전" if f.get("collected_at") else "-"
            mark = " (만료)" if facts.is_expired(f) else ""
            print(f"  {key} = {facts.show_value(f['value'])}  [{f['type']}, {age}, {f.get('run', '-')}]{mark}")
    return 0


# --- 파서 ---

def parser():
    p = argparse.ArgumentParser(
        prog="pidoc",
        description="실행 증거로 기술문서를 쓰고 시험하는 도구",
    )
    p.add_argument("--version", action="version", version=f"pidoc {__version__}")
    p.add_argument("--config", help="pidoc.toml 경로 (없으면 지금 폴더부터 위로 docs/pidoc.toml 을 찾음)")
    sub = p.add_subparsers(dest="command", metavar="명령")

    s = sub.add_parser("init", help="docs/ 뼈대와 pidoc.toml 견본 만들기")
    s.add_argument("dir", nargs="?", default=".", help="대상 저장소 (기본: 지금 폴더)")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("collect", help="명령 실행 → 증거 저장 → 사실 갱신")
    s.add_argument("--target", help="이 대상만")
    s.add_argument("--only", nargs="+", metavar="ID", help="이 명령들만")
    s.add_argument("--keep-raw", action="store_true",
                   help="가리기 전 원본을 docs/evidence/private/ 에도 저장(공개 저장소에 넣지 말 것)")
    s.set_defaults(func=cmd_collect)

    s = sub.add_parser("replay", help="저장된 증거에서 사실만 다시 뽑기(실행 안 함)")
    s.add_argument("runs", help="run 폴더 하나 또는 runs 폴더")
    s.set_defaults(func=cmd_replay)

    s = sub.add_parser("facts", help="사실 목록 보기")
    s.add_argument("--target", help="이 대상만")
    s.add_argument("--json", action="store_true", help="JSON 으로")
    s.set_defaults(func=cmd_facts)

    return p


def main(argv=None):
    p = parser()
    try:
        args = p.parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else USAGE
    if not getattr(args, "func", None):
        p.print_help()
        return USAGE
    try:
        return args.func(args)
    except PidocError as e:
        print(f"pidoc: {e}", file=sys.stderr)
        return e.code
    except KeyboardInterrupt:
        print("pidoc: 중단했습니다", file=sys.stderr)
        return USAGE
