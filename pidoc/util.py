"""여러 모듈이 같이 쓰는 작은 도우미: 오류·시각·JSON·해시."""

import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

# 종료 코드
OK = 0
CHECK_FAILED = 1   # 문서 문제
USAGE = 2          # 사용법·설정 오류
COLLECT_FAILED = 3 # 명령 실패·시간 초과


class PidocError(Exception):
    """사용자에게 보여 줄 오류. code 는 종료 코드."""

    def __init__(self, message, code=USAGE):
        super().__init__(message)
        self.code = code


def now():
    """지금 시각(오프셋 포함). 시험에서는 PIDOC_NOW 로 시계를 고정한다."""
    fixed = os.environ.get("PIDOC_NOW")
    if fixed:
        try:
            value = datetime.fromisoformat(fixed)
        except ValueError:
            raise PidocError(f"PIDOC_NOW 형식이 이상합니다: {fixed!r} (예: 2026-10-26T23:15:00+09:00)")
        if value.tzinfo is None:
            value = value.astimezone()
        return value
    return datetime.now().astimezone()


def iso(t):
    return t.isoformat(timespec="seconds")


def parse_iso(text):
    return datetime.fromisoformat(text)


def age_days(collected_at, at=None):
    at = at or now()
    return (at - parse_iso(collected_at)) / timedelta(days=1)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def dumps(obj):
    """결정적 JSON: 키 정렬, 들여쓰기 2, 끝 개행."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(obj), encoding="utf-8")


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PidocError(f"{path}: JSON 이 깨졌습니다: {e}")
