"""pidoc check --only secrets: src·out·facts·evidence 에 내부 정보가 남았는지 본다.

찾은 값은 화면에 앞 두 글자만 보인다(검사 출력이 다시 새지 않게).
"""

import ipaddress
import re
import sys

from pidoc.redact import IPV4_RE, Redactor, _keep_ip

AREAS = ("src", "out", "facts", "evidence")
# 문서용 예시 대역(RFC 5737)은 괜찮다
DOC_NETS = [ipaddress.IPv4Network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)", re.ASCII)
# 예시용 예약 도메인(RFC 2606)
OK_MAIL_RE = re.compile(r"(?:^|\.)(?:example(?:\.(?:com|net|org))?|test|invalid|localhost)$",
                        re.IGNORECASE)
# 다른 사람·다른 기계의 홈도 잡는다: /home/이름, /Users/이름, C:\Users\이름
HOME_RE = re.compile(r"(?<![\w./~-])(?:/home|/Users)/[\w.-]+|\b[A-Za-z]:\\Users\\[\w.-]+")
KEY_RE = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")


def _ip_ok(s):
    if _keep_ip(s):
        return True
    ip = ipaddress.IPv4Address(s)
    return any(ip in n for n in DOC_NETS)


def show(value):
    return f"'{value[:2]}…'"


class Scanner:
    def __init__(self, cfg, banned=()):
        red = Redactor.from_config(cfg)
        self.home_re = red.home_re
        # 별칭과 같은 이름은 가린 결과이므로 뺀다
        aliases = {t.alias.lower() for t in cfg.targets.values()}
        names = [n for n in red.names if n not in aliases]
        self.host_re = None
        if names:
            alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
            self.host_re = re.compile(rf"(?<![\w.-])(?:{alt})(?![\w-])", re.IGNORECASE)
        self.banned = [w for w in banned if w]

    def line(self, s):
        """[(종류, 값)]."""
        found = []
        for m in IPV4_RE.finditer(s):
            if not _ip_ok(m.group(0)):
                found.append(("IPv4", m.group(0)))
        for m in EMAIL_RE.finditer(s):
            if not OK_MAIL_RE.search(m.group(1)):
                found.append(("이메일", m.group(0)))
        if self.host_re:
            # 이메일 도메인 안의 이름도 호스트 이름으로 센다
            found += [("호스트 이름", m.group(0)) for m in self.host_re.finditer(s)]
        homes = list(HOME_RE.finditer(s))
        if self.home_re:
            homes += self.home_re.finditer(s)
        seen = set()
        for m in sorted(homes, key=lambda m: m.start()):
            if m.start() not in seen:
                seen.add(m.start())
                found.append(("홈 경로", m.group(0)))
        found += [("개인키", m.group(0)) for m in KEY_RE.finditer(s)]
        low = s.lower()
        for w in self.banned:
            i = low.find(w.lower())
            while i >= 0:
                found.append(("금지어", s[i:i + len(w)]))
                i = low.find(w.lower(), i + len(w))
        return found


def read_banned(cfg):
    """docs/banned.txt: 한 줄에 하나, # 은 주석. 없으면 빈 목록."""
    path = cfg.docs / "banned.txt"
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    return [s.strip() for s in text.splitlines() if s.strip() and not s.strip().startswith("#")]


def _files(cfg):
    for area in AREAS:
        d = cfg.docs / area
        if d.is_dir():
            yield from sorted(p for p in d.rglob("*") if p.is_file())


def check_secrets(cfg):
    try:
        banned = read_banned(cfg)
    except (OSError, UnicodeDecodeError) as e:
        print(f"banned.txt 를 읽지 못함: {e}", file=sys.stderr)
        return 1
    scan = Scanner(cfg, banned)
    bad = 0
    for path in _files(cfg):
        rel = path.relative_to(cfg.docs).as_posix()
        try:
            text = path.read_bytes().decode("utf-8", "replace")
        except OSError as e:
            print(f"{rel}: 읽지 못함: {e}", file=sys.stderr)
            bad += 1
            continue
        for n, s in enumerate(text.split("\n"), 1):
            for kind, value in scan.line(s):
                print(f"{rel}:{n}: {kind} {show(value)}", file=sys.stderr)
                bad += 1
    return bad
