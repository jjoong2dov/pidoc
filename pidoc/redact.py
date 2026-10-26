"""공개용 가리기: 수집 직후 증거와 사실에서 IP·hostname 같은 값을 바꾼다.

- [redact] patterns: 정규식 → 바꿀 글자 (예: IP → <ip>)
- hostname = true: 실제 hostname 을 대상 alias 로 바꾼다
  (로컬 대상은 이 PC 의 hostname, ssh 대상은 host 에 적은 이름, 그리고 [redact] names)
- home = true: 이 PC 의 홈 폴더 경로를 ~ 로 바꾼다. ssh 오류 메시지처럼 로컬 프로그램이
  찍는 경로에도 사용자 이름이 들어간다(파이 실기에서 known_hosts 경로가 증거에 남았다).
"""

import ipaddress
import json
import re
import socket
from pathlib import Path

SKIP_NAMES = {"localhost", "localhost.localdomain"}


def _is_ip(text):
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return False


def _with_short(name):
    """'pi4.local' → ['pi4.local', 'pi4']. IP 는 그대로."""
    names = [name]
    if not _is_ip(name) and "." in name:
        names.append(name.split(".", 1)[0])
    return names


def names_file(cfg):
    """ssh 대상에서 알아낸 실제 호스트 이름 기록. 공개하지 않는 폴더에 둔다(이름 자체가 가릴 대상이므로)."""
    return cfg.docs_dir / "evidence" / "private" / "hostnames.json"


def remembered(cfg, target):
    try:
        return json.loads(names_file(cfg).read_text(encoding="utf-8")).get(target.name, [])
    except (OSError, ValueError):
        return []


def remember(cfg, target, name):
    """ssh 대상의 실제 호스트 이름을 기록한다. 주소(IP)만 알고 장비 이름은 모르면 가릴 수 없었다
    (파이 실기: pimon once 출력의 host 에 파이의 호스트 이름이 그대로 남았다)."""
    path = names_file(cfg)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    names = sorted(set(data.get(target.name, [])) | {name})
    if data.get(target.name) == names:
        return
    data[target.name] = names
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def real_names(cfg, target):
    """이 대상의 실제 이름들(긴 것부터)."""
    names = list(remembered(cfg, target))
    if target.kind == "local":
        names += _with_short(socket.gethostname())
    elif target.host:
        host = target.host.rsplit("@", 1)[-1]
        names += _with_short(host)
    names += cfg.redact.get("names", [])
    names = {n for n in names if n and len(n) >= 2 and n.lower() not in SKIP_NAMES and n != target.alias}
    return sorted(names, key=lambda n: (-len(n), n))


def name_pattern(name):
    """이름이 다른 낱말의 일부일 때는 바꾸지 않는다(pi4 가 pi42 를 건드리지 않게)."""
    return re.compile(r"(?<![A-Za-z0-9_-])" + re.escape(name) + r"(?![A-Za-z0-9_-])")


def rules_for(cfg, target):
    rules = []
    if cfg.redact.get("hostname", True):
        rules += [(name_pattern(n), target.alias) for n in real_names(cfg, target)]
    if cfg.redact.get("home", True):
        home = str(Path.home())
        if home not in ("/", "") and len(home) > 1:
            rules.append((re.compile(re.escape(home) + r"(?![A-Za-z0-9_.-])"), "~"))
    rules += [(re.compile(p["re"]), p["to"]) for p in cfg.redact.get("patterns", [])]
    return rules


def apply_text(rules, text):
    count = 0
    for pattern, to in rules:
        text, n = pattern.subn(lambda m, to=to: to, text)
        count += n
    return text, count


def apply_bytes(rules, data):
    """바이트 → 바이트. UTF-8 이 아닌 바이트는 surrogateescape 로 그대로 지킨다."""
    if not rules:
        return data, 0
    text = data.decode("utf-8", errors="surrogateescape")
    text, count = apply_text(rules, text)
    return text.encode("utf-8", errors="surrogateescape"), count
