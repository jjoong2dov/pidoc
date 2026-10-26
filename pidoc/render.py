"""pidoc render: docs/src/*.md 의 {{fact:...}} 를 증거와 맞는 사실로 채워 docs/out/ 에 쓴다."""

import re
import sys
from decimal import ROUND_HALF_UP, Decimal

from pidoc.redact import Redactor
from pidoc.verify import FactsError, load_all, verify

PLACEHOLDER_RE = re.compile(r"\{\{fact:(.*?)\}\}")
TRANSFORMS = ("int", "round1", "join", "code")


class RenderError(Exception):
    pass


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _plain(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (str, int, float)):
        return str(v)
    raise RenderError("목록은 |join 으로 써야 함")


def _round(v, q):
    if not _is_num(v):
        raise RenderError(f"숫자가 아닌 값에 반올림을 쓸 수 없음: {v!r}")
    return str(Decimal(str(v)).quantize(Decimal(q), rounding=ROUND_HALF_UP))


def apply(value, tf):
    if tf is None:
        return _plain(value)
    if tf == "int":
        return _round(value, "1")
    if tf == "round1":
        return _round(value, "0.1")
    if tf == "join":
        if not isinstance(value, list):
            raise RenderError(f"목록이 아닌 값에 join 을 쓸 수 없음: {value!r}")
        return ", ".join(_plain(x) for x in value)
    if tf == "code":
        s = _plain(value)
        return f"`` {s} ``" if "`" in s else f"`{s}`"
    raise RenderError(f"모르는 변환: {tf} (int, round1, join, code 만)")


class Resolver:
    """자리표시자를 값으로 바꾼다. 쓰는 사실은 증거와 대조한다."""

    def __init__(self, cfg, facts):
        self.cfg = cfg
        self.facts = facts
        self.red = Redactor.from_config(cfg)
        self.checked = {}

    def verified(self, tname, key):
        if (tname, key) not in self.checked:
            rec = self.facts[tname][key]
            self.checked[tname, key] = verify(self.cfg, tname, key, rec, self.red)
        return self.checked[tname, key]

    def lookup(self, ref):
        target, sep, key = ref.partition(":")
        if sep and target in self.facts:
            if key not in self.facts[target]:
                raise RenderError(f"사실이 없음: {target}:{key}")
            return target, key
        key = ref
        if not key:
            raise RenderError("사실 키가 비어 있음")
        hits = [t for t, fs in self.facts.items() if key in fs]
        if not hits:
            raise RenderError(f"사실이 없음: {key}")
        if len(hits) > 1:
            raise RenderError(f"여러 대상에 있는 키 — 대상을 적을 것: {', '.join(hits)}")
        return hits[0], key

    def value(self, inner):
        ref, sep, tf = inner.partition("|")
        tname, key = self.lookup(ref.strip())
        why = self.verified(tname, key)
        if why:
            raise RenderError(f"사실 {tname}:{key} 가 증거와 맞지 않음 — {why}")
        return apply(self.facts[tname][key]["value"], tf.strip() if sep else None)


def render_text(text, res):
    """(결과, [(줄, 자리표시자, 까닭)])."""
    errors = []

    def sub(m):
        try:
            return res.value(m.group(1))
        except RenderError as e:
            errors.append((text.count("\n", 0, m.start()) + 1, m.group(0), str(e)))
            return m.group(0)

    return PLACEHOLDER_RE.sub(sub, text), errors


def src_docs(cfg):
    return sorted(p for p in cfg.src_dir.glob("*.md") if p.is_file())


def read_doc(path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise RenderError(f"읽지 못함: {e}")


def render(cfg):
    if not cfg.src_dir.is_dir():
        print("문서 원본 폴더가 없음: docs/src", file=sys.stderr)
        return 2
    try:
        res = Resolver(cfg, load_all(cfg))
    except FactsError as e:
        print(e, file=sys.stderr)
        return 1
    results = []
    bad = 0
    for path in src_docs(cfg):
        try:
            text = read_doc(path)
        except RenderError as e:
            print(f"src/{path.name}: {e}", file=sys.stderr)
            bad += 1
            continue
        out, errors = render_text(text, res)
        for line, ph, why in errors:
            print(f"src/{path.name}:{line}: {ph} — {why}", file=sys.stderr)
        bad += len(errors)
        results.append((path.name, out))
    if bad:
        print(f"오류 {bad}개 — 결과를 쓰지 않음", file=sys.stderr)
        return 1
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    for name, out in results:
        tmp = cfg.out_dir / (name + ".tmp")
        tmp.write_text(out, encoding="utf-8")
        tmp.replace(cfg.out_dir / name)
        print(f"렌더  src/{name} → out/{name}")
    print(f"문서 {len(results)}개 렌더함")
    return 0
