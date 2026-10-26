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


def cmd_extract(args):
    from .extract import extract
    cfg = load_config(args)
    return extract(cfg, list(dict.fromkeys(args.kinds)))


def cmd_draft(args):
    from .draft import draft
    cfg = load_config(args)
    return draft(cfg, args.template, args.out, args.ai)


def cmd_render(args):
    from . import doc
    from .render import render
    cfg = load_config(args)
    files = doc.src_files(cfg, args.files)
    if not files:
        print(f"렌더할 문서가 없습니다: {cfg.rel(cfg.src_dir)}/*.md")
        return 0
    return render(cfg, files)


def cmd_check(args):
    from .checks import check
    cfg = load_config(args)
    return check(cfg, args.files, args.only, args.json, args.rerun)


def cmd_stale(args):
    from .stale import stale
    cfg = load_config(args)
    return stale(cfg, args.since)


def cmd_build(args):
    from .build import build
    cfg = load_config(args)
    return build(cfg, args.pdf)


def cmd_notes(args):
    from .notes import notes
    cfg = load_config(args)
    return notes(cfg, args.range, args.template, args.out, args.ai, args.check)


def cmd_report(args):
    from .report import report
    cfg = load_config(args)
    return report(cfg, args.junit, args.template, args.out)


def cmd_i18n(args):
    from .i18n import i18n_check
    return i18n_check(args.original, args.translation)


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

    s = sub.add_parser("collect", help="명령 실행 → 증거 저장 → 사실 갱신",
                       description="pidoc.toml 의 명령을 셸 없이 실행해 증거를 남기고 사실을 뽑는다. "
                                   "collect.allow_programs 는 보안 경계가 아니라 실수 방지 목록이다"
                                   "(허용한 프로그램이 할 수 있는 일은 다 할 수 있다).")
    s.add_argument("--target", help="이 대상만")
    s.add_argument("--only", nargs="+", metavar="ID", help="이 명령들만")
    s.add_argument("--keep-raw", action="store_true",
                   help="가리기 전 원본을 docs/evidence/private/ 에도 저장(공개 저장소에 넣지 말 것)")
    s.set_defaults(func=cmd_collect)

    s = sub.add_parser("replay", help="저장된 증거에서 사실만 다시 뽑기(실행 안 함)")
    s.add_argument("runs", help="run 폴더 하나 또는 runs 폴더")
    s.set_defaults(func=cmd_replay)

    s = sub.add_parser("extract", help="코드에서 레퍼런스 사실 뽑기(facts/code.json)")
    s.add_argument("kinds", nargs="+", choices=["cli", "config", "http", "py"], help="뽑을 종류")
    s.set_defaults(func=cmd_extract)

    s = sub.add_parser("draft", help="틀 + 사실 목록으로 AI 초안 만들기")
    s.add_argument("template", help="틀 Markdown")
    s.add_argument("--out", required=True, help="초안을 쓸 곳 (예: docs/src/usage.md)")
    s.add_argument("--ai", choices=["claude", "codex", "none"], help="부를 AI (기본: 설정 [ai] provider, 없으면 none)")
    s.set_defaults(func=cmd_draft)

    s = sub.add_parser("render", help="docs/src → docs/out (사실·인용 채우기)")
    s.add_argument("files", nargs="*", help="이 문서들만 (기본: docs/src/*.md 전부)")
    s.set_defaults(func=cmd_render)

    s = sub.add_parser("check", help="문서 시험 (facts·numbers·quote·run·links·terms·secrets)")
    s.add_argument("files", nargs="*", help="이 문서들만 (기본: docs/src/*.md 전부)")
    s.add_argument("--only", nargs="+", metavar="검사", help="이 검사들만")
    s.add_argument("--json", action="store_true", help="결과를 JSON 으로")
    s.add_argument("--rerun", action="store_true", help="pidoc-run 블록을 지금 다시 실행해 비교")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("stale", help="코드가 바뀌어 다시 봐야 할 문서 찾기")
    s.add_argument("--since", metavar="REV", help="git 의 이 판 이후 바뀐 파일로 판단 (예: origin/main)")
    s.set_defaults(func=cmd_stale)

    s = sub.add_parser("build", help="render 후 HTML 한 파일(+ 선택 PDF)")
    s.add_argument("--pdf", action="store_true", help="PDF 도 만들기 (WeasyPrint 필요)")
    s.set_defaults(func=cmd_build)

    s = sub.add_parser("notes", help="git 커밋 → 사실 → 릴리스 노트 초안(해시 검사)")
    s.add_argument("range", help="git 범위 (예: v0.2..v0.3)")
    s.add_argument("--template", help="틀 Markdown (기본: 내장 틀)")
    s.add_argument("--out", help="초안 쓸 곳 (기본: docs/src/release-notes.md)")
    s.add_argument("--ai", choices=["claude", "codex", "none"], help="부를 AI")
    s.add_argument("--check", metavar="파일", help="AI 를 부르지 않고 이 파일의 커밋 해시만 검사")
    s.set_defaults(func=cmd_notes)

    s = sub.add_parser("report", help="pytest JUnit XML → 사실 → 시험 보고서")
    s.add_argument("junit", help="pytest --junitxml 로 만든 파일")
    s.add_argument("--template", help="틀 Markdown (기본: 내장 틀)")
    s.add_argument("--out", help="보고서 쓸 곳 (기본: docs/out/test-report.md)")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("i18n-check", help="원본과 번역본의 코드·자리표시자·링크·숫자 비교")
    s.add_argument("original")
    s.add_argument("translation")
    s.set_defaults(func=cmd_i18n)

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
