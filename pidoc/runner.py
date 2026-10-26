"""명령 하나를 셸 없이 실행하고 원시 출력을 상한까지 모은다."""

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass

CHUNK = 65536


@dataclass
class Result:
    exit_code: int | None
    timed_out: bool
    error: str | None
    duration_s: float
    stdout: bytes
    stderr: bytes
    stdout_bytes: int
    stderr_bytes: int
    stdout_truncated: bool
    stderr_truncated: bool


class _Sink:
    """상한까지만 담고 나머지는 세기만 한다(파이프가 막히지 않게 끝까지 읽음)."""

    def __init__(self, stream, limit):
        self.stream = stream
        self.limit = limit
        self.buf = bytearray()
        self.total = 0
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        while True:
            chunk = self.stream.read(CHUNK)
            if not chunk:
                break
            self.total += len(chunk)
            room = self.limit - len(self.buf)
            if room > 0:
                self.buf += chunk[:room]
        self.stream.close()


def _kill_group(p):
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run(argv, *, env, cwd, timeout_s, max_output):
    start = time.monotonic()
    try:
        p = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=cwd,
            shell=False,
            start_new_session=True,
        )
    except OSError as e:
        return Result(None, False, f"실행하지 못함: {e}", time.monotonic() - start,
                      b"", b"", 0, 0, False, False)

    out = _Sink(p.stdout, max_output)
    err = _Sink(p.stderr, max_output)
    timed_out = False
    try:
        p.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(p)
        p.wait()
    # 남은 자식이 파이프를 붙잡고 있지 않게 정리한다
    _kill_group(p)
    out.thread.join()
    err.thread.join()
    return Result(
        exit_code=None if timed_out else p.returncode,
        timed_out=timed_out,
        error=f"시간 초과({timeout_s}초)" if timed_out else None,
        duration_s=round(time.monotonic() - start, 3),
        stdout=bytes(out.buf),
        stderr=bytes(err.buf),
        stdout_bytes=out.total,
        stderr_bytes=err.total,
        stdout_truncated=out.total > max_output,
        stderr_truncated=err.total > max_output,
    )
