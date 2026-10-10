---
name: wiki-sync
description: >-
  将正式 Obsidian Wiki 单向同步至 OpenViking Resources，过滤草稿、模板及维护日志，保留来源和版本。正式页面授权更新后或用户要求同步时使用；资源副本不回写知识库。
---

# 同步正式知识索引

## 同步前检查

读取知识库 AGENTS.md 和当前 OpenViking 配置。确认同步源是实际的 wiki/，目标是专属 Resource URI。正式页面及其正文引用的本地附件一起打包，不能将整个 Vault 或用户原件批量上传。

## 执行同步

本目录 scripts/sync-wiki.py 负责过滤和一致性检查。使用全局入口指定的 OpenViking 工具环境 Python：

```text
<python> <skill>/scripts/sync-wiki.py --vault <vault>
```

--dry-run 只显示待同步清单，不调用服务；--force 用于已授权的索引重建。

- 只同步 active、confirmed、ready、reviewed 或未设置状态的正式 Markdown。排除 drafts/、templates/、log.md 与 proposed、draft、pending、merged 等状态。
- 相同源内容和模型身份可以跳过重复导入；变化时刷新同一专属目标，避免生成多份同名快照。
- 等待后台任务完成后才记录“已同步”。导入传空 reason，防止由同步触发自动 Memory。
- 记录每个来源的路径与 SHA-256、远端正文路径及模型身份，保存在仓库之外的 ~/.openviking/wiki-sync/。MCP context_read 据此回查本地版本；有图片的 Markdown 在服务端可能存入同名子目录。
- 出错保留之前成功的同步记录并报告待同步。本地正式知识保持权威。

## 边界

源码、草稿与原件不作为可编辑的检索副本。此流程不写 Memory，不修改技能，也不发布博客。
