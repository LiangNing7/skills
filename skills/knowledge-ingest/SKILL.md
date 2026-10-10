---
name: knowledge-ingest
description: >-
  整理用户指定的 PDF、HTML、Markdown 或文本资料，保留不可变原件，直接阅读并生成带原文定位的摘要与知识页面；提取版按阅读需要生成。用户要求整理或吸收资料时使用。
---

# 整理原始资料

## 整理资料

读取知识库 AGENTS.md，检查现有相关内容与用户指定范围。新资料按真实归属选择英文路径，明确的归属直接处理，有实质歧义时询问。

1. 已在 raw/ 的原件只读；新增原件用独占写入保存，已有同名文件不得覆盖。保存原始名称和出处。多文件来源保持引用关系，遇到命名冲突先保持原件可回查。
   整理前通过相关入口、概念表和 knowledge-recall 的本地／语义检索定位已有页面，明确本批可能影响的结论。
2. 默认直接阅读原件，按当前研究问题定位相关章节。PDF 可用 scripts/read-pdf.py 在运行时读取指定页文字，关键图表、公式、数字及实验条件渲染原页并实际查看；Markdown、文本和 HTML 正文直接阅读。临时页面图像放仓库外缓存。
3. 用 Codex 当前的 GPT 模型编写中文摘要与知识页面，关键结论链接到原件具体页码，并注明表号、公式号或章节。PDF 页码从 1 开始，指文件实际页序。只读部分章节时记录审阅范围；未核对的内容保留状态。区分来源事实、用户陈述、分析与待验证事项。
4. 提取版按需使用：扫描页需要 OCR、任务需要结构化全文、转换结果需要反复复用，或用户明确要求时，再生成。已有提取版可辅助阅读，原件仍是依据。新提取版沿用来源路径并追加 .md，已有版只依原件纠错；转换完成不代表核对完成。
5. 资料整理指令授权有依据的 Wiki 更新。按 [维护验收](references/maintenance.md) 更新受影响正文和概念表，核对研究概览；新设计提案保留 proposed 状态，正式项目决策依据用户确认。
6. 更新实际相关入口、wiki/index.md 和 wiki/log.md，记录变更影响；批次刷新本地 BM25，运行相关范围的 wiki-lint 程序检查，核查重要语义变更，再执行正式 Wiki 的单向同步。服务不可用时报告待同步。

## 直接阅读 PDF

使用全局入口指定的 OpenViking 工具环境 Python：

```text
<python> <skill>/scripts/read-pdf.py --vault <vault> --source <raw-pdf> --pages 1-3,7
<python> <skill>/scripts/read-pdf.py --vault <vault> --source <raw-pdf> --pages 7 --render-dir <outside-vault-cache>
```

程序输出原件路径、哈希、页数、选中页的文字和 Obsidian 页码链接；未指定页范围时只显示前三页，便于先定位资料。它不创建提取版；--render-dir 只向仓库外写指定页面的缓存图像，需用图像查看工具核验。

来源链接示例（用实际存在的路径替换）：`[[raw/thesis/topic/paper.pdf#page=8|原件第 8 页，表 4]]`。HTML 可用原始来源 URL 和章节定位，Markdown 用原件标题定位。

## 按需生成提取版

需要持久保存提取版时可使用 scripts/extract-source.py，或按实际资料选择 OCR/转换工具。脚本按页提取文字，不能保证双栏、公式和表格结构正确；原件核验仍需完成。

```text
<python> <skill>/scripts/extract-source.py --vault <vault> --source <raw-file>
```

--correct-conversion 仅用于已获授权、依据原件的转换纠错。两个脚本都不编写摘要，也不调用生成模型改写原文。
