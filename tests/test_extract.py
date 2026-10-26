import json

from conftest import pidoc


def code_facts(root):
    return json.loads((root / "docs/facts/code.json").read_text())


def test_extract_cli(miniproj):
    assert pidoc("extract", "cli") == 0
    data = code_facts(miniproj)
    assert data["target"] == "code"
    f = data["facts"]
    assert f["cli.minimon.commands"]["value"] == ["scan", "serve"]
    assert f["cli.minimon.options"]["value"] == ["--config", "--limit"]
    assert f["cli.minimon.option.limit.default"]["value"] == 90
    assert f["cli.minimon.option.limit.default"]["type"] == "int"
    assert f["cli.minimon.option.config.help"]["value"] == "설정 파일"
    assert f["cli.minimon.description"]["source"] == "minimon/__main__.py"
    assert len(f["cli.minimon.description"]["source_sha256"]) == 64


def test_extract_config(miniproj):
    assert pidoc("extract", "config") == 0
    f = code_facts(miniproj)["facts"]
    assert f["config.limit.default"]["value"] == 90
    assert f["config.web.port.default"]["value"] == 8000
    assert f["config.web.enabled.default"]["value"] is False
    assert f["config.limit.example"]["value"] == 90
    assert f["config.limit.comment"]["value"] == "경고 기준(%) 넘으면 scan 이 1 로 끝남"
    assert f["config.web.port.comment"]["value"] == "웹 포트"
    assert "config.web.enabled.comment" not in f
    assert f["config.keys"]["value"] == ["path", "limit", "web.port", "web.enabled"]


def test_extract_http(miniproj):
    assert pidoc("extract", "http") == 0
    f = code_facts(miniproj)["facts"]
    assert f["http.get.paths"]["value"] == ["/health", "/disk", "/disk.json"]
    assert f["http.post.paths"]["value"] == ["/reset"]


def test_extract_py(miniproj):
    assert pidoc("extract", "py") == 0
    f = code_facts(miniproj)["facts"]
    assert f["py.minimon.doc"]["value"].startswith("minimon — 디스크")
    assert f["py.minimon.settings.load.doc"]["value"] == "설정 파일을 읽어 기본값과 합친다."
    assert "py.minimon.settings._private.doc" not in f
    assert f["py.minimon.web.handler.doc"]["value"] == "요청 처리기."


def test_reextract_drops_removed_keys(miniproj):
    pidoc("extract", "cli", "http")
    main = miniproj / "minimon/__main__.py"
    main.write_text(main.read_text().replace('    p.add_argument("--config", help="설정 파일")\n', ""))
    pidoc("extract", "cli")
    f = code_facts(miniproj)["facts"]
    assert "cli.minimon.option.config.help" not in f
    assert "http.get.paths" in f                  # 다른 종류는 그대로


def test_extract_config_needs_settings(miniproj, capsys):
    toml = miniproj / "docs/pidoc.toml"
    toml.write_text(toml.read_text().replace('config_module = "minimon/settings.py"\n', "")
                    .replace('config_example = "minimon.toml.example"\n', ""))
    assert pidoc("extract", "config") == 2
    assert "config_example" in capsys.readouterr().err


def test_collect_on_miniproj(miniproj):
    assert pidoc("collect") == 0
    f = json.loads((miniproj / "docs/facts/pc.json").read_text())["facts"]
    assert f["minimon.commands"]["value"] == ["scan", "serve"]
    assert f["minimon.scan_path"]["value"] == "/"
