"""명령줄 진입점."""

import argparse
import sys

from . import settings


def build_parser():
    """명령줄 파서를 만든다."""
    p = argparse.ArgumentParser(prog="minimon", description="디스크 사용률 감시")
    p.add_argument("command", choices=["scan", "serve"])
    p.add_argument("--config", help="설정 파일")
    p.add_argument("-l", "--limit", type=int, default=90, help="경고 기준(%%)")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    cfg = settings.load(args.config)
    print(args.command, cfg["path"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
