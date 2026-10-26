"""secrets: 공개하면 안 되는 값 찾기(휴리스틱 — 모든 비밀을 찾지는 못한다).

찾는 것: IPv4·IPv6 주소, MAC 주소, 이메일, 실제 hostname, 금지어(docs/banned.txt),
개인키(PEM), Bearer 토큰, 흔한 API 토큰 모양(ghp_·github_pat_·xox?-·sk-·AKIA), URL 안 사용자:비밀번호, 홈 폴더 경로.
원본(docs/src)뿐 아니라 렌더 결과(docs/out), 사실(docs/facts), 증거(docs/evidence/runs), AI 기록(docs/ai)도 본다.
펜스 코드 안도 본다. 문서용 주소(192.0.2.x 등, 2001:db8::/32)·루프백, example.com 계열은 넘긴다.
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
TEXT_SUFFIXES = (".md", ".html", ".json", ".stdout", ".stderr", ".txt", ".sha256")
IPV6_RE = re.compile(r"(?<![\w:.])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])")
SAFE_V6 = [ipaddress.ip_network(n) for n in ("2001:db8::/32", "::1/128", "::/128")]
MAC_RE = re.compile(r"(?<![\w:])(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}(?![\w:])")
SAFE_MAC_RE = re.compile(r"^(00:00:00:00:00:00|ff:ff:ff:ff:ff:ff|00:00:5e:00:53:[0-9a-f]{2})$", re.IGNORECASE)
PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "개인키"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer 토큰"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,}|xox[abposr]-[\w-]{10,}|sk-[A-Za-z0-9_-]{20,}"
                r"|AKIA[0-9A-Z]{16})"), "API 토큰 모양"),
    (re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^/\s:@]+:[^/\s@]+@"), "URL 안 사용자:비밀번호"),
]
HOME_RE = re.compile(r"(?:/home|/Users)/([A-Za-z0-9_.-]+)")


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
        for folder in (cfg.out_dir, cfg.facts_dir, cfg.runs_dir, cfg.ai_dir):
            if folder.is_dir():
                files += sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix in TEXT_SUFFIXES)
    else:
        files += [o for o in (docmod.out_path(cfg, d.path) for d in ctx.docs) if o.is_file()]
    return files


def _ipv6_ok(text):
    try:
        ip = ipaddress.IPv6Address(text)
    except ValueError:
        return True                      # 시각(23:15:02)·C++ 이름 같은 것
    return any(ip in net for net in SAFE_V6)


class Scanner:
    """설정에 맞춘 비밀 찾기. scan(글) → [(줄 번호, 메시지)]"""

    def __init__(self, cfg):
        settings = cfg.check
        self.ip_allow = settings.get("ip_allow", [])
        self.email_allow = settings.get("email_allow", [])
        self.home_allow = set(settings.get("home_allow", ["pi"]))
        names = set()
        for target in cfg.targets.values():
            names.update(redact.real_names(cfg, target))
        self.hosts = [(n, redact.name_pattern(n)) for n in sorted(names)]
        self.banned = load_banned(cfg.docs_dir / settings.get("banned", "banned.txt"))

    def scan(self, text):
        found = []
        for n, line in enumerate(text.splitlines(), 1):
            for m in IP_RE.finditer(line):
                if not _ip_ok(m.group(0), self.ip_allow):
                    found.append((n, f"IP 주소 {hide(m.group(0))} — 문서용 주소(192.0.2.x)나 <ip> 로"))
            for m in IPV6_RE.finditer(line):
                if not _ipv6_ok(m.group(0)):
                    found.append((n, f"IPv6 주소 {hide(m.group(0))} — 문서용 주소(2001:db8::)로"))
            for m in MAC_RE.finditer(line):
                if not SAFE_MAC_RE.match(m.group(0)):
                    found.append((n, f"MAC 주소 {hide(m.group(0))}"))
            for m in EMAIL_RE.finditer(line):
                if not _email_ok(m.group(1), self.email_allow):
                    found.append((n, f"이메일 {hide(m.group(0))} — example.com 주소로"))
            for pattern, what in PATTERNS:
                m = pattern.search(line)
                if m:
                    found.append((n, f"{what} {hide(m.group(0))}"))
            for m in HOME_RE.finditer(line):
                if m.group(1) not in self.home_allow:
                    found.append((n, f"홈 폴더 경로 {hide(m.group(0))} — ~/ 나 /home/pi 처럼 일반적인 경로로"))
            for host, pattern in self.hosts:
                if pattern.search(line):
                    found.append((n, f"실제 hostname {hide(host)} — 대상 alias 로"))
            lower = line.lower()
            for word in self.banned:
                if word.lower() in lower:
                    found.append((n, f"금지어 {hide(word)} (banned.txt)"))
        return found


def run(ctx):
    scanner = Scanner(ctx.cfg)
    findings = []
    for path in files_to_scan(ctx):
        text = path.read_text(encoding="utf-8", errors="replace")
        for n, msg in scanner.scan(text):
            findings.append(Finding(ctx.cfg.rel(path), n, "secrets", msg))
    return findings
