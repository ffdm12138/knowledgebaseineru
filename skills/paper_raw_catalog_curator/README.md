# Paper Raw Catalog Curator

Project skill for curating a single `data/paper_raw/<source_id>/` folder.

输入是 metadata JSON 与 MinerU Markdown；任务是生成用于快速筛选精读文献的 catalog（v1.1）
与只补空字段的 metadata patch。

- metadata 是书目信息事实源；catalog 是筛选事实源。
- 不得覆盖 metadata 非空字段；不得生成 `paper_number`；不得入库或改 `data/papers`。
- 详细规则见 `SKILL.md`；schema 见 `catalog_schema.json` / `metadata_patch_schema.json`；示例见 `examples/`。
