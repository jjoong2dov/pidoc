"""draft: 틀 + 사실 목록으로 AI 초안을 만든다.

AI 에게는 숫자를 직접 쓰지 말고 {{fact:키}} 자리표시자를 쓰라고 한다.
그래도 숫자가 들어오면 초안은 저장하되 그 줄을 보여 주고 종료 1(사람이 고칠 차례).
"""

import re
from pathlib import Path

from . import ai, facts
from .util import CHECK_FAILED, OK, PidocError

RULES = """\
너는 기술문서 초안을 쓰는 도우미다. 아래 규칙을 꼭 지켜라.

1. 숫자(버전·개수·시간·크기·포트·주소 등)를 본문에 직접 쓰지 마라.
   숫자가 필요한 자리에는 아래 '사실 목록'의 키로 {{fact:대상:키}} 를 쓴다. 예: {{fact:pc:system.python_version}}
2. 사실 목록에 없는 값이 필요하면 지어내지 말고 그 자리에 <!-- TODO: 필요한 사실 --> 를 남겨라.
3. 명령 출력은 지어내지 마라. 출력을 보여 줄 자리에는 본문이 빈 블록을 둔다:
   ```console pidoc-run=명령id target=대상
   ```
4. '틀'의 제목 구조와 순서를 지키고, Markdown 문서 본문만 출력하라(설명·인사말 없이).
"""

MAX_VALUE = 120


def fact_lines(all_facts):
    lines = []
    for target in sorted(all_facts):
        for key in sorted(all_facts[target]):
            f = all_facts[target][key]
            value = facts.show_value(f["value"]).replace("\n", " ⏎ ")
            if len(value) > MAX_VALUE:
                value = value[:MAX_VALUE] + "…"
            lines.append(f"- {{{{fact:{target}:{key}}}}} ({f['type']}) = {value}")
    return lines


def command_lines(cfg):
    return [f"- pidoc-run={c['id']} target={t}: {' '.join(c['argv'])}"
            for c in cfg.commands for t in c["targets"]]


def build_prompt(cfg, template_text):
    parts = [RULES, "## 사실 목록"]
    parts += fact_lines(facts.load_all(cfg.facts_dir)) or ["(없음)"]
    parts += ["", "## 수집한 명령(pidoc-run 에 쓸 수 있는 것)"]
    parts += command_lines(cfg) or ["(없음)"]
    parts += ["", "## 틀", template_text]
    return "\n".join(parts) + "\n"


def number_lines(text):
    """펜스 코드·자리표시자·HTML 주석 밖에서 숫자가 있는 줄. (줄 번호, 줄)"""
    found, fence = [], None
    for n, line in enumerate(text.splitlines(), 1):
        m = re.match(r"^\s*(`{3,}|~{3,})", line)
        if m:
            mark = m.group(1)
            if fence is None:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        body = re.sub(r"\{\{fact:[^}]*\}\}|<!--.*?-->|`[^`]*`", "", line)
        if re.search(r"\d", body):
            found.append((n, line))
    return found


def draft(cfg, template, out, provider=None):
    template = Path(template)
    if not template.is_file():
        raise PidocError(f"틀 파일이 없습니다: {template}")
    prompt = build_prompt(cfg, template.read_text(encoding="utf-8"))
    text, record = ai.call(cfg, provider, prompt, "draft")
    if text is None:
        print(f"AI 를 부르지 않고 프롬프트만 저장했습니다: {cfg.rel(record / 'prompt.txt')}")
        return OK
    text = ai.strip_fence(text)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"초안: {cfg.rel(out)} (호출 기록 {cfg.rel(record)})")
    bad = number_lines(text)
    if bad:
        print(f"숫자가 직접 들어간 줄 {len(bad)}개 — 사실 키로 바꾸거나 근거를 확인하세요:")
        for n, line in bad:
            print(f"  {cfg.rel(out)}:{n}: {line.strip()}")
        return CHECK_FAILED
    return OK
