"""examples/pimon 견본이 깨지지 않았는지(설정 검사와 숫자·용어·링크 검사)."""

import shutil
from pathlib import Path

from pidoc import config

from conftest import pidoc

EXAMPLE = Path(__file__).parent.parent / "examples" / "pimon" / "docs"


def test_example_config_loads():
    cfg = config.load(EXAMPLE / "pidoc.toml")
    assert set(cfg.targets) == {"pc", "pi"}
    assert cfg.targets["pi"].kind == "ssh"


def test_example_docs_pass_static_checks(tmp_path, monkeypatch):
    root = tmp_path / "pimon"
    shutil.copytree(EXAMPLE, root / "docs")
    monkeypatch.chdir(root)
    assert pidoc("check", "--only", "numbers", "terms", "links") == 0
