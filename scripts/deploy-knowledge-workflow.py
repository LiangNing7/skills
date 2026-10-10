#!/usr/bin/env python3
"""将知识工作流技能注册到 cc-switch，并分发至 Claude Code 和 Codex。"""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
NAMES = ("knowledge-recall", "knowledge-ingest", "wiki-capture", "wiki-publish", "wiki-sync", "wiki-lint", "memory-curator")
PYTHON = HOME / ".local/share/uv/tools/openviking/bin/python"
VAULT = HOME / "workspace/note"
START = "<!-- knowledge-workflow:start -->"
END = "<!-- knowledge-workflow:end -->"


def directory_hash(directory):
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if path.is_file() and not any(part.startswith(".") or part == "__pycache__" for part in relative.parts) and path.suffix != ".pyc":
            digest.update(relative.as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".knowledge-workflow.tmp")
    with temporary.open("w", encoding="utf-8") as output:
        os.chmod(temporary, 0o600)
        output.write(text)
    os.replace(temporary, path)


def prompt_block():
    return f"""{START}
## 个人知识工作流

- 知识主仓库：`{VAULT}`。涉及知识任务时先读其中的 `AGENTS.md`，按已有入口定向读取。
- Obsidian 原件、提取版、正式 Wiki 与博客在该仓库维护；知识整理与写作默认由 Codex 当前使用的 GPT 完成。Claude Code 可以召回知识和使用共享 Skills；用户指定 Claude 执行时遵从当前指令。
- 资料整理默认直接阅读原件，保存带来源定位的 Wiki 摘要与分析；PDF 的关键结论链接原件 #page=N，并实际核对重要图表与公式。提取版仅在 OCR、结构化全文或反复复用等需要时生成，已有提取版可辅助定位。
- 项目、论文及历史经验任务主动使用 `knowledge-recall`；结合主题入口／概念表、本地中文与技术词 BM25、OpenViking MCP 定向召回，打开正文核对版本与来源；不可用时回退本地入口和 rg。
- 普通问答和一般认可不授权保存。资料整理、明确保存 Wiki、采用并保存提案分别使用 `knowledge-ingest`、`wiki-capture`、`wiki-publish`。原件严格只读，提取版仅依原件纠错；未采用提案保持 proposed。
- 正式 Wiki 更新后使用 `wiki-sync` 单向更新检索副本；原件、提取版、草稿、日志和博客不批量导入。同步使用空 reason，不触发自动 Memory。
- 新资料更新相关概念表和研究概览，记录受影响结论及待核实项；正式内容批次刷新 BM25，再检查变更范围。健康巡检使用 `wiki-lint`，默认只读，结构通过不代表语义核验完成。
- Memory 仅由用户明确要求记住时使用 `memory-curator` 提交选定内容并验证召回。自动发现技能不授权记忆写入；不启用自动会话采集或提交钩子。
- Skill 修改源为 `{ROOT}`；cc-switch 管理安装副本并同步给两个客户端。不要直接编辑已安装副本。
- 技能脚本运行环境：`{PYTHON}`。MCP 连接本机 OpenViking；服务内部 DeepSeek 和百炼 Embedding 设置不改变 Codex 自身的 GPT 模型。
{END}"""


def merge_prompt(existing):
    if existing.count(START) != existing.count(END) or existing.count(START) > 1:
        raise ValueError("全局规则的维护标记不完整，请先核对")
    existing = re.sub(re.escape(START) + r".*?" + re.escape(END), "", existing, flags=re.S).rstrip()
    return (existing + "\n\n" if existing else "") + prompt_block() + "\n"


