"""인용·출력 블록: ```lang pidoc-quote=경로#La-Lb, ```lang pidoc-run=[대상:]명령id."""

import hashlib
import json
import re
from dataclasses import dataclass

from pidoc.facts import find_run
from pidoc.redact import Redactor

OPEN_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
QUOTE_RE = re.compile(r"^(.*)#L(\d+)-L(\d+)$")
MASK = "[mask]"
_MON = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
_DAY = r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)"
TIME_RES = [
    # 2026-01-02T03:04:05Z, 2026-01-02 03:04:05.123+09:00, 2026-01-02
    re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?"
               r"(?:Z|[+-]\d{2}:?\d{2})?)?"),
    # date 명령: Fri Jan  2 03:04:05 UTC 2026 / syslog: Jan  2 03:04:05
    re.compile(rf"\b(?:{_DAY},? +)?{_MON} +\d{{1,2}},? +\d{{1,2}}:\d{{2}}(?::\d{{2}})?"
               r"(?: +[A-Z]{2,5})?(?: +\d{4})?\b"),
    re.compile(r"\b\d{1,2}:\d{2}:\d{2}(?:[.,]\d+)?\b"),
]
# 설정에 없는 호스트 이름은 사설·예약 접미사로만 알아본다
LOCAL_HOST_RE = re.compile(
    r"(?<![\w.-])[A-Za-z0-9](?:[\w-]*[A-Za-z0-9])?(?:\.[\w-]+)*"
    r"\.(?:local|lan|home|internal|localdomain|example|test|invalid)(?![\w-])", re.ASCII)


class BlockError(Exception):
    pass


@dataclass
class Block:
    line: int        # 여는 울타리 줄(1부터)
    indent: str
    fence: str
    info: str        # 울타리 뒤 나머지(앞 공백 포함)
    kind: str        # quote | run
    arg: str
    body: str        # 들여쓰기를 뗀 본문
    closed: bool

    @property
    def label(self):
        return f"pidoc-{self.kind}={self.arg}"


def _lines(text):
    # 마크다운 줄 끝은 \n 만 본다(str.splitlines 는 \x0c 등에서도 자른다)
    return re.findall(r"[^\n]*\n|[^\n]+$", text)


def _closes(line, fence):
    return re.match(rf" {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*$", line.rstrip("\n"))


def _directive(info):
    for w in info.split():
        for kind in ("quote", "run"):
            if w.startswith(f"pidoc-{kind}="):
                return kind, w.partition("=")[2]
    return None, None


def _dedent(line, n):
    k = len(line) - len(line.lstrip(" "))
    return line[min(k, n):]


def split(text):
    """[(시작 줄, 문자열 | Block)]. pidoc 블록만 Block 으로 떼고 나머지는 그대로 둔다."""
    lines = _lines(text)
    parts, buf, start = [], [], 1
    i = 0
    while i < len(lines):
        m = OPEN_RE.match(lines[i].rstrip("\n"))
        # ``` 울타리의 정보 문자열에는 ` 가 올 수 없다(인라인 코드)
        if not m or (m.group(2)[0] == "`" and "`" in m.group(3)):
            if not buf:
                start = i + 1
            buf.append(lines[i])
            i += 1
            continue
        indent, fence, info = m.groups()
        j = i + 1
        while j < len(lines) and not _closes(lines[j], fence):
            j += 1
        kind, arg = _directive(info)
        if kind is None:
            # 보통 코드 블록은 통째로 글로 둔다(안의 예시를 블록으로 읽지 않게)
            if not buf:
                start = i + 1
            buf.extend(lines[i:j + 1])
            i = j + 1
            continue
        if buf:
            parts.append((start, "".join(buf)))
            buf = []
        body = "".join(_dedent(ln, len(indent)) for ln in lines[i + 1:j])
        parts.append((i + 1, Block(i + 1, indent, fence, info, kind, arg, body, j < len(lines))))
        i = j + 1
    if buf:
        parts.append((start, "".join(buf)))
    return parts


def blocks(text):
    return [p for _, p in split(text) if isinstance(p, Block)]


def as_body(content):
    """블록 본문 꼴: 비어 있지 않으면 \\n 으로 끝난다."""
    return content + "\n" if content and not content.endswith("\n") else content


def fenced(b, content):
    """내용을 울타리로 싼다. 내용 속 울타리보다 길게 해서 블록이 깨지지 않게 한다."""
    content = as_body(content)
    ch = b.fence[0]
    # 줄 머리의 울타리 문자 줄기(\r 도 줄 끝으로 치는 렌더러가 있어 함께 본다)
    runs = [len(m.group(1)) for m in re.finditer(rf"(?:^|[\r\n])[ \t]*({re.escape(ch)}+)", content)]
    fence = ch * max([len(b.fence), *(r + 1 for r in runs)])
    body = "".join(ln if ln == "\n" else b.indent + ln for ln in _lines(content))
    return f"{b.indent}{fence}{b.info}\n{body}{b.indent}{fence}\n"


