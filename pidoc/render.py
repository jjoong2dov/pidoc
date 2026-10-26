"""render: docs/src → docs/out. 사실 자리표시자와 인용 블록을 채운다.

- {{fact:키}} · {{fact:대상:키|변환}} — 없는 사실, 타입이 안 맞는 변환, 만료된 사실,
  증거와 맞지 않는 사실(verify.py)은 오류
- 본문에 넣는 사실은 Markdown 특수 문자를 이스케이프한다(값이 링크·HTML·표 구조가 되지 않게).
  펜스 코드 안에서는 그대로 넣되 펜스를 닫을 수 있는 값은 거절한다. |raw 는 이스케이프하지 않는다.
- ```python pidoc-quote=경로#L10-L24   — 저장소 안 파일에서 그 줄들을 채움
- ```console pidoc-run=명령id target=대상 — 그 명령의 최신 수집 stdout 으로 채움(최신 수집이 실패면 오류)
  채운 블록의 펜스는 본문의 가장 긴 백틱보다 길게 만든다.
- docs/out/.deps.json 에 문서마다 의존 파일·쓴 사실·쓴 run 의 sha256 을 남긴다(stale 용)
- 렌더에 실패한 문서는 이전 결과와 의존 기록을 지운다(낡은 결과가 출판되지 않게)
"""

import json
import re

from . import doc as docmod
from . import evidence, facts
from .util import CHECK_FAILED, OK, iso, now, read_json, sha256_bytes, sha256_file, write_json
from .verify import Verifier

TRANSFORMS = ("int", "round1", "join", "code", "raw")
MD_SPECIAL_RE = re.compile(r"([\\`*_\[\]<>|!])")


class RenderError(ValueError):
    pass


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RenderError(f"|{name} 은 숫자 사실에만 쓸 수 있습니다(지금 {facts.type_of(value)})")
    return value


def code_span(text):
    """값 안의 백틱보다 긴 구분자로 감싼다."""
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    mark = "`" * (longest + 1)
    pad = " " if text.startswith(("`", " ")) or text.endswith(("`", " ")) else ""
    return f"{mark}{pad}{text}{pad}{mark}"


def apply_transforms(value, transforms, context="prose"):
    """정해진 변환만. 결과는 글자. context: prose(본문) | code(펜스 안)"""
    code = raw = False
    for t in transforms:
        if t == "int":
            value = int(round(_number(value, t)))
        elif t == "round1":
            value = f"{_number(value, t):.1f}"
        elif t == "join":
            if not isinstance(value, list):
                raise RenderError(f"|join 은 목록 사실에만 쓸 수 있습니다(지금 {facts.type_of(value)})")
            value = ", ".join(str(v) for v in value) if value else "(없음)"
        elif t == "code":
            code = True
        elif t == "raw":
            raw = True
        else:
            raise RenderError(f"모르는 변환 |{t} (쓸 수 있는 것: {', '.join(TRANSFORMS)})")
    text = facts.show_value(value)
    if context == "code":
        if "```" in text or "~~~" in text:
            raise RenderError("펜스를 닫을 수 있는 값(``` 나 ~~~)은 코드 블록에 넣을 수 없습니다")
        return text
    if "\n" in text and not raw:
        raise RenderError("여러 줄 사실은 본문에 넣을 수 없습니다 — 펜스 코드 블록 안에 쓰세요")
    if code:
        return code_span(text)
    return text if raw else MD_SPECIAL_RE.sub(r"\\\1", text)


def resolve(ref, all_facts, at=None, verifier=None, context="prose"):
    """참조 하나를 글자로. 문제가 있으면 RenderError."""
    if ref.target not in all_facts:
        raise RenderError(f"사실 파일이 없는 대상: {ref.target} ({ref.text})")
    fact = all_facts[ref.target].get(ref.key)
    if fact is None:
        raise RenderError(f"없는 사실: {ref.full_key} ({ref.text}) — pidoc facts 로 키를 확인하세요")
    if facts.is_expired(fact, at):
        raise RenderError(f"만료된 사실: {ref.full_key} (수집 {fact['collected_at']}, 유효 {fact['max_age_days']}일)"
                          " — pidoc collect 로 다시 모으세요")
    if verifier is not None:
        problem = verifier.problem(ref.target, ref.key, fact)
        if problem:
            raise RenderError(f"{ref.full_key}: {problem}")
    return apply_transforms(fact["value"], ref.transforms, context)


QUOTE_RE = re.compile(r"^(?P<path>[^#]+)(?:#L(?P<a>\d+)(?:-L(?P<b>\d+))?)?$")


def inside(cfg, rel, what):
    from .util import PidocError
    try:
        return cfg.inside(rel, what)
    except PidocError as e:
        raise RenderError(str(e))


def quote_lines(cfg, spec):
    """'경로#L10-L24' → 저장소 안 파일의 그 줄들. (줄 목록, 파일 경로)"""
    m = QUOTE_RE.match(spec)
    if not m:
        raise RenderError(f"pidoc-quote 형식: 경로 또는 경로#L10-L24 ({spec})")
    path = inside(cfg, m.group("path"), "pidoc-quote")
    if not path.is_file():
        raise RenderError(f"인용할 파일이 없습니다: {m.group('path')}")
    lines = path.read_text(encoding="utf-8").splitlines()
    if m.group("a"):
        a = int(m.group("a"))
        b = int(m.group("b") or a)
        if not 1 <= a <= b <= len(lines):
            raise RenderError(f"줄 범위가 파일 밖입니다: {spec} (파일은 {len(lines)}줄)")
        lines = lines[a - 1:b]
    return lines, path


