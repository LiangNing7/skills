# 本地关键词检索与语义召回

先从任务相关入口定位范围。已知准确路径时直接阅读；技术名称、错误信息、API、中文概念适合本地 BM25，跨措辞问题可并用 OpenViking。两种结果都是候选，关键结论回查本地正文与原件。

```text
<python> <skill>/scripts/wiki-search.py --vault <vault> stats
<python> <skill>/scripts/wiki-search.py --vault <vault> build
<python> <skill>/scripts/wiki-search.py --vault <vault> search "显存隔离" --scope wiki/projects/example --limit 5
```

脚本使用既有 PyYAML 与 SQLite FTS5：中文连续文本按重叠双字组，英文／API 保留完整词项并增加分隔词项；NFKC 和大小写归一化。按标题、别名、标题路径和正文加权，并结合词项覆盖与完整短语匹配排序。代码内容可被检索，按章节分块，同页结果去重。分数只用于本次候选排序，不是可信度。

仅索引正式 Wiki，筛选与 wiki-sync 使用同一页面解析模块；排除 drafts、templates、隐藏目录、log.md 和非正式状态。不索引 raw、extracted、blog。缓存位于 `${XDG_CACHE_HOME:-~/.cache}/knowledge-workflow/<vault-id>/`，`--cache-dir` 也必须在仓库外。

新旧判断比较路径集合与完整内容 SHA-256，包含删除、改名和状态变化。search 默认在缺失／过时时刷新；`--no-refresh` 则明确报错。构建按变更页更新暂存数据库，成功后原子替换；失败保留旧库。索引故障时用入口、rg 或 MCP 继续，不能把旧缓存当作当前证据。

返回 page_path、heading_path、source_sha256、sources、snippet 与评分。打开正文，必要时核对 source_sha256；来源数组保留完整路径。摘要片段不能代替正文，缓存和检索评分不能作引用依据。

新增资料前检索既有概念避免重复；正式 Wiki 更新后批次刷新一次。别名只补充实际术语名称，不凭空给无关页面添加别名来提高召回。
