"""Shared read-only Markdown parsing and formal Wiki selection."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

import yaml

FORMAL = {"", "active", "confirmed", "ready", "reviewed", "published"}
EXCLUDED = {"drafts", "templates"}


@dataclass
class Page:
    path: Path
    relative: str
    meta: dict
    body: str
    raw: str
    sha256: str

    @property
    def title(self):
        match = re.search(r"^#\s+(.+)$", visible_text(self.body), re.M)
        return str(self.meta.get("title") or (match.group(1) if match else self.path.stem))

    @property
    def aliases(self):
        value = self.meta.get("aliases", [])
        return [str(item) for item in (value if isinstance(value, list) else [value]) if item]


def frontmatter(text):
    text = text.lstrip("\ufeff")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ValueError("未闭合的 YAML 属性")
    try:
        meta = yaml.safe_load("".join(lines[1:end])) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"无法解析 YAML 属性：{exc}") from exc
    if not isinstance(meta, dict):
        raise ValueError("YAML 属性必须是对象")
    return meta, "".join(lines[end + 1:])


def read_page(vault, path):
    vault, path = Path(vault).resolve(), Path(path)
    if path.is_symlink() or not path.resolve().is_relative_to(vault):
        raise ValueError(f"页面越出知识仓库或为符号链接：{path}")
    data = path.read_bytes()
    text = data.decode("utf-8")
    meta, body = frontmatter(text)
    return Page(path, path.relative_to(vault).as_posix(), meta, body, text,
                hashlib.sha256(data).hexdigest())


def formal_pages(vault):
    vault = Path(vault).resolve()
    wiki = vault / "wiki"
    if wiki.is_symlink():
        raise ValueError("wiki 根目录不能是符号链接")
    pages = {}
    for path in sorted(wiki.rglob("*.md")):
        relative = path.relative_to(wiki)
        if any(p.startswith(".") or p.lower() in EXCLUDED for p in relative.parts) or path.name == "log.md":
            continue
        page = read_page(vault, path)
        if str(page.meta.get("status", "")).lower() in FORMAL and page.meta.get("type") != "draft":
            pages[page.relative] = page
    return pages


def visible_text(text, keep_code=False):
    """Mask fenced/inline code and comments without changing line numbers."""
    lines, fence = [], None
    for line in text.splitlines(keepends=True):
        match = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if match and fence is None:
            fence = match.group(1)
            lines.append("\n" if line.endswith("\n") else "")
        elif match and fence and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence):
            fence = None
            lines.append("\n" if line.endswith("\n") else "")
        elif fence and not keep_code:
            lines.append("\n" if line.endswith("\n") else "")
        else:
            lines.append(line)
    text = "".join(lines)
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group().count("\n"), text, flags=re.S)
    if not keep_code:
        text = re.sub(r"(`+)[^\n]*?\1", "", text)
    return text


def plain_text(text):
    text = visible_text(text, keep_code=True)
    text = re.sub(r"!?\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), text)
    text = re.sub(r"!?\[([^\]]*)\]\([^\n)]+\)", r"\1", text)
    return re.sub(r"[\s`*]+", " ", text).strip()


def links(text):
    """Yield (target, line, kind), excluding illustrative links inside code."""
    text = visible_text(text)
    for match in re.finditer(r"!?\[\[([^\]]+)\]\]", text):
        yield match.group(1).replace("\\|", "|").split("|", 1)[0], text.count("\n", 0, match.start()) + 1, "wiki"
    for match in re.finditer(r"!?\[[^\]\n]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)", text):
        yield match.group(1).strip("<>"), text.count("\n", 0, match.start()) + 1, "markdown"


def meta_links(page):
    for key in ("sources", "projects"):
        values = page.meta.get(key, [])
        if not isinstance(values, list):
            continue
        for value in values:
            value = str(value)
            found = list(links(value))
            if found:
                yield from ((target, 1, "metadata") for target, _, _ in found)
            elif value.startswith(("raw/", "wiki/", "extracted/")):
                yield value, 1, "metadata"


def resolve_link(vault, page, target, kind="wiki"):
    vault = Path(vault).resolve()
    target = unquote(target).strip()
    if re.match(r"^[a-zA-Z][\w+.-]*:", target) or target.startswith("//"):
        return None, "", "external"
    name, _, anchor = target.partition("#")
    if not name:
        return page.path, anchor, "ok"
    if Path(name).is_absolute():
        return None, anchor, "outside"
    if kind == "markdown" or name.startswith(("./", "../")):
        candidates = [page.path.parent / name]
    else:
        candidates = [vault / name]
        if "/" not in name:
            candidates.insert(0, page.path.parent / name)
    expanded = [p for item in candidates for p in (item, item.with_suffix(".md") if not item.suffix else item)]
    for item in expanded:
        if item.is_file():
            if not item.resolve().is_relative_to(vault):
                return None, anchor, "outside"
            return item, anchor, "ok"
    if any(not p.resolve().is_relative_to(vault) for p in candidates):
        return None, anchor, "outside"
    if kind != "markdown" and "/" not in name:
        matches = [p for p in (vault / "wiki").rglob("*.md") if p.stem == Path(name).stem]
        # Aliases are a navigation aid; ambiguity is never guessed away.
        if not matches:
            matches = [p.path for p in formal_pages(vault).values() if name in p.aliases]
        if len(matches) == 1:
            return matches[0], anchor, "ok"
        if len(matches) > 1:
            return None, anchor, "ambiguous"
    return None, anchor, "missing"


def headings(body):
    stack = []
    for line in visible_text(body).splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match:
            level, title = len(match.group(1)), match.group(2)
            stack = [item for item in stack if item[0] < level]
            stack.append((level, title))
            yield title, " > ".join(item[1] for item in stack)


def heading_slug(title):
    return re.sub(r"[^\w\s-]", "", title.lower()).strip().replace(" ", "-")


def chunks(page, max_chars=1800, overlap=200):
    if max_chars <= 0 or overlap < 0 or overlap >= max_chars:
        raise ValueError("分块长度必须为正，重叠范围须小于分块长度")
    stack, buffer, heading = [], [], page.title
    fence = None

    def emit():
        text = plain_text("\n".join(buffer))
        start = 0
        while start < len(text):
            yield heading, text[start:start + max_chars]
            if start + max_chars >= len(text):
                break
            start += max_chars - overlap

    for line in page.body.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            buffer.append(line)
            continue
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line) if not fence else None
        if match:
            yield from emit()
            buffer = []
            level, title = len(match.group(1)), match.group(2)
            stack = [item for item in stack if item[0] < level] + [(level, title)]
            heading = " > ".join(item[1] for item in stack)
        else:
            buffer.append(line)
    yield from emit()
