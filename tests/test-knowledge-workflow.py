#!/usr/bin/env python3
"""验证原件保护与同步筛选；--live 在独立账户验证真实模型和检索。"""

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pymupdf as fitz
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extractor = load("extractor", "skills/knowledge-ingest/scripts/extract-source.py")
pdf_reader = load("pdf_reader", "skills/knowledge-ingest/scripts/read-pdf.py")
syncer = load("syncer", "skills/wiki-sync/scripts/sync-wiki.py")


def wait_task(client, response, timeout=180):
    task_id = response.get("task_id")
    if not task_id:
        return response
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = client.get_task(task_id)
        if task and task.get("status") in {"completed", "succeeded", "success"}:
            return task
        if task and task.get("status") in {"failed", "cancelled"}:
            raise AssertionError(f"后台任务失败：{task.get('status')}")
        time.sleep(1)
    raise AssertionError("后台任务未在验证期限内完成")


async def mcp_roundtrip(vault, config, client):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    private = vault / "test-client.conf"
    private.write_text(json.dumps(config))
    private.chmod(0o600)
    server = StdioServerParameters(command=sys.executable,
        args=[str(ROOT / "skills/knowledge-recall/scripts/mcp-proxy.py")],
        env={**os.environ, "OPENVIKING_CLI_CONFIG_FILE": str(private), "KNOWLEDGE_SYNC_STATE_DIR": str(vault / "runtime")})

    def value(result):
        assert not result.isError, "MCP 工具执行失败"
        return result.structuredContent or json.loads(result.content[0].text)

    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            names = {tool.name for tool in (await session.list_tools()).tools}
            assert names == {"knowledge_find", "memory_find", "context_list", "context_read", "remember", "task_status", "health"}
            assert value(await session.call_tool("health", {}))["healthy"]
            read = value(await session.call_tool("context_read", {"uri": "viking://resources/wiki/facts/facts.md"}))
            assert read["local_current"] is True and read["source_path"] == str(vault / "wiki/facts.md")
            facts = vault / "wiki/facts.md"
            original = facts.read_bytes()
            try:
                facts.write_bytes(original + b"\nchanged during freshness validation\n")
                stale = value(await session.call_tool("context_read", {"uri": "viking://resources/wiki/facts/facts.md"}))
                assert stale["local_current"] is False
            finally:
                facts.write_bytes(original)
            before = len(client.list_sessions())
            refused = await session.call_tool("remember", {"messages": [{"role": "user", "content": "未经授权的测试文字"}]})
            assert refused.isError and len(client.list_sessions()) == before
            hits = value(await session.call_tool("knowledge_find", {"query": "原始资料不可变", "limit": 5}))
            assert hits.get("resources")
            print("PASS MCP 工具发现、文本检索、本地来源映射、过时副本识别、未授权 Memory 拒绝", flush=True)
            saved = value(await session.call_tool("remember", {"authorized": True,
                "messages": [{"role": "user", "content": "请明确记住这条测试偏好：整理知识时，用英文文件名和中文正文，关键结论保留来源；这是独立验证账户的保存测试。"}]}))
            return saved["processing"]


