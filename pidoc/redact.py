"""가리기: 증거와 사실에서 IP·실제 호스트 이름(→ alias)·이 PC 홈 경로(→ ~)를 바꾼다."""

import ipaddress
import os
import re
import socket

IP_TEXT = "192.0.2.x"
IPV4_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?!\w|\.\w)", re.ASCII)


def _keep_ip(s):
    try:
        ip = ipaddress.IPv4Address(s)
    except ValueError:
        return True  # IP 가 아님(999.1.1.1 등)
    # 루프백·0.0.0.0·넷마스크(255.x 는 reserved)는 남긴다
    return ip.is_loopback or ip.is_unspecified or ip.is_reserved


class Redactor:
    def __init__(self, home, hosts, ip_text=IP_TEXT):
        """home: 이 PC 홈 경로, hosts: {실제 호스트 이름: alias}."""
        self.ip_text = ip_text
        self.home_re = None
        if home and home.rstrip("/"):
            self.home_re = re.compile(re.escape(home.rstrip("/")) + r"(?![\w.-])")
        names = {}
        for host, alias in hosts.items():
            for n in (host, host.split(".")[0]):
                if n and not n.isdigit() and n.lower() != "localhost":
                    names.setdefault(n.lower(), alias)
        self.names = names
        self.host_re = None
        if names:
            alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
            self.host_re = re.compile(rf"(?<![\w.-])(?:{alt})(?![\w-])", re.IGNORECASE)

    @classmethod
    def from_config(cls, cfg):
        hosts = {}
        local = [t.alias for t in cfg.targets.values() if t.kind == "local"]
        for t in cfg.targets.values():
            if t.kind == "ssh":
                hosts[t.host.rpartition("@")[2]] = t.alias
        hosts.setdefault(socket.gethostname(), local[0] if local else "localhost")
        return cls(os.path.expanduser("~"), hosts)

    def text(self, s):
        if self.home_re:
            s = self.home_re.sub("~", s)
        if self.host_re:
            s = self.host_re.sub(lambda m: self.names[m.group(0).lower()], s)
        return IPV4_RE.sub(lambda m: m.group(0) if _keep_ip(m.group(0)) else self.ip_text, s)

    def bytes(self, b):
        # UTF-8 이 아닌 바이트도 그대로 남긴다
        return self.text(b.decode("utf-8", "surrogateescape")).encode("utf-8", "surrogateescape")

    def obj(self, o):
        if isinstance(o, str):
            return self.text(o)
        if isinstance(o, list):
            return [self.obj(x) for x in o]
        if isinstance(o, dict):
            return {k: self.obj(v) for k, v in o.items()}
        return o
