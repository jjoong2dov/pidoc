"""명령 하나를 셸 없이 실행한다.

- argv 배열을 그대로 넘긴다(shell=False). 셸 문법(파이프, $변수, ;)은 해석되지 않는다.
- 시간 초과면 프로세스 그룹째 죽인다(자식이 낳은 손자까지).
- 출력은 상한까지만 모으고 나머지는 읽어서 버린다(파이프가 막혀 멈추지 않게). 잘렸으면 truncated.
- 출력은 바이트 그대로 돌려준다. 해석(디코딩)은 사실을 뽑을 때 한다.
"""

import os
import signal
import subprocess
import threading
import time
from pathlib import Path


class Result:
    def __init__(self, argv):
        self.argv = list(argv)
        self.cwd = None
        self.stdout = b""
        self.stderr = b""
        self.exit = None          # 종료 코드. 시그널로 죽으면 음수, 실행 못 했으면 None
        self.duration_ms = 0
        self.timed_out = False
        self.stdout_truncated = False
        self.stderr_truncated = False
        self.error = None         # 실행 자체를 못 한 이유(프로그램 없음 등)

    def ok(self, ok_exit=(0,)):
        return self.error is None and not self.timed_out and self.exit in ok_exit


class _Reader(threading.Thread):
    """파이프 하나를 끝까지 읽되 limit 바이트까지만 남긴다."""

    def __init__(self, pipe, limit):
        super().__init__(daemon=True)
        self.pipe = pipe
        self.limit = limit
        self.chunks = []
        self.size = 0
        self.truncated = False

    def run(self):
        while True:
            chunk = self.pipe.read1(65536) if hasattr(self.pipe, "read1") else self.pipe.read(65536)
            if not chunk:
                break
            room = self.limit - self.size
            if room <= 0:
                self.truncated = True
                continue
            if len(chunk) > room:
                chunk = chunk[:room]
                self.truncated = True
            self.chunks.append(chunk)
            self.size += len(chunk)
        self.pipe.close()

    def data(self):
        return b"".join(self.chunks)


def build_env(env_allow, env_set, base=None):
    """허용 목록에 있는 환경변수만 넘기고 env_set 을 덧씌운다."""
    base = os.environ if base is None else base
    env = {k: base[k] for k in env_allow if k in base}
    env.update(env_set)
    return env


def run(argv, *, cwd=None, env=None, timeout=20, max_output=1048576):
    result = Result(argv)
    result.cwd = str(cwd) if cwd else None
    if cwd is not None and not Path(cwd).is_dir():
        result.error = f"작업 폴더가 없습니다: {cwd}"
        return result
    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,   # 시간 초과 때 그룹째 죽이려고
        )
    except OSError as e:
        result.error = f"실행하지 못했습니다: {e.strerror or e} ({argv[0]})"
        return result

    out = _Reader(proc.stdout, max_output)
    err = _Reader(proc.stderr, max_output)
    out.start()
    err.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        result.timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
    out.join(5)
    err.join(5)
    result.duration_ms = int((time.monotonic() - start) * 1000)
    result.exit = proc.returncode
    result.stdout, result.stdout_truncated = out.data(), out.truncated
    result.stderr, result.stderr_truncated = err.data(), err.truncated
    return result
