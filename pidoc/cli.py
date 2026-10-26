"""명령줄 입구."""

import argparse
import sys

from pidoc import config
from pidoc.collect import collect
from pidoc.draft import draft
from pidoc.facts import build_facts


def parser():
    p = argparse.ArgumentParser(prog="pidoc", description="실행 증거로 기술문서를 만든다.")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="명령")
    c = sub.add_parser("collect", help="명령을 실행해 증거를 남긴다")
    c.add_argument("--config", default="docs/pidoc.toml", help="설정 파일(기본 docs/pidoc.toml)")
    f = sub.add_parser("facts", help="증거에서 사실을 뽑는다")
    f.add_argument("--config", default="docs/pidoc.toml", help="설정 파일(기본 docs/pidoc.toml)")
    f.add_argument("--run", help="쓸 run id(기본 가장 최근)")
    d = sub.add_parser("draft", help="틀과 사실로 AI 초안을 만든다")
    d.add_argument("--config", default="docs/pidoc.toml", help="설정 파일(기본 docs/pidoc.toml)")
    d.add_argument("template", help="틀 마크다운 파일")
    d.add_argument("--out", help="초안을 쓸 파일(--ai none 이면 쓰지 않음)")
    d.add_argument("--ai", required=True, choices=["claude", "codex", "none"],
                   help="부를 AI(none 이면 프롬프트만 저장)")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        cfg = config.load(args.config)
    except config.ConfigError as e:
        print(f"설정 오류: {e}", file=sys.stderr)
        return 2
    if args.cmd == "collect":
        return collect(cfg)
    if args.cmd == "draft":
        return draft(cfg, args.template, args.out, args.ai)
    return build_facts(cfg, args.run)