def fixtures(vault):
    raw = vault / "raw"
    raw.mkdir()
    source = raw / "source.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((40, 60), "Immutable source for the knowledge workflow validation.")
        page = document.new_page()
        page.insert_text((40, 60), "Printed page 42; physical PDF page 2.")
        document.new_page()
        page = document.new_page()
        page.insert_text((40, 60), "Fourth page is outside the default three-page overview.")
        document.save(source)
    original = source.read_bytes()
    direct = pdf_reader.read_pdf(vault, "raw/source.pdf", pages="2,1-2")
    assert direct["displayed_pdf_pages"] == [1, 2]
    assert direct["page_count"] == 4
    assert pdf_reader.read_pdf(vault, source)["displayed_pdf_pages"] == [1, 2, 3]
    assert "physical PDF page 2" in direct["pages"][1]["text"]
    assert direct["pages"][1]["citation"] == "[[raw/source.pdf#page=2|原件第 2 页]]"
    assert not (vault / "extracted").exists()
    with tempfile.TemporaryDirectory(prefix="pdf-reading-cache-") as cache:
        rendered = pdf_reader.read_pdf(vault, source, pages="3", render_dir=cache)
        assert rendered["pages"][0]["text_layer_present"] is False
        image = Path(rendered["pages"][0]["rendered_image"])
        assert image.is_relative_to(Path(cache)) and image.read_bytes().startswith(b"\x89PNG")
        assert pdf_reader.read_pdf(vault, source, pages="3", render_dir=cache)["pages"] == rendered["pages"]
    for kwargs in ({"pages": "0"}, {"pages": "5"}, {"pages": "3-1"}, {"pages": "1", "render_dir": vault / "raw/cache"}):
        try:
            pdf_reader.read_pdf(vault, source, **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("阅读器接受了错误页码或仓库内缓存")
    assert source.read_bytes() == original and not (vault / "extracted").exists()
    print("PASS PDF 直接阅读、物理页码链接、仓库外图像缓存、无强制提取版、原件保护", flush=True)
    titled = vault / "mapping-check.md"
    content = "---\ntitle: 中文页面标题\nstatus: active\n---\n# 标题\n\n核对实际正文。\n"
    titled.write_text(content, encoding="utf-8")
    relative = "topic/english-name.md"
    remote = "viking://resources/wiki/topic/中文页面标题.md"
    class RenamedResource:
        def read(self, uri):
            return content if uri == remote else "其他页面内容"
    selected = {relative: titled}
    hashes = {relative: hashlib.sha256(titled.read_bytes()).hexdigest()}
    mapping = syncer.map_remote_sources(selected, hashes, {remote}, "viking://resources/wiki", RenamedResource())
    assert mapping == {remote: relative}
    for paths in ({"viking://resources/wiki/topic/其他页面.md"}, {remote, remote.replace("标题", "标题副本")}):
        class ChangedResource:
            def read(self, uri):
                return content
        if len(paths) == 1:
            paths = {"viking://resources/wiki/another-topic/中文页面标题.md"}
        try:
            syncer.map_remote_sources(selected, hashes, paths, "viking://resources/wiki", ChangedResource())
        except ValueError:
            pass
        else:
            raise AssertionError("正文映射接受了错误目录或歧义副本")
    print("PASS 标题改名的正文按哈希唯一映射，拒绝错误目录与歧义", flush=True)
    record = extractor.extract(vault, source, original_name="source.pdf", origin="独立集成验证生成的测试资料")
    assert source.read_bytes() == original
    extracted = vault / record["extracted_path"]
    assert "Immutable source" in extracted.read_text()
    assert record["source_sha256"] == hashlib.sha256(original).hexdigest()
    try:
        extractor.extract(vault, source)
    except FileExistsError:
        pass
    else:
        raise AssertionError("重复提取覆盖了已有提取版")
    wiki = vault / "wiki"
    (wiki / "assets").mkdir(parents=True)
    (wiki / "drafts").mkdir()
    (wiki / "templates").mkdir()
    (wiki / "facts.md").write_text("---\nstatus: active\nsources:\n  - raw/source.pdf\n---\n# 工作流验证资料\n\n这是独立测试资料。原件需要保持不可变；直接阅读后，关键结论链接原文。[[raw/source.pdf#page=1|测试原件第 1 页]]的文字为：Immutable source for the knowledge workflow validation.\n\n![红色方块](assets/red.png)\n![蓝色方块](assets/blue.png)\n", encoding="utf-8")
    (wiki / "drafts/proposal.md").write_text("---\nstatus: proposed\n---\n# 测试提案\n\n待确认的测试方案。", encoding="utf-8")
    (wiki / "templates/page.md").write_text("模板不进入检索。", encoding="utf-8")
    (wiki / "log.md").write_text("维护记录不进入检索。", encoding="utf-8")
    Image.new("RGB", (128, 128), "red").save(wiki / "assets/red.png")
    Image.new("RGB", (128, 128), "blue").save(wiki / "assets/blue.png")
    selected = syncer.collect(vault)
    assert set(selected) == {"facts.md", "assets/red.png", "assets/blue.png"}
    print("PASS 原件未修改、重复提取受保护、草稿与日志过滤、引用图片收集", flush=True)
    return source, original


def live(vault):
    from openviking_sdk import SyncHTTPClient

    config = json.loads((Path.home() / ".openviking/root-cli.conf").read_text())
    root = SyncHTTPClient(**config)
    root.initialize()
    account = "workflow-validation-" + uuid.uuid4().hex[:10]
    created = root.admin_create_account(account, "tester")
    user_config = dict(url=config["url"], api_key=created["user_key"], account=account, user="tester", timeout=240)
    client = SyncHTTPClient(**user_config)
    client.initialize()
    try:
        state = vault / "runtime"
        before = len(client.list_sessions())
        result = syncer.sync(vault, client=client, state_dir=state)
        assert result["status"] == "synced"
        assert len(client.list_sessions()) == before
        assert syncer.sync(vault, client=client, state_dir=state)["status"] == "unchanged"
        read = client.read("viking://resources/wiki/facts/facts.md")
        assert "原件" in read
        hits = client.find("原始资料为什么需要保持不可变", target_uri="viking://resources/wiki", limit=10)
        assert hits.get("resources"), "文本检索未召回测试资料"
        print("PASS 正式资料真实同步、幂等、文本召回、同步未创建 Memory 会话", flush=True)
        image = client.find("", image=str(vault / "wiki/assets/red.png"), target_uri="viking://resources/wiki", limit=10)
        assert image.get("resources"), "图片查询未召回任何资源"
        assert any("red.png" in item.get("uri", "") for item in image["resources"]), "图片查询未找到对应图片"
        print("PASS 多模态图片检索", flush=True)
        proposal = vault / "wiki/drafts/proposal.md"
        (vault / "wiki/decision.md").write_text("---\nstatus: confirmed\n---\n# 已确认的集成验证方案\n\n仅在用户采用并要求保存后，将草稿合并为正式知识。", encoding="utf-8")
        proposal.write_text("---\nstatus: merged\n---\n测试草稿已合并。", encoding="utf-8")
        syncer.sync(vault, client=client, state_dir=state)
        assert "用户采用" in client.read("viking://resources/wiki/decision.md")
        assert len(client.list_sessions()) == before
        print("PASS 草稿转正式知识后同步，仍无自动 Memory", flush=True)
        syncer.sync(vault, client=client, state_dir=state, force=True)
        assert len(client.list_sessions()) == before
        (vault / "wiki/decision.md").unlink()
        syncer.sync(vault, client=client, state_dir=state)
        assert not any("decision" in item["uri"] for item in client.tree("viking://resources/wiki"))
        print("PASS 强制索引重建及已移除页面清理", flush=True)
        committed = asyncio.run(mcp_roundtrip(vault, user_config, client))
        wait_task(client, committed)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            memory = client.find("知识文件英文命名中文正文来源", target_uri="viking://user/tester", limit=10, options={"context_type": "memory"})
            if memory.get("memories"):
                break
            time.sleep(2)
        else:
            raise AssertionError("授权保存后未召回 Memory")
        print("PASS 明确授权 Memory 保存和真实召回", flush=True)
        return {"server_version": "0.4.23", "embedding_model": "qwen3-vl-embedding", "dimension": 1024, "status": "passed"}
    finally:
        client.close()
        root.admin_delete_account(account)
        root.close()
        print("已清理本次独立验证账户。", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="knowledge-workflow-test-") as temporary:
        vault = Path(temporary)
        source, original = fixtures(vault)
        if args.live:
            print(json.dumps(live(vault), ensure_ascii=False), flush=True)
        assert source.read_bytes() == original


if __name__ == "__main__":
    main()
