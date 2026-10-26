"""render: docs/src → docs/out. 사실 자리표시자와 인용 블록을 채운다.

- {{fact:키}} · {{fact:대상:키|변환}} — 없는 사실, 타입이 안 맞는 변환, 만료된 사실은 오류
- ```python pidoc-quote=경로#L10-L24   — 파일에서 그 줄들을 채움
- ```console pidoc-run=명령id target=대상 — 최신 성공 run 의 stdout 으로 채움
- docs/out/.deps.json 에 문서마다 의존 파일 sha256·쓴 사실·쓴 run 을 남긴다(stale 용)
"""

import re
from pathlib import Path

from . import doc as docmod
from . import evidence, facts
from .util import CHECK_FAILED, OK, iso, now, read_json, sha256_file, write_json

TRANSFORMS = ("int", "round1", "join", "code")


class RenderError(ValueError):
    pass


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RenderError(f"|{name} 은 숫자 사실에만 쓸 수 있습니다(지금 {facts.type_of(value)})")
    return value


def apply_transforms(value, transforms):
    """정해진 변환만. 결과는 글자."""
    code = False
    for t in transforms:
        if t == "int":
            value = int(round(_number(value, t)))
        elif t == "round1":
            value = f"{_number(value, t):.1f}"
        elif t == "join":
            if not isinstance(value, list):
                raise RenderError(f"|join 은 목록 사실에만 쓸 수 있습니다(지금 {facts.type_of(value)})")
            value = ", ".join(str(v) for v in value)
        elif t == "code":
            code = True
        else:
            raise RenderError(f"모르는 변환 |{t} (쓸 수 있는 것: {', '.join(TRANSFORMS)})")
    text = facts.show_value(value)
    return f"`{text}`" if code else text


def resolve(ref, all_facts, at=None):
    """참조 하나를 글자로. 문제가 있으면 RenderError."""
    if ref.target not in all_facts:
        raise RenderError(f"사실 파일이 없는 대상: {ref.target} ({ref.text})")
    fact = all_facts[ref.target].get(ref.key)
    if fact is None:
        raise RenderError(f"없는 사실: {ref.full_key} ({ref.text}) — pidoc facts 로 키를 확인하세요")
    if facts.is_expired(fact, at):
        raise RenderError(f"만료된 사실: {ref.full_key} (수집 {fact['collected_at']}, 유효 {fact['max_age_days']}일)"
                          " — pidoc collect 로 다시 모으세요")
    return apply_transforms(fact["value"], ref.transforms)


QUOTE_RE = re.compile(r"^(?P<path>[^#]+)(?:#L(?P<a>\d+)(?:-L(?P<b>\d+))?)?$")


def quote_lines(cfg, spec):
    """'경로#L10-L24' → 파일의 그 줄들(끝 공백은 그대로). (줄 목록, 파일 경로)"""
    m = QUOTE_RE.match(spec)
    if not m:
        raise RenderError(f"pidoc-quote 형식: 경로 또는 경로#L10-L24 ({spec})")
    path = cfg.root / m.group("path")
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
    """pidoc-run 블록에 넣을 최신 증거. (글자, run)"""
    cmd_id = fence.opts["pidoc-run"]
    target = fence.opts.get("target", default_target)
    run = evidence.latest_with(cfg.runs_dir, target, cmd_id)
    if run is None:
        raise RenderError(f"증거가 없습니다: {cmd_id} (대상 {target}) — pidoc collect --target {target} --only {cmd_id}")
    text = run.stdout(cmd_id).decode("utf-8", errors="replace")
    return text.rstrip("\n").splitlines(), run


def render_doc(cfg, d, all_facts, at=None):
    """문서 하나를 렌더한다. (결과 글, 오류 [(줄, 메시지)], 의존 정보)"""
    errors = []
    used, runs, deps = set(), set(), {}
    for dep in d.deps + cfg.check.get("stale_deps", {}).get(cfg.rel(d.path), []):
        path = cfg.root / dep
        if path.is_file():
            deps[dep] = sha256_file(path)
        else:
            errors.append((1, f"pidoc-deps 의 파일이 없습니다: {dep}"))

    def fill(line, n):
        def one(m):
            ref = docmod.Ref(m, n, d.target)
            try:
                text = resolve(ref, all_facts, at)
            except RenderError as e:
                errors.append((n, str(e)))
                return m.group(0)
            used.add(ref.full_key)
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
                    runs.add(run.name)
            except RenderError as e:
                errors.append((n, str(e)))
                body = fence.body
            out.append(f"{fence.indent}{fence.mark}{fence.lang}")
            out += body
            out.append(f"{fence.indent}{fence.mark}")
            i = fence.end if fence.end else len(d.lines)
            continue
        out.append(fill(d.lines[i], n))
        i += 1
    info = {"deps": deps, "facts": sorted(used), "runs": sorted(runs)}
    return "\n".join(out) + "\n", errors, info


def load_deps(cfg):
    path = cfg.out_dir / ".deps.json"
    return read_json(path) if path.is_file() else {}


def render(cfg, files):
    all_facts = facts.load_all(cfg.facts_dir)
    at = now()
    deps = load_deps(cfg)
    failed = 0
    for src in files:
        d = docmod.load(src, cfg.default_target)
        text, errors, info = render_doc(cfg, d, all_facts, at)
        name = cfg.rel(src)
        if errors:
            failed += 1
            for n, msg in errors:
                print(f"{name}:{n}: [render] {msg}")
            continue
        out = docmod.out_path(cfg, src)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        deps[name] = dict(info, out=cfg.rel(out), rendered_at=iso(at), src_sha256=sha256_file(src))
        print(f"{cfg.rel(out)} ← {name}")
    if deps:
        write_json(cfg.out_dir / ".deps.json", deps)
    if failed:
        print(f"렌더 실패 {failed}개 문서(결과를 쓰지 않음)")
        return CHECK_FAILED
    return OK
