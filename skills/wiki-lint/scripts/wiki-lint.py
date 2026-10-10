#!/usr/bin/env python3
"""Read-only Wiki structural checks; semantic review remains an explicit LLM step."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "knowledge-recall/scripts"))
from wiki_core import (formal_pages, frontmatter, heading_slug, headings, links,
                       meta_links, plain_text, resolve_link, visible_text)


def lint(vault, scope="wiki", mention_threshold=3):
    vault = Path(vault).resolve()
    scope = Path(scope).as_posix().rstrip("/")
    if (scope != "wiki" and not scope.startswith("wiki/")) or ".." in Path(scope).parts:
        raise ValueError("巡检范围必须是 wiki 内页面或目录")
    if mention_threshold < 2:
        raise ValueError("提及阈值至少为 2")
    pages = formal_pages(vault)
    selected = {name for name in pages if name == scope or name.startswith(scope + "/")}
    if not selected:
        raise ValueError("巡检范围内没有正式 Wiki 页面")
    issues, edges, navigation = [], defaultdict(set), defaultdict(set)
    page_cache, pdf_counts = {}, {}
    link_count = 0

    def add(rule, path, line, message, severity="warning", certainty="certain", evidence=None):
        if path not in selected:
            return
        identity = f"{rule}\0{path}\0{line}\0{message}"
        issues.append({"id": hashlib.sha256(identity.encode()).hexdigest()[:12], "rule": rule,
                       "page_path": path, "line": line, "severity": severity,
                       "certainty": certainty, "message": message, "evidence": evidence or [],
                       "suggestion": "回查所列页面与来源后，按已有授权修复；语义候选需人工／LLM 核验。"})

    def check_anchor(target_path, anchor):
        if not anchor:
            return None
        if target_path.suffix.lower() == ".pdf" and re.fullmatch(r"page=\d+", anchor):
            if target_path not in pdf_counts:
                try:
                    import pymupdf
                    with pymupdf.open(target_path) as doc:
                        pdf_counts[target_path] = len(doc)
                except Exception as exc:
                    return ("pdf-unchecked", f"PDF 页码未能程序核验：{exc}", "warning", "unverified")
            page = int(anchor.split("=", 1)[1])
            if not 1 <= page <= pdf_counts[target_path]:
                return ("pdf-page", f"PDF 页码 {page} 超出 1..{pdf_counts[target_path]}", "error", "certain")
        elif target_path.suffix.lower() == ".md":
            if target_path not in page_cache:
                _, body = frontmatter(target_path.read_text(encoding="utf-8"))
                page_cache[target_path] = body
            body = page_cache[target_path]
            if anchor.startswith("^"):
                exists = bool(re.search(r"(?:^|\s)" + re.escape(anchor) + r"(?:\s|$)", visible_text(body)))
            else:
                titles = [title for title, _ in headings(body)]
                exists = anchor in titles or anchor.lower() in {heading_slug(title) for title in titles}
            if not exists:
                return ("heading-anchor", f"标题／块锚点不存在：{anchor}", "error", "certain")
        return None

    for name, page in pages.items():
        for key in ("topics", "projects", "sources", "aliases"):
            if key in page.meta and not isinstance(page.meta[key], list):
                add("metadata-type", name, 1, f"{key} 属性需为列表", "error")
        if page.meta.get("type") in {"concept", "analysis", "source-summary"} and not page.meta.get("sources"):
            add("missing-sources", name, 1, "知识正文未声明 sources；需核对依据或明确对话来源")
        body_refs = list(links(page.body))
        is_nav = page.path.name == "index.md" or page.meta.get("type") in {"project-index", "concept-map", "concept-table"}
        for target, line, kind in body_refs + list(meta_links(page)):
            if name in selected:
                link_count += 1
            path, anchor, status = resolve_link(vault, page, target, kind)
            if status == "external":
                continue
            if status != "ok":
                add("link-" + status, name, line, f"链接{status}：{target}", "error")
                continue
            relative = path.relative_to(vault).as_posix()
            if relative in pages and relative != name:
                edges[name].add(relative)
                if is_nav and kind != "metadata":
                    navigation[name].add(relative)
            elif relative.startswith("wiki/") and path.suffix == ".md" and relative not in pages:
                add("nonformal-link", name, line, f"正式页面引用非正式／排除页面：{relative}", "info", "candidate")
            problem = check_anchor(path, anchor)
            if problem:
                rule, message, severity, certainty = problem
                add(rule, name, line, message + f"（{target}）", severity, certainty)

    incoming = Counter(target for targets in edges.values() for target in targets)
    reached, queue = {"wiki/index.md"}, deque(["wiki/index.md"])
    while queue:
        current = queue.popleft()
        for target in navigation[current] - reached:
            reached.add(target)
            queue.append(target)
    for name in selected:
        if name != "wiki/index.md" and not incoming[name]:
            add("orphan", name, 1, "没有其他正式页面的入链")
        if name not in reached:
            add("index-unreachable", name, 1, "无法沿总入口及项目／主题索引导航到此页面")

    undirected = defaultdict(set)
    for name, targets in edges.items():
        for target in targets:
            undirected[name].add(target)
            undirected[target].add(name)
    unseen = set(pages)
    while unseen:
        first = min(unseen)
        component, queue = {first}, deque([first])
        while queue:
            for target in undirected[queue.popleft()] - component:
                component.add(target)
                queue.append(target)
        unseen -= component
        if len(component) > 1 and "wiki/index.md" not in component:
            for name in sorted(component & selected):
                add("isolated-cluster", name, 1, "页面群与总知识网络隔离", evidence=sorted(component))

    titles, bodies = defaultdict(list), defaultdict(list)
    for name, page in pages.items():
        titles[page.title.casefold()].append(name)
        text = plain_text(page.body)
        if len(text) >= 80:
            bodies[hashlib.sha256(text.encode()).hexdigest()].append(name)
    for rule, groups in (("duplicate-title", titles), ("duplicate-body", bodies)):
        for group in groups.values():
            if len(group) > 1:
                for name in group:
                    add(rule, name, 1, "多个页面标题／正文相同，需核对是否重复维护", evidence=group)

    maps = [page for page in pages.values() if page.meta.get("type") in {"concept-map", "concept-table"}]
    for mapping in maps:
        linked = edges[mapping.relative]
        for target in linked:
            if pages[target].meta.get("type") != "concept":
                continue
            if not pages[target].meta.get("evidence_state"):
                add("concept-evidence-state", target, 1, "概念表关联的概念正文未记录 evidence_state", "info", "candidate")
        parent = mapping.path.parent.relative_to(vault).as_posix()
        for name, page in pages.items():
            if name.startswith(parent + "/") and page.meta.get("type") == "concept" and name not in linked:
                add("concept-map-missing", name, 1, f"同主题概念未出现在概念表：{mapping.relative}")

    # Lexical candidate discovery: frequency is NOT a verdict that a page is needed.
    existing = {value.casefold() for page in pages.values() for value in [page.title, page.path.stem, *page.aliases]}
    candidates = defaultdict(set)
    stop = {"原件", "来源", "分析", "推论", "注意", "关键结论", "当前状态", "待确认", "待核实", "Summary", "TODO"}
    for name in selected:
        body = visible_text(pages[name].body)
        terms = set(re.findall(r"\*\*([^*\n]{2,24})\*\*", body))
        terms |= set(re.findall(r"\b[A-Z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*\b", body))
        for term in terms:
            if term not in stop and term.casefold() not in existing and len(term) >= 3:
                candidates[term].add(name)
    for term, mentions in sorted(candidates.items(), key=lambda item: (-len(item[1]), item[0]))[:30]:
        if len(mentions) >= mention_threshold:
            first = min(mentions)
            add("frequent-term", first, 1, f"术语候选 {term} 在 {len(mentions)} 个页面出现，未匹配标题或别名",
                "info", "candidate", sorted(mentions))
    order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: (order[i["severity"]], i["page_path"], i["line"], i["rule"]))
    return {"scope": scope, "read_only": True, "pages_checked": len(selected), "graph_pages": len(pages),
            "links_checked": link_count, "counts": dict(Counter(item["severity"] for item in issues)),
            "findings": issues, "semantic_review": {"status": "not_performed",
              "checks": ["按用途核查内容深度", "链接语义相关性", "对齐条件后的命题矛盾", "来源时效及证据质量", "知识缺口与补证建议"]}}


def markdown(report):
    lines = [f"# Wiki 巡检：{report['scope']}", "", f"程序检查 {report['pages_checked']} 页、{report['links_checked']} 个链接。只读；语义检查尚未执行。", ""]
    for issue in report["findings"]:
        lines += [f"- [{issue['severity']} / {issue['certainty']}] {issue['page_path']}:{issue['line']} — {issue['message']}",
                  f"  - 依据：{', '.join(issue['evidence']) or '上述位置'}", f"  - 建议：{issue['suggestion']}"]
    if not report["findings"]:
        lines.append("本次程序检查未发现结构问题；不代表已完成语义审查。")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True)
    parser.add_argument("--scope", default="wiki")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--mention-threshold", type=int, default=3)
    args = parser.parse_args()
    try:
        report = lint(args.vault, args.scope, args.mention_threshold)
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + "\n")
    print(markdown(report) if args.format == "markdown" else json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(1 if report["counts"].get("error", 0) else 0)


if __name__ == "__main__":
    main()
