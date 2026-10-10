# nex-skills

个人 / 项目共用的 skills 集合，通过 cc-switch 统一管理，可同时供 Claude Code 与 Codex 使用。

## 目录结构

```
skills/<skill-name>/
├── SKILL.md           # 共享内核：name + description + 正文（两个工具都读这里）
└── agents/
    └── openai.yaml    # Codex 专属元数据（Claude Code 忽略）
```

## 命名约定

- 项目专用 skill 以 `nex-` 为前缀，避免与其他 skill 重名（跨工具没有 plugin 命名空间，只能用名字前缀区分）。

## 安装（cc-switch）

在 cc-switch 的 Skills 管理中「添加仓库」：

- Owner: `LiangNing7`
- Name: `skills`
- Branch: `main`
- Subdirectory: `skills`

## 个人知识工作流

| Skill | 用途 |
| --- | --- |
| knowledge-recall | 结合中文／技术词 BM25 与 OpenViking 召回正式知识和已保存经验，回查来源与版本 |
| knowledge-ingest | 直接阅读原件，由 Codex 当前 GPT 整理带原文定位的摘要与知识；提取版按需生成 |
| wiki-capture | 明确要求保存时写入 Wiki，未采用提案保持草稿 |
| wiki-publish | 将已采用且授权保存的提案合并为正式知识 |
| wiki-sync | 将正式 Wiki 与引用图片单向同步至 OpenViking |
| wiki-lint | 默认只读，程序检查结构与来源，再由 LLM 审查矛盾、时效、缺口和引用相关性 |
| memory-curator | 明确要求记住时提交指定经验，并核对召回结果 |

知识库维护规则与使用说明位于 `/home/liangning/workspace/note/AGENTS.md` 和 `workflow.md`。
原件严格只读；提取版只依据原件纠错；普通对话不会自动保存 Wiki 或 Memory。

默认从原件直接生成 Wiki 摘要与分析；PDF 的关键结论链接到实际页码并核对原页。`knowledge-ingest/scripts/read-pdf.py` 输出指定页文字及来源链接，可将关键页渲染到仓库外缓存，无需生成持久的全文 Markdown。需要 OCR 或结构化全文时再使用提取/转换辅助。

### 本机分发

知识工作流技能先通过 cc-switch 本地记录注册，安装副本位于 `~/.cc-switch/skills/`，Claude Code 与 Codex 使用符号链接。源码以本 Git 工作树为准。本地分发不提交或推送 Git，也不假定远端已有这些文件。

关闭 cc-switch 后执行：

```bash
/home/liangning/.local/share/uv/tools/openviking/bin/python scripts/deploy-knowledge-workflow.py
```

脚本同步七个技能、全局知识入口和 MCP 配置，备份数据库与受影响配置，保留其他技能和原有全局规则。更新后重新打开 cc-switch，并启动新的 Agent 会话。

本地 BM25 位于 knowledge-recall/scripts/wiki-search.py，索引在仓库外缓存；与 wiki-lint 共用正式页面筛选和完整 YAML 解析。内容哈希识别变化／删除，构建失败保留旧索引。健康巡检只输出报告；明确要求修复才修改内容。

### OpenViking 与验证

当前工具环境为 OpenViking 0.4.23，使用 DeepSeek 生成内部摘要和授权 Memory，百炼 `qwen3-vl-embedding` 生成 1024 维多模态向量。Codex 知识写作仍使用其当前 GPT 模型。

`scripts/launch-openviking.py` 读取仓库外的私有配置启动服务，并适配 0.4.23 账户代理缺失的多模态能力标志；没有直接修改已安装依赖。MCP 入口位于 `knowledge-recall/scripts/mcp-proxy.py`，仅提交明确授权的记忆，不启用会话采集或提交钩子。

```bash
/home/liangning/.local/share/uv/tools/openviking/bin/python tests/test-knowledge-workflow.py
/home/liangning/.local/share/uv/tools/openviking/bin/python tests/test-wiki-maintenance.py
/home/liangning/.local/share/uv/tools/openviking/bin/python tests/test-knowledge-workflow.py --live
```

基础验证使用本地临时资料；真实验证使用独立账户检查导入、文本与图片检索、草稿过滤、版本回查及显式 Memory 写入，并清理测试账户。真实验证会调用模型 API，需要仓库外的管理员连接配置。