def run_output(cfg, fence, default_target):
    """pidoc-run 블록에 넣을 최신 증거. (줄 목록, run)"""
    cmd_id = fence.opts["pidoc-run"]
    target = fence.opts.get("target", default_target)
    run = evidence.latest_attempt(cfg.runs_dir, target, cmd_id)
    if run is None:
        raise RenderError(f"증거가 없습니다: {cmd_id} (대상 {target}) — pidoc collect --target {target} --only {cmd_id}")
    if not evidence.run_ok(run, cmd_id):
        raise RenderError(f"{cmd_id}: 더 최근 수집({run.name})이 실패했습니다 — 옛 출력을 쓰지 않습니다")
    try:
        text = run.stdout(cmd_id).decode("utf-8")
    except UnicodeDecodeError:
        raise RenderError(f"{cmd_id}: 출력이 UTF-8 이 아닙니다")
    return text.rstrip("\n").splitlines(), run


def fence_mark(body):
    """본문의 가장 긴 백틱 줄보다 긴 펜스(최소 ```)."""
    longest = max((len(m) for line in body for m in re.findall(r"`+", line)), default=0)
    return "`" * max(3, longest + 1)


def fact_hash(fact):
    """stale 용: 값·타입·출처가 같으면 같은 해시."""
    keep = {k: fact.get(k) for k in ("value", "type", "run", "source_sha256")}
    return sha256_bytes(json.dumps(keep, sort_keys=True, ensure_ascii=False).encode())


def render_doc(cfg, d, all_facts, at=None, verifier=None):
    """문서 하나를 렌더한다. (결과 글, 오류 [(줄, 메시지)], 의존 정보)"""
    errors = []
    used, runs, deps = {}, {}, {}
    for dep in d.deps + cfg.check.get("stale_deps", {}).get(cfg.rel(d.path), []):
        try:
            path = inside(cfg, dep, "pidoc-deps")
        except RenderError as e:
            errors.append((1, str(e)))
            continue
        if path.is_file():
            deps[dep] = sha256_file(path)
        else:
            errors.append((1, f"pidoc-deps 의 파일이 없습니다: {dep}"))

    def fill(line, n, context):
        def one(m):
            ref = docmod.Ref(m, n, d.target)
            try:
                text = resolve(ref, all_facts, at, verifier, context)
            except RenderError as e:
                errors.append((n, str(e)))
                return m.group(0)
            used[ref.full_key] = fact_hash(all_facts[ref.target][ref.key])
            return text
        return docmod.FACT_RE.sub(one, line)

    fences = {f.start: f for f in d.fences}
    out, i = [], d.header_lines
    while i < len(d.lines):
        n = i + 1
        fence = fences.get(n)
        if fence and fence.directive:
            try:
                if fence.directive == "pidoc-quote":
                    body, path = quote_lines(cfg, fence.opts["pidoc-quote"])
                    deps[cfg.rel(path)] = sha256_file(path)
                else:
                    body, run = run_output(cfg, fence, d.target)
                    target = fence.opts.get("target", d.target)
                    cmd_id = fence.opts["pidoc-run"]
                    runs[f"{target}:{cmd_id}"] = {"run": run.name,
                                                   "stdout_sha256": run.record(cmd_id)["stdout"]["sha256"]}
            except RenderError as e:
                errors.append((n, str(e)))
                body = fence.body
            mark = fence_mark(body)
            out.append(f"{fence.indent}{mark}{fence.lang}")
            out += body
            out.append(f"{fence.indent}{mark}")
            i = fence.end if fence.end else len(d.lines)
            continue
        out.append(fill(d.lines[i], n, "code" if d.in_fence[i] else "prose"))
        i += 1
    info = {"deps": deps, "facts": used, "runs": runs}
    return "\n".join(out) + "\n", errors, info


def load_deps(cfg):
    path = cfg.out_dir / ".deps.json"
    return read_json(path) if path.is_file() else {}


def render(cfg, files):
    all_facts = facts.load_all(cfg.facts_dir)
    verifier = Verifier(cfg)
    at = now()
    deps = load_deps(cfg)
    failed = 0
    for src in files:
        d = docmod.load(src, cfg.default_target)
        text, errors, info = render_doc(cfg, d, all_facts, at, verifier)
        name = cfg.rel(src)
        out = docmod.out_path(cfg, src)
        if errors:
            failed += 1
            for n, msg in errors:
                print(f"{name}:{n}: [render] {msg}")
            deps.pop(name, None)
            if out.exists():
                out.unlink()
                print(f"{name}: 이전 결과 {cfg.rel(out)} 를 지웠습니다(낡은 결과가 출판되지 않게)")
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        deps[name] = dict(info, out=cfg.rel(out), rendered_at=iso(at), src_sha256=sha256_file(src))
        print(f"{cfg.rel(out)} ← {name}")
    if deps or (cfg.out_dir / ".deps.json").exists():
        write_json(cfg.out_dir / ".deps.json", deps)
    if failed:
        print(f"렌더 실패 {failed}개 문서")
        return CHECK_FAILED
    return OK
