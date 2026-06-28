# 项目架构

MinerU 文献资产库 — 三层架构 + 四类接入点。

## 三层存储架构

### Canonical storage layer（唯一物理存储）

| 路径 | 内容 | 写入入口 |
|------|------|---------|
| `data/raw/<name>.pdf` | canonical 原始 PDF（副本） | `PaperRegistryService` |
| `data/papers/<paper_id>/paper.md` | MinerU 转换 + 清理后的 Markdown | ingest |
| `data/papers/<paper_id>/images/` | 嵌入图片 | ingest |
| `data/manifests/papers_manifest.json` | 文件状态账本（sha256/status/转换元数据） | **仅** `PaperManifest` / `IngestService` / `PaperRegistryService` |
| `data/catalog/library_index.json` | 物理路径注册表 + 领域 membership | **仅** `LibraryIndex` / `PaperRegistryService` |

### Semantic catalog layer

| 路径 | 内容 | 写入入口 |
|------|------|---------|
| `data/catalog/literature_catalog.json` | 全局文献理解目录（每篇一条） | `Catalog` / `PaperRegistryService` |

### Domain view layer

| 路径 | 内容 |
|------|------|
| `data/catalog/domains/<domain_id>/literature_catalog.json` | 领域视图（可跨篇重复索引） |
| `data/catalog/domains/<domain_id>/references.bib` | 领域 BibTeX |

领域视图由 `build_domain_library()` + `apply_domain_library()` 自动重建，不手动编辑。领域注册表由 `config/domains.json` 驱动；`src.library_index.VALID_DOMAINS`、`DOMAIN_LABELS`、`DOMAIN_REGISTRY` 是配置派生结果。

### Pending fetch layer

| 路径 | 内容 |
|------|------|
| `data/raw/<domain>/pending/<doi-slug>.pdf` | 刚下载待入库的 PDF |
| `data/raw/_inbox/pending/<name>.pdf` | 未选 domain 的上传/手动待处理 PDF |
| `data/raw/<domain>/pending/<doi-slug>.json` | 统一 sidecar v0.2（含 source_kind/access_mode/sha256/status 等） |

pending PDF **不自动入库**，必须经 `import_pending_pdf.py --apply` 完成正式注册。

## 模块职责边界

```
core storage/
  manifest.py         文件状态账本（PaperManifest）
  library_index.py    路径/领域注册表（LibraryIndex）
  catalog.py          文献理解目录（Catalog）
  library.py          全文/图片读取（PaperLibrary，只读）

ingest/
  converter.py        MinerU CLI 调用
  cleaner.py          MinerU 输出清理
  upload_service.py   上传 → 转换 → 清理
  watcher.py          文件变更检测 → 转换
  batch_convert.py    批量转换

services/
  paper_registry.py          事实源写入统一入口（PaperRegistryService）
  pending_import_service.py  pending → 查重 → 转换 → registry
  pdf_acquisition_service.py PDF 来源 → pending sidecar
  ingest_service.py          转换流程入口
  mineru_runtime.py          runner/GPU/API preflight

discovery/
  discovery/pipeline.py    多源搜索（OpenAlex / S2 / Crossref）
  discovery/query_expand.py 中英文术语扩展

fetch/
  fetch_pipeline.py         resolver chain 执行
  resolver_registry.py      resolver 注册表
  access_policy.py          访问策略控制
  resolvers/                各 PDF 来源实现
  fetch_*.py                旧式单模块 resolver（向后兼容）

writer/
  writer/                   综述写作工作区
  scripts/write_review.py   写作 CLI

api/
  server.py                 FastAPI 应用
  app.py                    Gradio 界面
```

## 写入规则

1. `scripts/*.py` 和 `src/server.py` **只能是适配层**：参数校验 → 调 service → 格式化输出。
2. **不得**在 adaptor 层直接 `manifest.upsert()` / `json.load` / `json.dump` 操作事实源文件。
3. 真正修改 manifest / catalog / library_index / domain views / bib 的逻辑集中在：
   - `PaperManifest` — 文件状态
   - `Catalog` — 语义目录
   - `LibraryIndex` — 注册表
   - `PaperRegistryService` — 组合操作（register / failed / delete / rename / update_domains）
   - `build_domain_library()` + `apply_domain_library()` — 领域视图重建
4. 新论文入库的完整流程：
   ```
   pending PDF → duplicate_detector → converter → cleaner → PaperRegistryService(catalog+manifest+index+domain views)
   ```

## 接入层

| 接入点 | 技术 | 职责 |
|--------|------|------|
| `scripts/*.py` | CLI (argparse) | 管理/批量操作 |
| `src/server.py` | FastAPI | REST API |
| `src/app.py` | Gradio | 交互式界面 |
| `docs/prompts/*` | prompt 模板 | AI 辅助操作 |

所有接入层共享同一套 service / store 层，不绕过。

## 日常入口

1. DOI/OA 获取：`fetch_pdf.py <doi> --domain <domain>` → `import_pending_pdf.py <pending.pdf> --apply`
2. 本地 PDF：`register_manual_pdf.py paper.pdf --domain <domain>` → `import_pending_pdf.py <pending.pdf> --apply`
3. Web 上传：当前仍直接转换，但必须经过 upload/ingest/manifest 状态机；新架构中不允许把 PDF 直接丢进 `data/raw/` 根目录当作正式入库。

> **watcher 与 unregistered_converted**：`start.bat` 默认只启动 Web 服务，不启动 watcher（`START_WATCHER=0`）。只有设置 `START_WATCHER=1` 或直接运行 `python watcher.py` 时，watcher 才会扫描 `data/raw/` 根目录自动转换 PDF。watcher 产物为 **unregistered_converted**（manifest 有记录，无 catalog 条目），不会直接进入正式 catalog / library_index / domain catalog / BibTeX。日常推荐正式入库流程仍是 `register_manual_pdf.py` → `import_pending_pdf.py --apply`。

## MinerU Runtime

`start.bat` 默认 CLI runner，不同时启动 `mineru-api`，避免 GPU 双模型 OOM。运行时状态由 `src/mineru_runtime.py` 提供，API 为 `GET /status/runtime`。HTTP `mineru-api` 上传 adapter 未默认启用；`api_url` 不会静默回退到 CLI，也不会假装转换成功。

## 非契约

- **不做**向量数据库 / RAG / embedding / ChromaDB
- **不调用**任何 LLM（所有 `/prompt/*` 只生成 prompt 文本）
- **不允许** pending PDF 自动变成 summarized 状态
- **不绕过** duplicate detection 入库
- **domain catalog 不是**唯一事实源（canonical 在 library_index + global catalog）
- **zip 中缺失 data/papers/** 只 warning，不 fail
