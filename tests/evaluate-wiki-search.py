#!/usr/bin/env python3
"""Small auditable retrieval sample; compares identical chunks against default FTS5."""
import argparse
import importlib.util
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/knowledge-recall/scripts"))
from wiki_core import chunks, formal_pages

spec = importlib.util.spec_from_file_location("wiki_search", ROOT / "skills/knowledge-recall/scripts/wiki-search.py")
searcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(searcher)

GPU = "wiki/projects/gpu-pooling-virtualization/"
THESIS = "wiki/thesis/embodied-rsi/"
CASES = [
    ("显存隔离", {"wiki/shared/gpu/sharing-and-isolation.md"}),
    ("内存完成语义", {"wiki/shared/gpu/memory-and-completion.md"}),
    ("GPU池化", {"wiki/shared/gpu/resource-layers.md"}),
    ("GPU性能评测", {"wiki/shared/gpu/performance-evaluation.md"}),
    ("CUDA_DEVICE_MEMORY_LIMIT", {GPU + "hami/hami-core.md"}),
    ("RDMA lkey rkey", {GPU + "networking/rdma-basics.md", "wiki/shared/gpu/memory-and-completion.md"}),
    ("NCCL GIN flush", {GPU + "communication/nccl-device-api.md", "wiki/shared/gpu/memory-and-completion.md"}),
    ("静态 SM 分区", {GPU + "sharing/mps.md"}),
    ("Confidence Sequences", {THESIS + "budget-and-evaluation/confidence-sequences.md"}),
    ("Sequential Halving", {THESIS + "budget-and-evaluation/almost-optimal-exploration.md", THESIS + "analysis/budget-allocation-and-statistics.md"}),
    ("Meta-Harness 完整历史", {THESIS + "harness-evolution/meta-harness.md", THESIS + "analysis/experiment-design-and-acceptance.md"}),
    ("LIBERO 恢复资格", {THESIS + "recovery-and-robustness/libero-recover.md", THESIS + "analysis/experiment-design-and-acceptance.md"}),
]


def evaluate(vault):
    pages = formal_pages(vault)
    con = sqlite3.connect(":memory:")
    con.execute("CREATE VIRTUAL TABLE baseline USING fts5(title,aliases,heading,text)")
    paths = {}
    for name, page in pages.items():
        for heading, text in chunks(page):
            cursor = con.execute("INSERT INTO baseline VALUES (?,?,?,?)", (page.title, " ".join(page.aliases), heading, text))
            paths[cursor.lastrowid] = name
    records = []
    for query, gold in CASES:
        missing = gold - set(pages)
        if missing:
            raise ValueError(f"评估原定页面缺失：{missing}")
        tokens = re.findall(r"[^\W_][\w-]*", query, re.UNICODE)
        match = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
        candidates = con.execute("SELECT rowid,bm25(baseline,8,10,4,1) FROM baseline WHERE baseline MATCH ? ORDER BY bm25(baseline,8,10,4,1)", (match,)).fetchall()
        baseline = list(dict.fromkeys(paths[row[0]] for row in candidates))[:5]
        current = [row["page_path"] for row in searcher.search(vault, query, limit=5)["results"]]
        records.append({"query": query, "expected_any": sorted(gold), "baseline_top5": baseline,
                        "optimized_top5": current, "baseline_hit": bool(gold & set(baseline)),
                        "optimized_hit": bool(gold & set(current))})
    con.close()
    return {"sample_size": len(records), "pages": len(pages), "metric": "hit@5 (any manually selected relevant page)",
            "baseline_hits": sum(row["baseline_hit"] for row in records),
            "optimized_hits": sum(row["optimized_hit"] for row in records),
            "limitations": "12 个手工选定的真实查询；同一语料与分块。只验证候选召回，不衡量语义正确性或证明普遍提升。", "cases": records}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.vault), ensure_ascii=False, indent=2))
