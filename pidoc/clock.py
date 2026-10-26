"""시각. 시험에서는 PIDOC_NOW 로 고정한다."""

import os
from datetime import datetime, timezone


def now():
    fixed = os.environ.get("PIDOC_NOW")
    if fixed:
        t = datetime.fromisoformat(fixed.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def run_stamp(t):
    return t.strftime("%Y%m%dT%H%M%SZ")
