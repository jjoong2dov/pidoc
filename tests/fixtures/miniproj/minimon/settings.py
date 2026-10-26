"""설정 읽기."""

import tomllib

DEFAULTS = {
    "path": "/",
    "limit": 90,
    "web": {"port": 8000, "enabled": False},
}


def load(path=None):
    """설정 파일을 읽어 기본값과 합친다."""
    cfg = dict(DEFAULTS)
    if path:
        with open(path, "rb") as f:
            cfg.update(tomllib.load(f))
    return cfg


def _private():
    """밖에서 쓰지 않는 함수."""
