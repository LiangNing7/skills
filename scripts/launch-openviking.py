#!/usr/bin/env python3
"""加载仓库外凭证并启动 OpenViking，保留 0.4.23 的多模态兼容适配。"""

import importlib.metadata
import json
import os
import sys
from functools import wraps
from pathlib import Path


def enable_multimodal_compatibility():
    # 0.4.23 的账户代理遗漏此能力标志；从真实账户模型获取，避免误放行文本模型。
    if importlib.metadata.version("openviking") != "0.4.23":
        return False
    from openviking.config.embedding import AccountBoundEmbedder
    from openviking.retrieve.hierarchical_retriever import HierarchicalRetriever

    original = HierarchicalRetriever.retrieve
    if getattr(original, "_knowledge_compatibility", False):
        return True

    @wraps(original)
    async def retrieve(self, query, ctx, *args, **kwargs):
        bound = self.embedder
        if query.image_query and isinstance(bound, AccountBoundEmbedder):
            resource = await bound.provider._resource_for(bound.account_id)
            bound.supports_multimodal = bool(resource.embedder.supports_multimodal)
        return await original(self, query, ctx, *args, **kwargs)

    retrieve._knowledge_compatibility = True
    HierarchicalRetriever.retrieve = retrieve
    return True


def main():
    private = Path.home() / ".openviking"
    for name, value in json.loads((private / "environment.json").read_text()).items():
        os.environ.setdefault(name, value)
    os.environ["OPENVIKING_CONFIG_FILE"] = str(private / "ov.conf")
    sys.argv = ["openviking-server", "--config", str(private / "ov.conf"), *sys.argv[1:]]
    adapted = enable_multimodal_compatibility()
    if adapted:
        print("Applied OpenViking 0.4.23 account multimodal compatibility.", flush=True)
    from openviking_cli.server_bootstrap import main as start

    start()


if __name__ == "__main__":
    main()
