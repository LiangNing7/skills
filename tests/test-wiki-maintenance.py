#!/usr/bin/env python3
"""Observable search/health behavior and protected-data invariants in isolated vaults."""
import hashlib
import importlib.util
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/knowledge-recall/scripts"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


searcher = load("wiki_search", "skills/knowledge-recall/scripts/wiki-search.py")
checker = load("wiki_lint", "skills/wiki-lint/scripts/wiki-lint.py")
syncer = load("wiki_sync", "skills/wiki-sync/scripts/sync-wiki.py")
from wiki_core import formal_pages, resolve_link, read_page


class MaintenanceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.vault = self.base / "vault"
        self.cache = self.base / "cache"
        self.vault.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, body):
        path = self.vault / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def query(self, query, **kw):
        return searcher.search(self.vault, query, cache_dir=self.cache, **kw)["results"]

    def test_chinese_technical_alias_and_code(self):
        self.write("wiki/index.md", "# 导航\n[[wiki/memory]]\n[[wiki/noise]]")
        self.write("wiki/memory.md", "---\ntitle: 显存共享\naliases:\n  - GPU isolation\nsources:\n  - raw/paper.pdf\n---\n# 显存共享\n\n## 控制\n显存隔离与GPU资源调度机制。\n```c\nCUDA_DEVICE_MEMORY_LIMIT=3000;\n```\n")
        self.write("wiki/noise.md", "---\ntitle: 不相关段落\n---\n# 不相关\n" + "调度资源机制。" * 50)
        for query in ["显存隔离", "GPU", "GPU isolation", "CUDA_DEVICE_MEMORY_LIMIT", "如何实现显存隔离"]:
            with self.subTest(query=query):
                results = self.query(query)
                self.assertEqual(results[0]["page_path"], "wiki/memory.md")
                self.assertIsInstance(results[0]["sources"], list)
                self.assertEqual(results[0]["sources"], ["raw/paper.pdf"])
                self.assertIn("控制", results[0]["heading_path"])
        self.assertEqual(len(self.query("显存隔离")), len({r["page_path"] for r in self.query("显存隔离")}))

    def test_content_hash_deletion_status_and_scope(self):
        page = self.write("wiki/a/page.md", "# Alpha\n旧内容。")
        self.write("wiki/b/page.md", "# Beta\n全新词项。")
        self.query("旧内容")
        stamp = page.stat().st_mtime
        page.write_text("# Alpha\n全新词项。", encoding="utf-8")
        os.utime(page, (stamp, stamp))
        self.assertFalse(searcher.stats(self.vault, self.cache)["fresh"])
        self.assertEqual(self.query("全新词项", scope="wiki/a")[0]["page_path"], "wiki/a/page.md")
        page.unlink()
        self.assertFalse(searcher.stats(self.vault, self.cache)["fresh"])
        self.assertEqual(self.query("全新词项", scope="wiki/a"), [])
        beta = self.vault / "wiki/b/page.md"
        beta.write_text("---\nstatus: proposed\n---\n# Beta\n全新词项。")
        self.assertEqual(self.query("全新词项"), [])

    def test_filters_match_sync_and_protected_hashes(self):
        raw = self.write("raw/paper.md", "原件 immutable")
        self.write("wiki/facts.md", "---\nstatus: active\n---\n# Fact\n事实")
        for name in ["wiki/log.md", "wiki/drafts/x.md", "wiki/templates/x.md", "wiki/.private/x.md"]:
            self.write(name, "# 敏感候选\n秘密词项")
        self.write("wiki/proposal.md", "---\nstatus: proposed\n---\n# 秘密词项")
        before = hashlib.sha256(raw.read_bytes()).hexdigest()
        self.assertEqual(set(formal_pages(self.vault)), {"wiki/facts.md"})
        self.assertEqual(set(syncer.collect(self.vault)), {"facts.md"})
        self.assertEqual(self.query("秘密词项"), [])
        self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(), before)
        with self.assertRaises(ValueError):
            searcher.build(self.vault, self.vault / "cache")

    def test_failed_build_preserves_index(self):
        page = self.write("wiki/a.md", "# 原始词项\n真实证据")
        self.query("原始词项")
        database = searcher.cache_path(self.vault, self.cache)
        original = database.read_bytes()
        page.write_text("---\nsources: [broken\n---\n# 损坏")
        with self.assertRaises(Exception):
            searcher.build(self.vault, self.cache)
        self.assertEqual(database.read_bytes(), original)

    def test_titles_weighted_no_fts_injection(self):
        self.write("wiki/a.md", "---\ntitle: GPUDirect RDMA\n---\n# GPUDirect RDMA\n设备数据传输。")
        self.write("wiki/b.md", "# 普通资料\n" + "GPUDirect RDMA " * 20)
        self.assertEqual(self.query("GPUDirect RDMA")[0]["page_path"], "wiki/a.md")
        self.query('RDMA\" OR * NEAR(\"')
        with self.assertRaises(ValueError):
            self.query("RDMA", scope="../raw")

    def test_lint_links_navigation_code_and_physical_pages(self):
        self.write("wiki/index.md", "# 导航\n[[wiki/topic/index]]")
        self.write("wiki/topic/index.md", "# 导航\n| 页面 |\n| --- |\n| [[wiki/topic/good\\|Good]] |\n[[wiki/topic/bad]]")
        self.write("wiki/topic/good.md", "# Good\n\n## 已有标题\n[[wiki/topic/index]]\n```md\n[[不存在的示例]]\n```\n")
        self.write("wiki/topic/bad.md", "# Bad\n[[wiki/topic/good#缺失标题]]\n[[wiki/missing]]\n[[raw/paper.pdf#page=3]]")
        pdf = self.vault / "raw/paper.pdf"
        pdf.parent.mkdir()
        with pymupdf.open() as document:
            document.new_page()
            document.new_page()
            document.save(pdf)
        before = {p: p.read_bytes() for p in self.vault.rglob("*") if p.is_file()}
        report = checker.lint(self.vault, scope="wiki/topic")
        rules = {item["rule"] for item in report["findings"]}
        self.assertTrue({"heading-anchor", "link-missing", "pdf-page"} <= rules)
        self.assertNotIn("index-unreachable", rules)
        self.assertFalse(any("不存在的示例" in item["message"] for item in report["findings"]))
        self.assertEqual(report["semantic_review"]["status"], "not_performed")
        self.assertEqual(before, {p: p.read_bytes() for p in self.vault.rglob("*") if p.is_file()})

    def test_orphan_cluster_and_ambiguous_name(self):
        self.write("wiki/index.md", "# 导航\n[[same]]")
        self.write("wiki/a/same.md", "# A\n[[wiki/b/same]]")
        self.write("wiki/b/same.md", "# B\n[[wiki/a/same]]")
        self.write("wiki/orphan.md", "# 独立页面")
        rules = {item["rule"] for item in checker.lint(self.vault)["findings"]}
        self.assertTrue({"link-ambiguous", "orphan", "isolated-cluster", "index-unreachable"} <= rules)

    def test_alias_resolution_and_no_escape(self):
        path = self.write("wiki/a.md", "---\naliases:\n - 中文别名\n---\n# A")
        page = read_page(self.vault, path)
        self.assertEqual(resolve_link(self.vault, page, "中文别名")[0], path)
        self.assertEqual(resolve_link(self.vault, page, "../../external", "markdown")[2], "outside")

    def test_heading_inside_code_does_not_split_search_section(self):
        self.write("wiki/a.md", "# Code\n## 真实章节\n```python\n# fake heading\nibv_post_send(queue)\n```\n")
        self.assertIn("真实章节", self.query("ibv_post_send")[0]["heading_path"])
        self.assertNotIn("fake heading", self.query("ibv_post_send")[0]["heading_path"])

    def test_incremental_build_and_rename(self):
        old = self.write("wiki/old.md", "# 唯一词项\n内容")
        first = searcher.build(self.vault, self.cache)
        self.assertEqual(first["changed"], 1)
        self.assertEqual(searcher.build(self.vault, self.cache)["changed"], 0)
        old.rename(self.vault / "wiki/new.md")
        changed = searcher.build(self.vault, self.cache)
        self.assertEqual((changed["changed"], changed["removed"]), (1, 1))
        self.assertEqual(self.query("唯一词项")[0]["page_path"], "wiki/new.md")

    def test_alias_hit_selects_relevant_section(self):
        self.write("wiki/a.md", "---\naliases: [显存隔离]\n---\n# GPU\n## 无关短节\nCPU\n## 具体机制\n显存隔离通过容量上限与访问条件区分。" + "这里列出配置条件。" * 12)
        self.assertIn("具体机制", self.query("显存隔离")[0]["heading_path"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
