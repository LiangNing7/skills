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