def quote_content(cfg, arg):
    m = QUOTE_RE.match(arg)
    if not m:
        raise BlockError("pidoc-quote 는 경로#La-Lb 꼴이어야 함")
    rel, a, b = m.group(1), int(m.group(2)), int(m.group(3))
    if not rel:
        raise BlockError("인용할 경로가 비어 있음")
    root = cfg.root.resolve()
    path = (root / rel).resolve()
    # 절대 경로·../·밖을 가리키는 심볼릭 링크 모두 resolve 뒤에 걸러진다
    if not path.is_relative_to(root):
        raise BlockError(f"프로젝트 밖 경로는 인용할 수 없음: {rel}")
    if not path.is_file():
        raise BlockError(f"인용할 파일이 없음: {rel}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise BlockError(f"인용할 파일을 읽지 못함: {rel}: {e}")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not 1 <= a <= b <= len(lines):
        raise BlockError(f"줄 범위가 올바르지 않음: L{a}-L{b} (파일은 {len(lines)}줄)")
    return "\n".join(lines[a - 1:b]) + "\n"


def _command(cfg, arg):
    tname, sep, cid = arg.rpartition(":")
    cmd = next((c for c in cfg.commands if c.id == cid), None)
    if cmd is None:
        raise BlockError(f"설정에 없는 명령: {cid}")
    if sep:
        if tname not in cmd.targets:
            raise BlockError(f"{cid} 는 대상 {tname} 에서 돌지 않음")
    elif len(cmd.targets) > 1:
        raise BlockError(f"여러 대상에서 도는 명령 — 대상을 적을 것: "
                         + ", ".join(f"{t}:{cid}" for t in cmd.targets))
    else:
        tname = cmd.targets[0]
    return tname, cmd


def run_content(cfg, arg):
    """최신 run 의 stdout(이미 가린 것)."""
    tname, cmd = _command(cfg, arg)
    run_dir = find_run(cfg)
    if run_dir is None:
        raise BlockError("증거 run 이 없음 — pidoc collect 를 먼저 할 것")
    where = f"{run_dir.name}/{tname}/{cmd.id}"
    rec_path = run_dir / tname / f"{cmd.id}.json"
    out_path = run_dir / tname / f"{cmd.id}.stdout"
    if not rec_path.is_file() or not out_path.is_file():
        raise BlockError(f"최신 run 에 증거가 없음: {where}")
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise BlockError(f"증거 기록을 읽지 못함: {where}.json")
    if not isinstance(rec, dict) or not rec.get("ok"):
        raise BlockError(f"최신 run 에서 명령이 실패함: {where}")
    if rec.get("stdout_truncated"):
        raise BlockError(f"최신 run 의 출력이 잘림: {where}")
    raw = out_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != rec.get("stdout_sha256"):
        raise BlockError(f"증거 stdout 의 sha256 이 기록과 다름: {where}")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise BlockError(f"증거 stdout 이 UTF-8 이 아님: {where}")


def content(cfg, b):
    if not b.closed:
        raise BlockError("닫히지 않은 pidoc 블록")
    return as_body(quote_content(cfg, b.arg) if b.kind == "quote" else run_content(cfg, b.arg))


def masker(cfg, arg):
    """pidoc-run 비교 전에 가릴 함수."""
    _, cmd = _command(cfg, arg)
    rxs = []
    if "time" in cmd.mask:
        rxs += TIME_RES
    if "host" in cmd.mask:
        names = set(Redactor.from_config(cfg).names) | {t.alias.lower() for t in cfg.targets.values()}
        if names:
            alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
            rxs.append(re.compile(rf"(?<![\w.-])(?:{alt})(?![\w-])", re.IGNORECASE))
        rxs.append(LOCAL_HOST_RE)
    rxs += [re.compile(r) for r in cmd.mask_regex]

    def mask(s):
        for rx in rxs:
            s = rx.sub(MASK, s)
        return s

    return mask


def first_diff(a, b):
    """처음 다른 줄 (줄 번호, 문서 쪽, 기대 쪽)."""
    la, lb = a.split("\n"), b.split("\n")
    for n, (x, y) in enumerate(zip(la, lb), 1):
        if x != y:
            return n, x, y
    n = min(len(la), len(lb)) + 1
    return n, la[n - 1] if n <= len(la) else "(없음)", lb[n - 1] if n <= len(lb) else "(없음)"
