"""Validate notebooks, local documentation links and GitHub metadata without data."""

import ast
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import mistune
import nbformat
import yaml

ROOT = Path(__file__).resolve().parents[1]


class HTMLLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        self.urls.extend(value for name, value in attrs if name in {"href", "src"} and value)


def markdown_links(text):
    tokens = mistune.create_markdown(renderer="ast")(text)
    urls = []

    def walk(items):
        for item in items:
            if item["type"] in {"link", "image"}:
                urls.append(item["attrs"]["url"])
            elif item["type"] in {"block_html", "inline_html"}:
                parser = HTMLLinks()
                parser.feed(item["raw"])
                urls.extend(parser.urls)
            walk(item.get("children", []))

    walk(tokens)
    return urls


def check_document_links(path, root):
    for url in markdown_links(path.read_text()):
        parts = urlsplit(url)
        if parts.scheme or parts.netloc or not parts.path:
            continue
        target = (path.parent / unquote(parts.path)).resolve()
        if not target.is_relative_to(root.resolve()) or not target.exists():
            raise ValueError(f"{path.relative_to(root)}: broken local link {url}")


def check_notebook(path):
    notebook = nbformat.read(path, as_version=4)
    nbformat.validate(notebook)
    for index, cell in enumerate(notebook.cells):
        if cell.cell_type == "code":
            ast.parse(cell.source, filename=f"{path.name}:cell {index + 1}")
            if any(output.output_type == "error" for output in cell.outputs):
                raise ValueError(f"{path.name}: cell {index + 1} contains a saved error")


def main():
    documents = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", *sorted((ROOT / "docs").glob("*.md"))]
    for path in documents:
        check_document_links(path, ROOT)
    for path in (ROOT / "src").glob("*.ipynb"):
        check_notebook(path)
    for path in (ROOT / ".github").rglob("*.yml"):
        yaml.safe_load(path.read_text())
    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text())
    for key in ["cff-version", "message", "title", "authors", "doi"]:
        if not citation.get(key):
            raise ValueError(f"CITATION.cff: missing {key}")
    print("PASS: notebook schema/syntax, saved errors, local documentation links and YAML metadata.")


if __name__ == "__main__":
    main()
