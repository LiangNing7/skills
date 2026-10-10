#!/usr/bin/env python3
"""向 Agent 提供受限的 OpenViking 检索与明确授权记忆工具。"""

import hashlib
import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from openviking_sdk import SyncHTTPClient

mcp = FastMCP("openviking-knowledge")


@contextmanager
def connected():
    client = SyncHTTPClient()
    client.initialize()
    try:
        yield client
    finally:
        client.close()


@mcp.tool()
def knowledge_find(query: str, target_uri: str = "viking://resources/wiki", limit: int = 5, image_path: str | None = None) -> dict:
    """定向检索正式 Wiki；图片输入仅使用本次用户指定的实际文件。"""
    if not target_uri.startswith("viking://resources/"):
        raise ValueError("知识检索目标需要是 Resource URI")
    with connected() as client:
        return client.find(query=query, target_uri=target_uri, limit=limit, image=image_path)


@mcp.tool()
def memory_find(query: str, limit: int = 5) -> dict:
    """读取本用户明确保存的经验与偏好，不产生新的 Memory。"""
    with connected() as client:
        user = client._async_client._user_id
        return client.find(query=query, target_uri=f"viking://user/{user}", limit=limit, options={"context_type": "memory"})


@mcp.tool()
def context_list(uri: str = "viking://resources/wiki") -> list:
    """列出指定上下文目录，帮助按需定位页面。"""
    with connected() as client:
        return client.ls(uri)


@mcp.tool()
def context_read(uri: str) -> dict:
    """读取命中正文；存在同步记录时返回本地源路径与新旧版本检查。"""
    with connected() as client:
        if client.stat(uri).get("isDir"):
            result = {"uri": uri, "content": client.overview(uri), "content_kind": "overview", "children": client.ls(uri)}
        else:
            result = {"uri": uri, "content": client.read(uri), "content_kind": "content"}
        account = client._async_client._account
    directory = Path(os.environ.get("KNOWLEDGE_SYNC_STATE_DIR", Path.home() / ".openviking/wiki-sync"))
    for path in directory.glob("*.json"):
        record = json.loads(path.read_text())
        prefix = record["target_uri"].rstrip("/") + "/"
        if record["account"] != account or not uri.startswith(prefix):
            continue
        mapping = record.get("remote_sources", {})
        relative = mapping.get(uri) or mapping.get(uri.rsplit("/", 1)[0]) or uri[len(prefix):]
        source = record["sources"].get(relative)
        if source:
            local = Path(source["source_path"])
            result["source_path"] = str(local)
            result["source_sha256"] = source["sha256"]
            result["model_identity"] = record["signature"]["model"]
            result["local_current"] = local.is_file() and hashlib.sha256(local.read_bytes()).hexdigest() == source["sha256"]
    return result


@mcp.tool()
def remember(messages: list[dict], authorized: bool = False) -> dict:
    """仅在用户明确要求保存所提交的经验/偏好时设置 authorized=true；返回后台任务供核对。"""
    if not authorized:
        raise ValueError("Memory 写入需要当前用户明确授权")
    if not messages or any(message.get("role") not in {"user", "assistant"} or not isinstance(message.get("content"), str) for message in messages):
        raise ValueError("提交需要是带 user/assistant 角色的精炼文字")
    with connected() as client:
        created = client.create_session()
        session = client.session(created["session_id"])
        for message in messages:
            session.add_message(message["role"], message["content"])
        committed = session.commit()
        return {"session_id": session.session_id, "submitted": True, "processing": committed}


@mcp.tool()
def task_status(task_id: str) -> dict:
    """检查同步或授权 Memory 的后台处理结果；提交不等于已完成。"""
    with connected() as client:
        return client.get_task(task_id) or {"status": "not_found"}


@mcp.tool()
def health() -> dict:
    """检查服务连接；不导入资料或写入 Memory。"""
    with connected() as client:
        return {"healthy": client.health()}


if __name__ == "__main__":
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("mcp.server.lowlevel.server").setLevel(logging.WARNING)
    mcp.run(transport="stdio")
