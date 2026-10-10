#!/usr/bin/env python3
"""将正式 Wiki 及引用图片单向同步至专属 OpenViking Resource。"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "knowledge-recall/scripts"))
from wiki_core import formal_pages, frontmatter
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metadata(path):
    return frontmatter(path.read_text(encoding="utf-8"))[0]


def collect(vault):
    vault = Path(vault).resolve()
    wiki = vault / "wiki"
    if wiki.is_symlink():
        raise ValueError("wiki 根目录不能是符号链接")
    files = {}
    if not wiki.exists():
        return files
    for page in formal_pages(vault).values():
        path = page.path
        relative = path.relative_to(wiki)
        files[relative.as_posix()] = path
        text = page.raw
        references = re.findall(r"!\[\[([^\]]+)\]\]", text)
        references += re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
        for reference in references:
            reference = unquote(reference.split("|", 1)[0].split("#", 1)[0].strip("<> "))
            if "://" in reference:
                continue
            candidates = [vault / reference, path.parent / reference]
            if "/" not in reference:
                candidates += list(wiki.rglob(reference))
            matches = {p.resolve() for p in candidates if p.is_file()}
            if not matches:
                if Path(reference).suffix.lower() in IMAGE_SUFFIXES:
                    raise FileNotFoundError(f"正文引用图片缺失：{reference}")
                continue
            if len(matches) > 1:
                raise ValueError(f"正文附件存在路径歧义：{reference}")
            asset = matches.pop()
            if not asset.is_relative_to(wiki.resolve()):
                raise ValueError("同步附件需先依据来源复制到 wiki 中，原件与提取版保持本地")
            if asset.suffix.lower() in IMAGE_SUFFIXES:
                files[asset.relative_to(wiki).as_posix()] = asset
    return files


def identity():
    config = Path.home() / ".openviking/ov.conf"
    if not config.is_file():
        return {"configured": False}
    settings = json.loads(config.read_text())
    dense = settings["embedding"]["dense"]
    model = {"embedding": {key: dense.get(key) for key in ("provider", "model", "dimension", "input")},
             "summary": {key: settings["vlm"].get(key) for key in ("provider", "model")}}
    codex = Path.home() / ".codex/config.toml"
    if codex.exists():
        model["codex_configured_model"] = tomllib.loads(codex.read_text()).get("model")
    return model


def check_completed(result):
    if result.get("errors") or result.get("meta", {}).get("failed_files"):
        raise ValueError("导入存在错误，未标记同步成功")
    if result.get("status") not in {None, "success", "completed", "ok"}:
        raise ValueError(f"服务处理状态未成功：{result.get('status')}")
    for queue in result.get("queue_status", {}).values():
        if isinstance(queue, dict) and (queue.get("error_count", 0) or queue.get("errors")):
            raise ValueError("摘要或向量处理失败，未标记同步成功")


def map_remote_sources(files, hashes, remote_files, target, client):
    """依据实际存储路径映射；标题改名的正文必须按内容哈希核对。"""
    prefix = target.rstrip("/") + "/"
    remote_hashes = {}
    mapping = {}
    for relative, path in files.items():
        direct = prefix + relative
        nested = prefix + (Path(relative).parent / path.stem / path.name).as_posix()
        if direct in remote_files:
            mapping[direct] = relative
        elif path.suffix == ".md" and nested in remote_files:
            mapping[nested] = relative
            mapping[nested.rsplit("/", 1)[0]] = relative
        elif path.suffix == ".md":
            parent = Path(relative).parent
            matches = []
            for uri in sorted(remote_files):
                if not uri.startswith(prefix) or not uri.endswith(".md"):
                    continue
                remote_path = Path(uri[len(prefix):])
                if remote_path.parent != parent:
                    continue
                if uri not in remote_hashes:
                    remote_hashes[uri] = hashlib.sha256(client.read(uri).encode("utf-8")).hexdigest()
                if remote_hashes[uri] == hashes[relative]:
                    matches.append(uri)
            if len(matches) != 1:
                raise ValueError(f"远端正文需要唯一的内容核验映射：{relative}；匹配数 {len(matches)}")
            if matches[0] in mapping and mapping[matches[0]] != relative:
                raise ValueError(f"不同本地页面映射到了同一远端正文：{relative}")
            mapping[matches[0]] = relative
        else:
            raise ValueError(f"导入后未找到对应附件：{relative}")
    return mapping


def sync(vault, target="viking://resources/wiki", client=None, dry_run=False, force=False, state_dir=None):
    if not target.startswith("viking://resources/") or any(part in {".", ".."} for part in target[9:].split("/")):
        raise ValueError("目标必须是专属 Resource 子目录")
    vault = Path(vault).resolve()
    files = collect(vault)
    hashes = {name: sha(path) for name, path in files.items()}
    result = {"target_uri": target, "files": sorted(files), "excluded_drafts": True, "memory_reason": ""}
    if dry_run:
        return {**result, "status": "dry-run"}
    from openviking_sdk import SyncHTTPClient
    from openviking_sdk.options import AddResourceOptions
    from openviking_sdk.errors import NotFoundError

    owns_client = client is None
    client = client or SyncHTTPClient()
    if owns_client:
        client.initialize()
    try:
        remote_sources = {}
        account = client._async_client._account
        fingerprint = hashlib.sha256((str(vault) + "\0" + account + "\0" + target).encode()).hexdigest()
        directory = Path(state_dir or Path.home() / ".openviking/wiki-sync")
        state_path = directory / (fingerprint + ".json")
        previous = json.loads(state_path.read_text()) if state_path.exists() else None
        signature = {"hashes": hashes, "model": identity()}
        exists = True
        try:
            client.stat(target)
        except NotFoundError:
            exists = False
        if exists and previous is None:
            raise ValueError("目标已有资源且没有本流程的来源记录，请使用独立目标")
        if previous and previous["signature"] == signature and not force and (exists or not files):
            return {**result, "status": "unchanged"}
        if not files:
            if exists and previous:
                client.rm(target, recursive=True)
            status = "empty"
        else:
            with tempfile.TemporaryDirectory(prefix="wiki-sync-") as temporary:
                snapshot = Path(temporary) / "wiki"
                snapshot.mkdir()
                for relative, source in files.items():
                    destination = snapshot / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
                options = AddResourceOptions(reason="", args={"parse_mode": "no_split"})
                imported = client.add_resource(str(snapshot), to=target, wait=True, timeout=180, options=options)
                check_completed(imported)
                if imported.get("root_uri") and imported["root_uri"] != target:
                    raise ValueError("服务返回了不同目标，不能标记已同步")
                if force or (previous and previous["signature"]["model"] != signature["model"]):
                    check_completed(client.reindex(target, mode="semantic_and_vectors", wait=True, recursive=True, force=True))
                remote_files = {item["uri"] for item in client.tree(target, level_limit=100, node_limit=100000) if not item.get("isDir")}
                remote_sources = map_remote_sources(files, hashes, remote_files, target, client)
                for name, path in files.items():
                    if sha(path) != hashes[name]:
                        raise ValueError("同步期间本地页面变化，请重新同步；未更新成功记录")
            status = "synced"
        directory.mkdir(parents=True, exist_ok=True)
        record = {
            "vault_root": str(vault), "account": account, "target_uri": target,
            "signature": signature,
            "remote_sources": remote_sources,
            "sources": {name: {"source_path": str(path), "sha256": hashes[name]} for name, path in files.items()},
        }
        temporary_state = state_path.with_suffix(".tmp")
        temporary_state.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        os.chmod(temporary_state, 0o600)
        os.replace(temporary_state, state_path)
        return {**result, "status": status}
    finally:
        if owns_client:
            client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True)
    parser.add_argument("--target", default="viking://resources/wiki")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(json.dumps(sync(args.vault, args.target, dry_run=args.dry_run, force=args.force), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
