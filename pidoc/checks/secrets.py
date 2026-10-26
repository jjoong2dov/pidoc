"""secrets: 공개하면 안 되는 값 — IP 주소, 이메일, 실제 hostname, 금지어(docs/banned.txt).

원본(docs/src)뿐 아니라 렌더 결과(docs/out), 사실(docs/facts), 증거(docs/evidence/runs)도 본다.
저장소에 함께 공개되는 것들이기 때문이다. 펜스 코드 안도 본다.
문서용 주소(192.0.2.x, 198.51.100.x, 203.0.113.x)·루프백·0.0.0.0 과 example.com 계열은 넘긴다.
메시지에는 찾은 값을 앞 두 글자만 보여 준다(CI 기록에 다시 새지 않게).
"""

import ipaddress
import re

from . import Finding
from .. import doc as docmod
from .. import redact

IP_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.]|\.\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
SAFE_NETS = [ipaddress.ip_network(n) for n in
             ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "127.0.0.0/8", "0.0.0.0/32")]
SAFE_DOMAINS = ("example.com", "example.org", "example.net", "users.noreply.github.com")
TEXT_SUFFIXES = (".md", ".html", ".json", ".stdout", ".stderr", ".txt")


def hide(value):
    return value[:2] + "…"


def _ip_ok(text, allow):
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return True                      # 255 넘는 마디: IP 가 아님(버전 번호 등)
    nets = SAFE_NETS + [ipaddress.ip_network(a, strict=False) for a in allow]
    return any(ip in net for net in nets)


def _email_ok(domain, allow):
    domain = domain.lower()
    return any(domain == d or domain.endswith("." + d) for d in (*SAFE_DOMAINS, *allow)) or domain.endswith(".example")


def load_banned(path):
    if not path.is_file():
        return []
    words = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.append(line)
    return words


def files_to_scan(ctx):
    cfg = ctx.cfg
    files = [d.path for d in ctx.docs]
    if ctx.all_files:
        for folder in (cfg.out_dir, cfg.facts_dir, cfg.runs_dir):
            if folder.is_dir():
                files += sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix in TEXT_SUFFIXES)
    else:
        files += [o for o in (docmod.out_path(cfg, d.path) for d in ctx.docs) if o.is_file()]
    return files


def run(ctx):
    cfg = ctx.cfg
    settings = cfg.check
    ip_allow = settings.get("ip_allow", [])
    email_allow = settings.get("email_allow", [])
    names = set()
    for target in cfg.targets.values():
        names.update(redact.real_names(cfg, target))
    hosts = [(n, redact.name_pattern(n)) for n in sorted(names)]
    banned = load_banned(cfg.docs_dir / settings.get("banned", "banned.txt"))
    findings = []
    for path in files_to_scan(ctx):
        name = cfg.rel(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        for n, line in enumerate(text.splitlines(), 1):
            for m in IP_RE.finditer(line):
                if not _ip_ok(m.group(0), ip_allow):
                    findings.append(Finding(name, n, "secrets", f"IP 주소 {hide(m.group(0))} — 문서용 주소(192.0.2.x)나 <ip> 로"))
            for m in EMAIL_RE.finditer(line):
                if not _email_ok(m.group(1), email_allow):
                    findings.append(Finding(name, n, "secrets", f"이메일 {hide(m.group(0))} — example.com 주소로"))
            for host, pattern in hosts:
                if pattern.search(line):
                    findings.append(Finding(name, n, "secrets", f"실제 hostname {hide(host)} — 대상 alias 로"))
            lower = line.lower()
            for word in banned:
                if word.lower() in lower:
                    findings.append(Finding(name, n, "secrets", f"금지어 {hide(word)} (banned.txt)"))
    return findings