def main():
    if subprocess.run(["pgrep", "-x", "cc-switch"], stdout=subprocess.DEVNULL).returncode == 0:
        raise SystemExit("请先关闭 cc-switch，避免与本地注册同时写入数据库")
    if not PYTHON.is_file() or not (VAULT / "AGENTS.md").is_file():
        raise SystemExit("OpenViking 工具环境或知识仓库尚未准备好")
    central = HOME / ".cc-switch/skills"
    db_path = HOME / ".cc-switch/cc-switch.db"
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    packages = {}
    for name in NAMES:
        source, destination = ROOT / "skills" / name, central / name
        props = yaml.safe_load((source / "SKILL.md").read_text().split("---", 2)[1])
        row = connection.execute("SELECT * FROM skills WHERE directory=?", (name,)).fetchone()
        if row and row["id"] != "local:" + name:
            raise ValueError(f"发现其他来源的同名技能：{name}")
        if destination.exists() and (not row or row["content_hash"] != directory_hash(destination)):
            raise ValueError(f"已安装副本存在未同步改动或不受此流程管理：{name}")
        for app in (".claude", ".codex"):
            link = HOME / app / "skills" / name
            if (link.exists() or link.is_symlink()) and (not link.is_symlink() or link.resolve() != destination.resolve()):
                raise ValueError(f"客户端中存在其他同名目录：{link}")
        packages[name] = (source, destination, props, row)

    proxy = central / "knowledge-recall/scripts/mcp-proxy.py"
    server = {"type": "stdio", "command": str(PYTHON), "args": [str(proxy)]}
    previous_mcp = connection.execute("SELECT server_config FROM mcp_servers WHERE id='openviking'").fetchone()
    if previous_mcp and json.loads(previous_mcp[0]) != server:
        raise ValueError("cc-switch 中的 openviking 条目由其他配置管理")
    codex_path = HOME / ".codex/config.toml"
    codex_text = codex_path.read_text()
    codex_data = tomllib.loads(codex_text)
    codex_server = codex_data.get("mcp_servers", {}).get("openviking")
    if codex_server:
        if codex_server.get("command") != server["command"] or codex_server.get("args") != server["args"]:
            raise ValueError("Codex 中存在其他 openviking 配置")
    else:
        codex_text += '\n[mcp_servers.openviking]\ncommand = ' + json.dumps(server["command"]) + '\nargs = ' + json.dumps(server["args"]) + '\nstartup_timeout_sec = 30\ntool_timeout_sec = 240\n'
    tomllib.loads(codex_text)
    claude_path = HOME / ".claude.json"
    claude_data = json.loads(claude_path.read_text()) if claude_path.exists() else {}
    previous_native = claude_data.setdefault("mcpServers", {}).get("openviking")
    if previous_native and previous_native != server:
        raise ValueError("Claude Code 中存在其他 openviking 配置")
    claude_data["mcpServers"]["openviking"] = server

    prompts = {}
    for app, relative in (("claude", ".claude/CLAUDE.md"), ("codex", ".codex/AGENTS.md")):
        path = HOME / relative
        rows = connection.execute("SELECT * FROM prompts WHERE app_type=? AND enabled=1", (app,)).fetchall()
        if len(rows) > 1:
            raise ValueError(f"发现多个活动全局规则：{app}")
        row = rows[0] if rows else None
        text = path.read_text() if path.exists() else (row["content"] if row else "")
        if row and path.exists() and text != row["content"]:
            raise ValueError(f"客户端与 cc-switch 全局规则不一致：{app}")
        prompts[app] = (path, merge_prompt(text), row)

    timestamp = int(time.time())
    backup = HOME / ".cc-switch/backups" / ("knowledge-workflow-" + str(time.time_ns()))
    backup.mkdir(parents=True, mode=0o700)
    with sqlite3.connect(backup / "cc-switch.db") as destination:
        connection.backup(destination)
    os.chmod(backup / "cc-switch.db", 0o600)
    for path in (codex_path, claude_path, *(item[0] for item in prompts.values())):
        if path.exists():
            saved = backup / path.relative_to(HOME)
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, saved)
            os.chmod(saved, 0o600)
    for name, (_, destination, _, _) in packages.items():
        if destination.exists():
            shutil.copytree(destination, backup / "skills" / name)

    with connection:
        for name, (source, destination, props, row) in packages.items():
            staged = central / (".knowledge-workflow-" + name)
            if staged.exists():
                raise ValueError(f"上次分发暂存未清理：{staged}")
            shutil.copytree(source, staged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            if destination.exists():
                shutil.rmtree(destination)
            staged.rename(destination)
            connection.execute("""INSERT INTO skills
                (id,name,description,directory,repo_owner,repo_name,repo_branch,readme_url,enabled_claude,enabled_codex,installed_at,content_hash,updated_at)
                VALUES (?,?,?,?,NULL,NULL,NULL,NULL,1,1,?,?,0)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,description=excluded.description,
                enabled_claude=1,enabled_codex=1,content_hash=excluded.content_hash""",
                ("local:" + name, props["name"], props["description"], name, timestamp, directory_hash(destination)))
            for app in (".claude", ".codex"):
                link = HOME / app / "skills" / name
                link.parent.mkdir(parents=True, exist_ok=True)
                if not link.is_symlink():
                    link.symlink_to(destination, target_is_directory=True)
        for app, (path, content, row) in prompts.items():
            if row:
                connection.execute("UPDATE prompts SET content=?,updated_at=? WHERE id=? AND app_type=?", (content, timestamp, row["id"], app))
            else:
                connection.execute("INSERT INTO prompts(id,app_type,name,content,description,enabled,created_at,updated_at) VALUES (?,?,?,?,?,1,?,?)",
                    ("knowledge-workflow-global", app, "个人知识工作流", content, "知识库入口与保存边界", timestamp, timestamp))
            atomic_text(path, content)
        connection.execute("""INSERT INTO mcp_servers(id,name,server_config,description,tags,enabled_claude,enabled_codex)
            VALUES ('openviking','OpenViking Knowledge',?,'正式 Wiki 检索与明确授权 Memory','[]',1,1)
            ON CONFLICT(id) DO UPDATE SET server_config=excluded.server_config,enabled_claude=1,enabled_codex=1""", (json.dumps(server),))
        atomic_text(codex_path, codex_text)
        atomic_text(claude_path, json.dumps(claude_data, ensure_ascii=False, indent=2) + "\n")
    connection.close()
    print(json.dumps({"skills": list(NAMES), "clients": ["claude", "codex"], "mcp": "openviking", "backup": str(backup)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
