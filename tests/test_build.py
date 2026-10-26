import sys

import pytest

from conftest import pidoc


def docs(root):
    src = root / "docs/src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "quick.md").write_text("# 빠른 시작\n\n## 설치\n\n명령: {{fact:minimon.commands|join|code}}\n\n"
                                  "[설정 보기](ref.md#설정-키) · [위로](#설치) · [코드](../../minimon/web.py)\n")
    (src / "ref.md").write_text("# 레퍼런스\n\n## 설치\n\n## 설정 키\n\n| 키 | 설명 |\n|---|---|\n| path | 경로 |\n")
    toml = root / "docs/pidoc.toml"
    toml.write_text(toml.read_text() + '\n[build]\ntitle = "minimon 문서"\norder = ["quick.md", "ref.md"]\n')


def test_build_html(miniproj):
    pytest.importorskip("markdown_it")
    pidoc("collect")
    docs(miniproj)
    assert pidoc("build") == 0
    page = (miniproj / "docs/out/site.html").read_text()
    assert "<title>minimon 문서</title>" in page
    assert "'NanumGothic'" in page
    assert page.index('id="doc-quick"') < page.index('id="doc-ref"')
    assert '<h2 id="quick--설치">' in page and '<h2 id="ref--설치">' in page
    assert 'href="#ref--설정-키"' in page and 'href="#quick--설치"' in page
    assert 'href="../../minimon/web.py"' in page
    assert "<code>scan, serve</code>" in page
    assert "<table>" in page
    assert '<li><a href="#doc-quick">빠른 시작</a></li>' in page


def test_build_stops_on_render_error(miniproj, capsys):
    pytest.importorskip("markdown_it")
    docs(miniproj)                        # collect 하지 않아 사실이 없다
    assert pidoc("build") == 1
    assert not (miniproj / "docs/out/site.html").exists()


def test_build_without_markdown_it(miniproj, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "markdown_it", None)
    docs(miniproj)
    assert pidoc("build") == 2
    assert "pip install markdown-it-py" in capsys.readouterr().err


def test_build_pdf_without_weasyprint(miniproj, monkeypatch, capsys):
    pytest.importorskip("markdown_it")
    monkeypatch.setitem(sys.modules, "weasyprint", None)
    pidoc("collect")
    docs(miniproj)
    assert pidoc("build", "--pdf") == 2
    assert "WeasyPrint 가 필요합니다" in capsys.readouterr().err
    assert not (miniproj / "docs/out/site.html").exists()     # 렌더 전에 멈춤


def test_build_pdf(miniproj):
    pytest.importorskip("markdown_it")
    pytest.importorskip("weasyprint")
    pidoc("collect")
    docs(miniproj)
    assert pidoc("build", "--pdf") == 0
    assert (miniproj / "docs/out/site.pdf").read_bytes().startswith(b"%PDF")


def test_link_from_subfolder_doc_is_resolved():
    """en/quickstart.md 의 ../reference.md#x 는 reference 문서 안 앵커로(Codex 최종 검토 지적)."""
    import pytest
    pytest.importorskip("markdown_it")
    from pidoc.build import _markdown, to_html
    out = to_html(_markdown(), "[참조](../reference.md#x)\n", "en-quickstart", {"reference", "en-quickstart"}, "en/quickstart.md")
    assert 'href="#reference--x"' in out
