# 项目核心契约（PROJECT_CONTRACT）

> 本文件是本项目**最完整的核心契约**，定义不可删除、不可弱化、不可重构掉的设计原则。
> 任何代码代理（Codex / Claude Code / 其他）在修改本仓库前**必须先完整阅读本文件**。
> `AGENTS.md` 与 `CLAUDE.md` 是本文件的摘要与入口，内容必须与本文件保持同源。

## 项目定位

一个本地 **文献资产库 + AI 摘要目录 + 按需全文阅读 + 博士论文级综述写作工作区**，基于 [MinerU 3.4](https://github.com/opendatalab/MinerU)。把 PDF/DOCX/PPTX/XLSX/图片用 MinerU 转成 Markdown，清理后只保留 `paper.md + images/` 作为 AI 可读资产；再用结构化目录 `literature_catalog.json` 让大模型"像导师一样"先规划该读哪些全文，最后按需读取全文 Markdown、组装可编译的独立 LaTeX 写作项目。

## 核心契约：不要删除、不要弱化、不要重构掉

1. 本项目是本地文献资产库 + AI 摘要目录 + 按需全文阅读 + 博士论文级综述写作工作区。
2. 本项目不做向量数据库、不做 RAG、不做 embedding、不做 ChromaDB。
3. 所有 `/prompt/*` 和写作流程只生成 prompt / 模板，不内置 LLM client，不自动调用任何大模型。
4. PDF/DOCX/PPTX/XLSX/图片先经 MinerU 转为 `paper.md + images/`；长期 AI 可读资产只保留清理后的 Markdown 和图片。
5. `data/raw/` 和 `data/papers/` 是版权语料，不进入 git，zip 快照中缺失时校验只能 warning。
6. `library_index.json` 是全局路径/领域注册表，是 paper 物理存储唯一事实源。
7. 同一篇文献可以重复出现在多个领域 catalog 中；这是合法的领域视图重复索引（domain catalog 可以重复索引）。
8. 同一篇文献不能重复存储 PDF / paper.md / images / manifest / library_index canonical record（paper 物理存储不能重复）。
9. 多领域选文进入写作前必须 compact / dedupe。
10. PDF 获取系统采用可配置 access policy（默认 `oa_only`，只使用开放获取来源）。项目核心流程不得硬编码任何单一下载站点；非 OA 来源必须通过 access policy 显式启用，并通过插件/浏览器辅助/本地导入等隔离接口进入 pending PDF 队列。无论来源如何，正式入库前必须经过 duplicate detection 和人工确认。
    - `oa_only` 模式下**不得包含 Sci-Hub** 或其他非开放获取渠道。
    - Sci-Hub 仅能通过 `AccessPolicy(mode=CUSTOM, allow_scihub=True)` 显式启用。
11. 新论文从 pending PDF 入库时，必须先做 duplicate detection 查重；重复 DOI 或重复 sha256 只能更新 domains membership，不能新建 paper。
12. catalog 管文献理解，manifest 管文件状态，library_index 管路径和领域 membership，三者职责分离。
13. 所有 JSON 写入必须原子化：filelock + tmp + os.replace。
14. 所有外部输入的 paper_id / job_id / image_name / file path 必须经 validate + safe_child 防路径穿越。
15. paper_id 命名规范：格式为 `{year}_{author}_{中文描述}`，如 `2023_wang_有限粒径颗粒阻力模型`。入库时通过 `--paper-id` 传入中文名称，auto-fallback 的英文名仅为临时兜底。目录 `data/papers/<paper_id>/` 的文件夹名必须与 paper_id 一致。
    - **禁止用 PDF 原始文件名作为 paper_id**（如 `download`、`article`、`fulltext`、`1-s2.0-...`、`science.abc12345`）。
    - paper_id 优先级链：`CLI --paper-id` > `sidecar.canonical_paper_id` > `sidecar.proposed_paper_id` > DOI 元数据生成 > filename fallback。
    - filename fallback 必须在 sidecar 中写入 warning，不得静默。
    - 同名冲突：DOI 相同 → 同一篇（不可新建）；DOI 不同 → 报错（不可覆盖）；无 DOI → warning + 需用户确认。
    - 已有错误 paper_id 通过 `python scripts/repair_paper_ids.py` 安全迁移（默认 dry-run，--apply 执行，执行前自动备份）。
16. 测试不得访问真实网络；OpenAlex / Semantic Scholar / Crossref / Unpaywall 必须 mock。
17. 每次代码改动完成后，必须运行完整验收，并运行 `python scripts/pack_repo.py` 生成 zip 快照。

## 三层文献库架构

文献库分三层，职责严格分离：

### A. Canonical storage layer（唯一物理存储层）

唯一事实源：

- `data/raw/` — PDF 原文
- `data/papers/<paper_id>/paper.md` + `images/`
- `data/manifests/papers_manifest.json`
- `data/catalog/library_index.json`

规则：每篇文献只能有一个 canonical `paper_id`；同一 DOI / 同一 sha256 / 同一 paper_id 不能产生多个 canonical 记录。所有全文与图片读取必须通过 `library_index.json` / `PaperLibrary` 解析路径，禁止硬编码 `data/papers/<paper_id>/paper.md`。

### B. Global semantic catalog（全局文献理解目录）

`data/catalog/literature_catalog.json`：每篇 canonical paper 一条，管理 `ai_summary` / `tags` / `selection_hints` / `citation` / `primary_domain` / `domains`。是"文献理解事实源"，不在全局层重复同一篇文献。

### C. Domain catalog view layer（领域视图索引层）

`data/catalog/domains/<domain_id>/literature_catalog.json` + `references.bib`：是"视图"，不是唯一事实源。**同一篇文献允许出现在多个领域 catalog 中**（跨领域重复索引合法）；同一领域 catalog 内部不应重复同一 paper_id。每个领域条目带 `domain_view`（`domain_id` / `is_primary_domain` / `canonical_paper_id`）指明它只是视图而非新实体。同一篇 paper 出现在多个 domain `references.bib` 中也合法。

`primary_domain` 决定主领域，`domains` 决定所有领域视图 membership。领域 catalog 收录所有 `domains` 中声明该领域的文献，而不只是 primary domain。

领域注册表由 `config/domains.json` 驱动；代码中的 `VALID_DOMAINS`、`DOMAIN_LABELS`、`DOMAIN_REGISTRY` 必须从该配置派生。旧三个领域必须保持兼容，新增领域不得硬编码到业务代码中。

## 多领域 compact 选文

同一篇文献可跨领域重复索引。多领域选文进入写作前必须 compact / dedupe：

```bash
python scripts/compact_domain_catalog.py \
    --domains blowing_snow_physics aeolian_snow_transport \
    --output data/discovery/queries/compact_blowing_snow_aeolian.json
```

写作流程 `match --domains` / `POST /write/jobs/{id}/match-catalog {domain_ids}` 支持按领域选文并 compact，候选保留 `source_domains`。不传时使用全局 catalog。

## PDF 获取架构（可配置 access policy）

PDF 获取系统采用多后端可插拔架构，通过 access policy 控制启用哪些 resolver。

### Access modes

- `oa_only`（默认）— 只用开放获取：Unpaywall / OpenAlex / Semantic Scholar / arXiv / publisher OA 直链。不绕过付费墙。
- `institutional` — 允许使用用户已有机权（TDM API、机构代理、浏览器登录态等），但核心仓库不实现自动化登录，只提供 `requires_user_action=True` 的浏览器辅助接口。
- `browser_assisted` — 不自动化下载，只生成 landing page 和待办任务，用户手动确认后通过 `register_manual_pdf.py` 登记。
- `local_manual` — 用户已有 PDF，本系统只做查重、sidecar、pending import。
- `custom` — 通过外部命令插件扩展，默认禁用。

### resolver chain

每个 access mode 对应一组 enabled resolver。resolver 依次尝试，首个成功返回 PDF URL / 本地点命中即返回。每次尝试记录到 `resolver_chain`。所有结果写入 sidecar 进入 pending 队列。

### 规则

- 默认 access_mode 必须为 `oa_only`。
- 任何自动下载结果只能进入 `data/raw/<domain>/pending/`，不得直接入正式 catalog。
- 所有来源都必须写 sidecar，记录 `source`、`access_mode`、`resolver`、`pdf_url / landing_url`、`sha256`、`access_status`、`fetched_at`。
- 正式入库必须走 `import_pending_pdf.py`。
- 重复 DOI / sha256 只能更新 domains membership，不能新建 paper。

## DOI discovery 与 PDF 获取

多阶段管线：关键词 → DOI 候选 → access policy → resolver chain → pending PDF。

优先使用开放获取 source：OpenAlex、Semantic Scholar、Crossref、Unpaywall、arXiv、Copernicus OA 等。非 OA 渠道须通过 access policy 显式启用。Unpaywall/OpenAlex 优先明确 PDF 字段（`url_for_pdf` / `primary_location.pdf_url`），landing page 仅 fallback 并在 metadata 标记 `maybe_landing_page=True`。所有结果默认进入 pending 状态，不会自动写入 catalog、manifest 或触发 MinerU。

## pending PDF 人工确认入库

第三阶段实现 pending PDF 的人工确认入库闭环：pending PDF → 本地 duplicate detection 查重 → MinerU 转换 → 正式入库。入库后自动更新 manifest / library_index / 全局 catalog placeholder / 领域 catalog / references.bib，但**不自动生成 AI summary**，只生成待补全 catalog 条目并提示用 `/prompt/catalog-entry` 补全。

入库前必须查重：重复 DOI 或重复 sha256 **只更新 domains membership，不新建 paper、不重新转换**；title 相似 + year 接近的疑似重复需用户确认。查重完全本地，不联网。

```bash
python scripts/list_pending_pdfs.py
python scripts/import_pending_pdf.py <pending.pdf> --domain ... --domains ... --title ... --doi ... --year ...   # dry-run
python scripts/import_pending_pdf.py <pending.pdf> ... --apply
```

sidecar JSON 状态机：`pending` → `imported` / `duplicate` / `failed`。

## 完整验收命令

```bash
python scripts/migrate_to_domain_library.py --apply
python scripts/validate_catalog.py
python scripts/validate_bib.py
python scripts/validate_domain_library.py
python scripts/compact_domain_catalog.py --domains blowing_snow_physics aeolian_snow_transport
pytest -q
python scripts/pack_repo.py
```

要求：所有测试通过；不访问真实网络；不真实调用 MinerU；zip 快照包含新增代码与文档；不破坏第一/二阶段；允许 domain catalog 跨领域重复索引；禁止 paper 物理重复存储。

## Paper ID Migration / 错误文件夹修复

已有 `data/papers/` 中可能包含错误命名的文件夹（来自历史导入的 PDF 文件名 fallback）。修复工具：

```bash
# 全库扫描
python scripts/repair_paper_ids.py

# 导出 mapping
python scripts/repair_paper_ids.py --export-mapping repair_mapping.json

# 人工审核后执行
python scripts/repair_paper_ids.py --mapping repair_mapping.json --apply

# 单篇重命名
python scripts/repair_paper_ids.py --rename download:2024_zhang_canonical --apply
```

安全规则：
- 默认 dry-run（--apply 才执行）
- 执行前自动备份索引到 `data/backups/paper_id_repair/`
- 迁移同步更新：manifest、catalog、library_index、domain catalogs、references.bib
- 不删除 paper.md 或 images
- 不同 DOI 的冲突不覆盖；相同 DOI 报告 merge candidate（默认不合并）

## Metadata Enrichment / 元数据补全

- `src/services/metadata_enrichment_service.py` — DOI 提取 + Crossref 查询 + 多源元数据规范化
- `scripts/enrich_pending_pdf.py` — CLI 补全 pending PDF sidecar（默认 dry-run）
- `src/services/paper_id.py` — `resolve_paper_id()` 实现完整 paper_id 优先级链
- `register_manual_pdf.py` 支持 `--auto-metadata`、`--chinese-title`、`--paper-id`、`--doi`、`--title`、`--year`、`--authors`
- `import_pending_pdf.py` 导入前自动做 metadata enrichment preflight
- `src/fetch/fetch_pipeline.py` 的 `_write_sidecar` 自动写入规范化的 authors/first_author/venue/proposed_paper_id

## 禁止事项

- 不要恢复 ChromaDB / embedding / RAG。
- 不要引入 LLM client，不要让任何流程自动调用大模型。
- 不要把 domain catalog 当唯一事实源；不要因同一 paper 出现在两个 domain catalog 就判定错误。
- 不要因 zip 里缺 `data/papers` 正文就让测试失败（只能 warning）。
- 不要把 pending PDF 自动入 catalog 为已总结状态。
- 不要让入库流程绕过 duplicate detection。
- 不要硬编码 `data/papers/<paper_id>/paper.md` 作为唯一读取方式。
- 不要用 PDF 原始文件名作为 paper_id（必须走 metadata enrichment 或显式 --paper-id）。
- 不要让 repair_paper_ids.py 在无 --apply 时修改数据。
- 不要让迁移流程绕过备份。
