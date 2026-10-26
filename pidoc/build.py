"""build: render → HTML 한 파일(docs/out/site.html) → 선택 PDF(docs/out/site.pdf).

HTML 은 markdown-it-py(MIT), PDF 는 WeasyPrint(BSD) 가 있어야 한다. 없으면 그 명령만 친절하게 멈춘다.
한 파일에 여러 문서를 넣으므로 제목 앵커는 '<문서>--<제목>' 으로 만들고, 문서 사이 링크(x.md#제목)를 거기에 맞춘다.
"""

import html
import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

from . import doc as docmod
from .render import render
from .util import OK, PidocError

CSS = """\
body { font-family: 'NanumGothic', 'Nanum Gothic', sans-serif; line-height: 1.7;
       max-width: 52rem; margin: 2rem auto; padding: 0 1rem; color: #222; }
nav { border: 1px solid #ddd; padding: .5rem 1rem; margin-bottom: 2rem; }
nav ol { margin: .3rem 0; }
h1, h2, h3 { line-height: 1.3; }
section + section { border-top: 2px solid #eee; margin-top: 3rem; }
code, pre { font-family: 'D2Coding', 'NanumGothicCoding', monospace; }
pre { background: #f6f6f6; padding: .7rem; overflow-x: auto; white-space: pre-wrap; }
:not(pre) > code { background: #f2f2f2; padding: 0 .2rem; }
table { border-collapse: collapse; }
th, td { border: 1px solid #ccc; padding: .2rem .5rem; text-align: left; }
@page { size: A4; margin: 18mm 16mm; }
@media print { section { break-before: page; } nav { break-after: page; } body { max-width: none; margin: 0; } }
"""


def _markdown():
    try:
        from markdown_it import MarkdownIt
    except ImportError:
        raise PidocError("HTML 을 만들려면 markdown-it-py 가 필요합니다: pip install markdown-it-py")
    return MarkdownIt("commonmark").enable("table")


def _stem(path):
    return re.sub(r"[^\w-]", "-", PurePosixPath(path).with_suffix("").as_posix())


def doc_title(text, fallback):
    for line in text.splitlines():
        m = re.match(r"^#\s+(.*?)\s*#*\s*$", line)
        if m:
            return m.group(1)
    return fallback


def to_html(md, text, stem, stems):
    """문서 하나를 HTML 로. 제목에 id 를 달고 문서 사이 링크를 한 파일 안 앵커로 바꾼다."""
    tokens = md.parse(text)
    seen = {}
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            base = docmod.slug(tokens[i + 1].content)
            n = seen.get(base, 0)
            seen[base] = n + 1
            tok.attrSet("id", f"{stem}--{base if n == 0 else f'{base}-{n}'}")
        for child in tok.children or []:
            if child.type != "link_open":
                continue
            href = child.attrGet("href") or ""
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:|^//", href):
                continue
            path, _, anchor = unquote(href).partition("#")   # markdown-it 이 %인코딩한 한글을 되돌림
            if not path:
                child.attrSet("href", f"#{stem}--{anchor}")
            elif path.endswith(".md"):
                other = _stem(path)
                if other in stems:
                    child.attrSet("href", f"#{other}--{anchor}" if anchor else f"#doc-{other}")
    return md.renderer.render(tokens, md.options, {})


def build_html(cfg, outs):
    """[(src 상대 이름, out 경로)] → site.html 경로"""
    md = _markdown()
    title = cfg.build.get("title") or cfg.name or "문서"
    items = []
    for src_rel, out in outs:
        rel = out.relative_to(cfg.out_dir).as_posix()
        items.append((_stem(rel), out.read_text(encoding="utf-8"), rel))
    stems = {stem for stem, _, _ in items}
    toc, sections = [], []
    for stem, text, rel in items:
        name = doc_title(text, rel)
        toc.append(f'<li><a href="#doc-{stem}">{html.escape(name)}</a></li>')
        sections.append(f'<section id="doc-{stem}">\n{to_html(md, text, stem, stems)}</section>')
    page = (
        "<!doctype html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{html.escape(title)}</title>\n<style>\n{CSS}</style>\n</head>\n<body>\n"
        f"<nav><strong>{html.escape(title)}</strong>\n<ol>\n" + "\n".join(toc) + "\n</ol></nav>\n"
        + "\n".join(sections) + "\n</body>\n</html>\n"
    )
    path = cfg.out_dir / "site.html"
    path.write_text(page, encoding="utf-8")
    return path


def _weasyprint():
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as e:
        raise PidocError("PDF 를 만들려면 WeasyPrint 가 필요합니다: pip install weasyprint "
                         f"(시스템 Pango 도 필요, https://doc.courtbouillon.org/weasyprint/ 참고) — {e.__class__.__name__}")
    return HTML


def _allowed(cfg, url):
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme == "data":
        return True
    return parsed.scheme == "file" and Path(unquote(parsed.path)).resolve().is_relative_to(cfg.root)


def url_fetcher(cfg):
    """PDF 를 만들 때 가져올 수 있는 주소: data: 와 저장소 안 file: 만(file:///etc/... 나 바깥 http 차단)."""
    try:
        from weasyprint.urls import URLFetcher          # WeasyPrint 67 이후
    except ImportError:
        URLFetcher = None
    if URLFetcher is not None:
        class SafeFetcher(URLFetcher):
            def fetch(self, url, headers=None):
                if not _allowed(cfg, url):
                    raise ValueError(f"PDF 에서 가져오지 않는 주소: {url}")
                return super().fetch(url, headers)
        return SafeFetcher(allowed_protocols=("data", "file"))

    from weasyprint import default_url_fetcher        # 옛 판

    def fetch(url, *args, **kwargs):
        if not _allowed(cfg, url):
            raise ValueError(f"PDF 에서 가져오지 않는 주소: {url}")
        return default_url_fetcher(url, *args, **kwargs)
    return fetch


def build_pdf(cfg, html_path):
    HTML = _weasyprint()
    pdf = Path(html_path).with_suffix(".pdf")
    HTML(filename=str(html_path), url_fetcher=url_fetcher(cfg)).write_pdf(str(pdf))
    return pdf


def order_files(cfg, files):
    order = cfg.build.get("order", [])
    def key(path):
        rel = path.relative_to(cfg.src_dir.resolve()).as_posix() if path.is_relative_to(cfg.src_dir.resolve()) else path.name
        return (order.index(rel) if rel in order else len(order), rel)
    return sorted(files, key=key)


def build(cfg, pdf=False):
    _markdown()                                   # 렌더 전에 의존부터 확인
    if pdf:
        _weasyprint()
    files = order_files(cfg, docmod.src_files(cfg))
    if not files:
        raise PidocError(f"만들 문서가 없습니다: {cfg.rel(cfg.src_dir)}/*.md")
    code = render(cfg, files)
    if code != OK:
        for old in (cfg.out_dir / "site.html", cfg.out_dir / "site.pdf"):
            if old.exists():
                old.unlink()
        print("렌더에 실패해 HTML 을 만들지 않았습니다(이전 site.html·site.pdf 도 지움)")
        return code
    outs = [(cfg.rel(f), docmod.out_path(cfg, f)) for f in files]
    page = build_html(cfg, outs)
    print(f"HTML: {cfg.rel(page)}")
    if pdf:
        print(f"PDF: {cfg.rel(build_pdf(cfg, page))}")
    return OK
