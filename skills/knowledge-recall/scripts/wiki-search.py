#!/usr/bin/env python3
"""Chinese/technical-term BM25 candidates over formal Wiki; cache stays outside vault."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import unicodedata
from contextlib import closing
from pathlib import Path

from wiki_core import chunks, formal_pages

VERSION = "2-cjk-bigram-technical"
TOKEN = re.compile(r"[\u3400-\u9fff]+|[a-z0-9]+(?:[_.:+/-][a-z0-9]+)*", re.I)
QUESTION_WORDS = {"是什么", "为什么", "如何", "怎么", "有哪些", "请问", "我们", "目前"}


def normalized(text):
    return unicodedata.normalize("NFKC", str(text)).casefold()


def terms(text, query=False):
    text = normalized(text)
    if query:
        for word in sorted(QUESTION_WORDS, key=len, reverse=True):
            text = text.replace(word, " ")
    result = []
    for value in TOKEN.findall(text):
        if re.fullmatch(r"[\u3400-\u9fff]+", value):
            result += [value[i:i + 2] for i in range(len(value) - 1)] if len(value) > 1 else [value]
        else:
            result.append(value)
            parts = re.split(r"[_.:+/-]", value)
            if len(parts) > 1:
                result += [p for p in parts if len(p) > 1]
    return result


def encoded(text):
    # Hex gives FTS5 unambiguous tokens, including API punctuation and CJK grams.
    return " ".join("t" + term.encode().hex() for term in terms(text))


def cache_path(vault, cache_dir=None):
    vault = Path(vault).resolve()
    cache = Path(cache_dir or Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "knowledge-workflow").resolve()
    if cache.is_relative_to(vault):
        raise ValueError("检索缓存必须位于知识仓库之外")
    return cache / hashlib.sha256(str(vault).encode()).hexdigest()[:20] / "fts.sqlite"


def manifest(pages):
    return {name: page.sha256 for name, page in pages.items()}


def stats(vault, cache_dir=None):
    path = cache_path(vault, cache_dir)
    pages = formal_pages(vault)
    if not path.exists():
        return {"status": "missing", "fresh": False, "pages": len(pages), "database": str(path)}
    try:
        with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as con:
            meta = dict(con.execute("SELECT key,value FROM metadata"))
            previous = dict(con.execute("SELECT path,sha256 FROM pages"))
            count = con.execute("SELECT count(*) FROM chunks").fetchone()[0]
        fresh = meta.get("version") == VERSION and previous == manifest(pages)
        return {"status": "ready", "fresh": fresh, "pages": len(previous), "chunks": count, "database": str(path)}
    except sqlite3.Error:
        return {"status": "invalid", "fresh": False, "database": str(path)}


def schema(con):
    con.executescript('''
      CREATE TABLE pages(path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, metadata TEXT NOT NULL);
      CREATE TABLE chunks(id INTEGER PRIMARY KEY, path TEXT NOT NULL, heading TEXT NOT NULL, text TEXT NOT NULL);
      CREATE INDEX chunks_path ON chunks(path);
      CREATE VIRTUAL TABLE search USING fts5(title, aliases, heading, text, tokenize='ascii');
      CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    ''')
    con.execute("INSERT INTO metadata VALUES ('version',?)", (VERSION,))


def build(vault, cache_dir=None):
    path = cache_path(vault, cache_dir)
    # Parse before opening a writer: malformed YAML leaves the last good DB intact.
    pages = formal_pages(vault)
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.parent / "build.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        fd, staged = tempfile.mkstemp(prefix="fts-", suffix=".sqlite", dir=path.parent)
        os.close(fd)
        staged = Path(staged)
        changed, removed = [], []
        try:
            with closing(sqlite3.connect(staged)) as con:
                valid = False
                if path.exists():
                    try:
                        with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as old:
                            valid = dict(old.execute("SELECT key,value FROM metadata")).get("version") == VERSION
                            if valid:
                                old.backup(con)
                    except sqlite3.Error:
                        valid = False
                if not valid:
                    schema(con)
                previous = dict(con.execute("SELECT path,sha256 FROM pages"))
                removed = sorted(set(previous) - set(pages))
                changed = [name for name, page in pages.items() if previous.get(name) != page.sha256]
                for name in removed + changed:
                    con.execute("DELETE FROM search WHERE rowid IN (SELECT id FROM chunks WHERE path=?)", (name,))
                    con.execute("DELETE FROM chunks WHERE path=?", (name,))
                    con.execute("DELETE FROM pages WHERE path=?", (name,))
                for name in changed:
                    page = pages[name]
                    con.execute("INSERT INTO pages VALUES (?,?,?)", (name, page.sha256, json.dumps(page.meta, ensure_ascii=False, default=str)))
                    for heading, text in chunks(page):
                        row = con.execute("INSERT INTO chunks(path,heading,text) VALUES (?,?,?)", (name, heading, text))
                        con.execute("INSERT INTO search(rowid,title,aliases,heading,text) VALUES (?,?,?,?,?)",
                                    (row.lastrowid, encoded(page.title), encoded(" ".join(page.aliases)), encoded(heading), encoded(text)))
                if manifest(formal_pages(vault)) != manifest(pages):
                    raise ValueError("构建期间 Wiki 发生变化，旧索引已保留；请重试")
                con.commit()
            os.replace(staged, path)
        finally:
            staged.unlink(missing_ok=True)
    return {**stats(vault, cache_dir), "status": "built", "changed": len(changed), "removed": len(removed)}


def search(vault, query, limit=10, scope="wiki", cache_dir=None, refresh=True):
    if limit < 1 or limit > 100:
        raise ValueError("limit 范围为 1..100")
    query_terms = list(dict.fromkeys(terms(query, query=True)))
    if not query_terms or len(query_terms) > 256:
        raise ValueError("查询需包含有效词项，最多 256 个词项")
    scope = Path(scope).as_posix().rstrip("/")
    if scope != "wiki" and not scope.startswith("wiki/") or ".." in Path(scope).parts:
        raise ValueError("检索范围必须是 wiki 内的页面或目录")
    state = stats(vault, cache_dir)
    if not state["fresh"]:
        if not refresh:
            raise ValueError("索引缺失或过时；需要 build，或允许自动刷新")
        build(vault, cache_dir)
    path = cache_path(vault, cache_dir)
    match = " OR ".join('"t' + term.encode().hex() + '"' for term in query_terms)
    # Scope predicates precede LIMIT; unrelated projects cannot consume candidates.
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as con:
        rows = con.execute('''SELECT c.path,c.heading,c.text,p.metadata,bm25(search,8,10,4,1),p.sha256
          FROM search JOIN chunks c ON c.id=search.rowid JOIN pages p ON p.path=c.path
          WHERE search MATCH ? AND (c.path=? OR substr(c.path,1,?)=?)
          ORDER BY bm25(search,8,10,4,1) LIMIT ?''',
          (match, scope, len(scope) + 1, scope + "/", max(200, limit * 20))).fetchall()
    maximum = max((-row[4] for row in rows), default=1) or 1
    ranked = {}
    for name, heading, text, raw_meta, bm25, source_sha in rows:
        meta = json.loads(raw_meta)
        aliases = meta.get("aliases", [])
        aliases = aliases if isinstance(aliases, list) else [aliases]
        title = str(meta.get("title", Path(name).stem))
        combined = " ".join([title, *map(str, aliases), heading, text])
        matched = set(query_terms) & set(terms(combined))
        coverage = len(matched) / len(query_terms)
        phrase = normalized(query).strip()
        body_terms = set(terms(heading + " " + text))
        body_coverage = len(set(query_terms) & body_terms) / len(query_terms)
        exact = bool(phrase and phrase in normalized(heading + " " + text))
        title_exact = bool(phrase and any(phrase in normalized(v) for v in [title, *map(str, aliases)]))
        score = 0.35 * (-bm25 / maximum) + 0.25 * coverage + 0.25 * body_coverage + 0.15 * exact + 0.25 * title_exact
        position = min((normalized(text).find(t) for t in matched if t in normalized(text)), default=0)
        snippet = text[max(0, position - 80):max(0, position - 80) + 360]
        item = {"page_path": name, "heading_path": heading, "title": title,
                "source_sha256": source_sha,
                "sources": meta.get("sources", []), "snippet": snippet,
                "score": round(score, 6), "bm25": bm25, "matched_terms": sorted(matched),
                "coverage": round(coverage, 3), "section_coverage": round(body_coverage, 3)}
        if name not in ranked or score > ranked[name][0]:
            ranked[name] = (score, item)
    return {"query": query, "scope": scope, "candidate_only": True,
            "results": [item for _, item in sorted(ranked.values(), key=lambda pair: (-pair[0], pair[1]["page_path"]))[:limit]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True)
    parser.add_argument("--cache-dir")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build")
    sub.add_parser("stats")
    query = sub.add_parser("search")
    query.add_argument("query")
    query.add_argument("--limit", type=int, default=10)
    query.add_argument("--scope", default="wiki")
    query.add_argument("--no-refresh", action="store_true")
    args = parser.parse_args()
    try:
        result = search(args.vault, args.query, args.limit, args.scope, args.cache_dir, not args.no_refresh) if args.command == "search" else globals()[args.command](args.vault, args.cache_dir)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
