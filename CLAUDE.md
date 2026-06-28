# CLAUDE.md / AGENTS.md

**开始任何修改前必须先读：**
- `docs/PROJECT_CONTRACT.md` — 最完整的项目核心契约（**必读，不可跳过**）
- `README.md` — 项目定位、快速开始、常用命令

本文件是代码代理（Claude Code / Codex）在本仓库的工作入口，与 `AGENTS.md` 内容同源。

## 这是什么

一个本地 **文献资产库 + AI 摘要目录 + 按需全文阅读** 系统，基于 [MinerU 3.4](https://github.com/opendatalab/MinerU)。把 PDF/DOCX/PPTX/XLSX/图片用 MinerU 转成 Markdown，清理后只保留 `paper.md + images/` 作为 AI 可读资产；再用一个结构化目录 `literature_catalog.json` 让大模型"像导师一样"先规划该读哪些全文，再按需读取全文 Markdown 进行综述/写作。

> **重要**：本项目**不做向量检索 / RAG / 语义搜索**。重构时已删除 ChromaDB、chunker、indexer、retriever、embedding 模型。所有 `/prompt/*` 接口**只生成可复制粘贴的 prompt，不调用任何 LLM**——仓库里没有任何 LLM client。`data/raw/` 中的语料是雪科学 / 风吹雪文献，但代码与领域无关。

> **⚠️ 每次代码改动完成后，必须运行 `python scripts/pack_repo.py` 生成 `mineru_snapshot.zip`。**

## 核心不可改规则（完整版见 `docs/PROJECT_CONTRACT.md`）

1. 本项目是本地文献资产库 + AI 摘要目录 + 按需全文阅读 + 博士论文级综述写作工作区。
2. 不做向量数据库 / RAG / embedding / ChromaDB。
3. 所有 `/prompt/*` 和写作流程只生成 prompt / 模板，不内置 LLM client，不自动调用任何大模型。
4. PDF/DOCX/PPTX/XLSX/图片先经 MinerU 转为 `paper.md + images/`；长期 AI 可读资产只保留清理后的 Markdown 和图片。
5. `data/raw/` 和 `data/papers/` 是版权语料，不进入 git，zip 快照中缺失时校验只能 warning。
6. `library_index.json` 是全局路径/领域注册表，是 paper 物理存储唯一事实源。
7. 同一篇文献可以重复出现在多个领域 catalog 中（domain catalog 可以重复索引）；这是合法的领域视图。
8. 同一篇文献不能重复存储 PDF / paper.md / images / manifest / library_index canonical record（paper 物理存储不能重复）。
9. 多领域选文进入写作前必须 compact / dedupe。
10. PDF 获取系统采用可配置 access policy（默认 `oa_only`，只使用开放获取来源）。核心流程不得硬编码任何单一下载站点；非 OA 来源必须通过 access policy 显式启用，并通过插件/浏览器辅助/本地导入等隔离接口进入 pending PDF 队列。正式入库前必须经过 duplicate detection 和人工确认。
11. 新论文从 pending PDF 入库时，必须先做 duplicate detection 查重；重复 DOI 或重复 sha256 只能更新 domains membership，不能新建 paper。
12. catalog 管文献理解，manifest 管文件状态，library_index 管路径和领域 membership，三者职责分离。
13. 所有 JSON 写入必须原子化：filelock + tmp + os.replace。
14. 所有外部输入的 paper_id / job_id / image_name / file path 必须经 validate + safe_child 防路径穿越。
15. paper_id 命名规范：`{year}_{author}_{中文描述}`（如 `2023_wang_有限粒径颗粒阻力模型`），不遵循规范报错。
16. `hybrid-engine + medium + auto` 是默认产品路径；pipeline / vlm-engine 只作高级调试，不作为普通用户首选项。
17. 测试不得访问真实网络；OpenAlex / Semantic Scholar / Crossref / Unpaywall 必须 mock。
17. 每次代码改动完成后，必须运行完整验收，并运行 `python scripts/pack_repo.py` 生成 zip 快照。

## 不要改掉的设计

- 不要恢复 ChromaDB / embedding / RAG。
- 不要引入 LLM client，不要让任何流程自动调用大模型。
- 不要把 domain catalog 当唯一事实源；不要因同一 paper 出现在两个 domain catalog 就判定错误。
- 不要因 zip 里缺 `data/papers` 正文就让测试失败（只能 warning）。
- 不要把 pending PDF 自动入 catalog 为已总结状态。
- 不要让入库流程绕过 duplicate detection。
- 不要硬编码 `data/papers/<paper_id>/paper.md` 作为唯一读取方式；全文/图片读取一律经 `PaperLibrary`/`LibraryIndex` 解析路径。

## 每次修改前先理解的事实源

- `data/catalog/library_index.json` — paper 物理存储唯一事实源（路径 + 领域 membership）。
- `data/catalog/literature_catalog.json` — 全局文献理解目录（每篇 canonical paper 一条）。
- `data/catalog/domains/<domain_id>/literature_catalog.json` — 领域视图层（可跨领域重复索引）。
- `data/manifests/papers_manifest.json` — 文件状态账本（含 sha256）。

## 三层文献库架构

- **Canonical storage layer**（唯一物理存储）：`data/raw/`、`data/papers/<paper_id>/`、`papers_manifest.json`、`library_index.json`。同一 DOI / sha256 / paper_id 只能一个 canonical 记录。
- **Global semantic catalog**：`literature_catalog.json`，每篇 canonical paper 一条，管 ai_summary/tags/selection_hints/citation/primary_domain/domains。
- **Domain catalog view layer**：`data/catalog/domains/<domain_id>/`，是视图，同一篇文献可跨领域重复索引；领域条目带 `domain_view`（domain_id / is_primary_domain / canonical_paper_id）。`primary_domain` 决定主领域，`domains` 决定全部领域视图 membership。

## 多领域重复索引规则

- 领域注册表来自 `config/domains.json`；`VALID_DOMAINS` / `DOMAIN_LABELS` / `DOMAIN_REGISTRY` 均从配置派生，旧三个领域保持兼容。
- 领域 catalog 由 `migrate_to_domain_library.py --apply` 重建：收录所有 `domains` 中声明该领域的文献（不是只 primary domain）。
- `validate_domain_library.py` 允许跨领域重复 paper_id / DOI / bib_key，但禁止：library_index 内 paper_id/DOI/bib_key 多义、manifest 同 sha256 多 converted paper、同领域 catalog 内重复 paper_id、domain catalog 条目找不到 canonical 记录、`domain_view.domain_id` 与文件夹不一致、paper domains 声明与领域 catalog 收录不一致。
- 多领域选文用 `compact_domain_catalog.py` 或 `match --domains` compact 去重，候选保留 `source_domains`。

## pending PDF 入库规则

- `import_pending_pdf.py` 默认 dry-run，`--apply` 才写入。
- 入库前必须经 `src/duplicate_detector.py` 本地查重（DOI / sha256 / title+year），不联网。
- 重复 DOI 或 sha256：只更新已有 paper 的 `domains` membership，不重新转换、不新建 paper。
- 新文献：生成 canonical paper_id → 复制 PDF 到 `data/raw/` → MinerU 转换+清理 → manifest → library_index → 全局 catalog placeholder（status=unsummarized，不自动生成 AI summary）→ 重建领域 catalog → 更新 sidecar status=imported。
- 入库后提示用 `/prompt/catalog-entry` 补全文献理解条目。

## discovery/fetch 的 PDF 获取规则

- 优先使用 OpenAlex / Semantic Scholar / Crossref / Unpaywall / arXiv / publisher OA 直链。非 OA 来源须通过 access policy 显式启用。
- PDF 获取必须通过 `access_policy` + `resolver chain`，不得绕过 pending/import/duplicate detection。
- 新 resolver 必须可开关、可 mock、可记录 sidecar。
- 新 resolver 不得绕过 Content-Type / PDF 校验和 pending PDF 状态机。
- Codex/Claude 修改 PDF 获取逻辑时，必须先检查 access policy。
- 网络错误降级为 warning/失败结果，不中断本地校验。
- Unpaywall/OpenAlex 优先明确 PDF 字段（`url_for_pdf` / `primary_location.pdf_url`），landing page 仅 fallback 并在 metadata 标记 `maybe_landing_page=True`。
- 下载阶段保留 Content-Type / `.pdf` 校验。

## 环境

- **Conda 环境**：`mineru`（Python 3.10）。所有命令假设 `conda activate mineru`。
- **CUDA 路径**：`C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6`。
- **仅 Windows**：用 `mineru.exe`、`.bat` 编排、硬编码 Windows 路径。平台为 win32。
- `config/settings.py` 导入有副作用——创建数据目录。
- 所有配置项支持环境变量覆盖（`.env` 兼容）。

### MinerU 转换注意事项

**内存管理**：MinerU hybrid-engine 后端每启动一个进程约占用 4-8 GB 显存 + 系统内存。**不要同时跑多个转换**，否则会 OOM（os error 1455）。

- 默认单线程：`MINERU_MAX_WORKERS=1`（`config/settings.py`）
- 手动导入 pending PDF 时**逐个运行**，等一个完成再跑下一个
- 多 GPU 时可适当调大，但每增加一个 worker 需额外 4-8 GB 显存

**MinerU API 常驻服务**：

当前仓库的 HTTP 上传 adapter（runner=api）未实现。日常有三种 runner：
- `cli`：普通 MinerU CLI（每篇冷启动，稳定但批量慢）
- `cli_api_proxy`：MinerU CLI + `--api-url`，复用常驻 mineru-api 服务（推荐加速路径）
- `api`：项目自己实现 HTTP upload adapter（未实现，明确报错）

运行时状态看 `/status/runtime`。

```bash
# 启动（模型加载到 GPU，约 30 秒，约占用 6-8 GB 显存）
cd /d E:\1\mineru
set CUDA_PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6
set PATH=%CUDA_PATH%\bin;%PATH%
mineru-api --port 8000 --enable-vlm-preload true

# 验证
curl http://127.0.0.1:8000/health

# 当前代码不会静默把 api_url 回退到 CLI；启用 HTTP adapter 前不要在日常转换中传 --api-url
python batch_convert.py data/raw
```

> ⚠️ API 模式 + CLI 模式不能同时运行：API 已占用 GPU 显存时再起 CLI 转换会 OOM。
> `start.bat` 默认 CLI 单路径；如果以后实现 HTTP API 上传 adapter，必须让 watcher/upload/import 全部走同一个 runner。

### MinerU / GPU 运行时规则（agent 必须遵守）

- **不要手写 `subprocess.run(["mineru", ...])`**。所有 MinerU 调用必须通过项目内统一封装：
  - `MinerUConverter.convert()` — 普通转换
  - `MinerURuntime` (build_mineru_env / preflight_gpu / runtime_config_from_env) — 环境与 GPU 预检
  - `PaperRegistryService` / `PendingImportService` — 正式入库流程
  - `scripts/rebuild_library.py` — legacy repair（已改为调用 MinerUConverter）
- GPU 配置以项目 runtime 为准：
  - `MINERU_RUNNER`：`cli`（默认，每篇冷启动）| `cli_api_proxy`（推荐加速）| `api`（未实现）
  - `MINERU_REQUIRE_GPU=true`（默认）
  - `CUDA_PATH`、`CUDA_VISIBLE_DEVICES` 从环境变量读取；`CUDA_PATH` 已硬编码默认值到 `build_mineru_env()`
- 如果 `MINERU_REQUIRE_GPU=true`，`preflight_gpu()` 失败时 **不得静默降级 CPU**。
- 不要因为命令能跑就假设用了 GPU——查看 `/status/runtime` 确认。
- `start.bat` 默认 **不启动 watcher**（`START_WATCHER=0`），只启动 Web 服务。需要 watcher 时 `START_WATCHER=1`。

### MinerU Runner 说明

| Runner | 含义 | 加速效果 |
|--------|------|----------|
| `cli` | 纯 MinerU CLI，每次启动临时 mineru-api 服务 | 基准（82KB PDF ~63s） |
| `cli_api_proxy` | MinerU CLI + `--api-url`，复用常驻 mineru-api | **约 3.2x**（~20s） |
| `api` | 项目 HTTP upload adapter | **未实现，明确报错** |

加速流程：
1. 手动启动 `mineru-api --port 8000 --enable-vlm-preload true`（或运行 `start_fast_api_mode.bat`）
2. 设置 `MINERU_RUNNER=cli_api_proxy MINERU_API_URL=http://127.0.0.1:8000`
3. 所有转换共享同一模型实例，避免每篇冷启动

### CLI 冷启动风险

- 默认 `MINERU_RUNNER=cli`，批量转换时**每个 PDF 都会启动一个新的 mineru 进程**。
- MinerU CLI 不带 `--api-url` 时内部会自动启动临时 mineru-api 服务，每篇都经历模型加载。
- GPU preflight 只证明 GPU 可用，**不保证 GPU 被复用**。
- **诊断方法**：
  - `nvidia-smi -l 1` 观察 GPU 显存和利用率。
  - `data/logs/mineru_runs/*.json` 中 `nvidia_smi_before/after` 判断显存变化。
  - `python scripts/benchmark_mineru.py <pdf> --repeat 2` 测试单篇耗时。
  - `python scripts/check_mineru_processes.py` 查看进程和锁状态。
- **不要**同时启动多个 mineru 进程抢 GPU（全局 MinerULock 已保护）。
- **不要**在 `cli` runner 下传 `--api-url`（会返回结构化错误，提示改用 `cli_api_proxy`）。

## PDF Import Discipline / 文献 PDF 导入规范

> **这是 Codex / Claude Code 操作本仓库时关于 PDF 导入的权威规则。违反以下规则会导致 catalog 污染或数据不一致。**

### 核心状态定义

| 状态 | 含义 | 在哪里 |
|------|------|--------|
| **pending PDF** | 等待导入的 PDF，尚未进入正式库 | `data/raw/<domain>/pending/` |
| **converted** | 已转换并正式入库的文献 | manifest + catalog + library_index + domain catalog + bib |
| **unregistered_converted** | 已转换但缺少元数据，尚未正式入库 | manifest only（无 catalog 条目） |

### 推荐流程：外部文件夹 → register → import

**新 PDF 不要直接放进 `data/raw/` 根目录。**

正确流程：

**第 1 步**：把 PDF 放在项目外部的普通文件夹（如 `E:\papers_to_import\`）。

**第 2 步**：用 `register_manual_pdf.py` 登记为 pending：

```bash
# 如果知道 DOI，必须带 DOI
python scripts/register_manual_pdf.py "E:\papers_to_import\paper.pdf" \
    --domain blowing_snow_physics --title "Paper Title" --doi "10.xxxx/xxxxx" --year 2024

# 不知道 DOI 也至少带 title + year
python scripts/register_manual_pdf.py "E:\papers_to_import\paper.pdf" \
    --domain blowing_snow_physics --title "Paper Title" --year 2024
```

**第 3 步**：用 `import_pending_pdf.py --apply` 正式导入：

```bash
python scripts/import_pending_pdf.py \
    "data/raw/blowing_snow_physics/pending/paper.pdf" \
    --domain blowing_snow_physics --apply
```

正式导入后文献才会进入：
- `data/raw/`（canonical PDF 副本）
- `data/papers/<paper_id>/`
- `data/manifests/papers_manifest.json`
- `data/catalog/literature_catalog.json`
- `data/catalog/library_index.json`
- `data/catalog/domains/<domain>/literature_catalog.json`
- `data/catalog/domains/<domain>/references.bib`

> **正式入库必须经过 pending → duplicate detection → import 流程，不得绕过。**

### DOI / OA 获取 PDF 流程

```bash
# 第 1 步：获取 PDF 到 pending（不正式入库）
python scripts/fetch_pdf.py "10.xxxx/xxxxx" --domain blowing_snow_physics

# 第 2 步：正式导入
python scripts/import_pending_pdf.py \
    "data/raw/blowing_snow_physics/pending/<downloaded>.pdf" \
    --domain blowing_snow_physics --apply
```

关键规则：
- `fetch_pdf.py` / `fetch_pdf_batch.py` **只负责获取 PDF 并放入 pending**。
- pending PDF ≠ 正式入库。只有 `import_pending_pdf.py --apply` 才会正式注册到 catalog/index/domain/bib。
- 默认 `oa_only` 模式**不使用 Sci-Hub**。Sci-Hub 不得加入默认 OA resolver chain。
- Wiley / Elsevier / Springer TDM 等 publisher/institutional 通道必须通过 access policy 显式启用（`AccessMode.INSTITUTIONAL` 或 `AccessMode.CUSTOM`），并使用合法 token 或授权环境。当前没有 `AccessMode.PUBLISHER_TDM`，TDM 通道归于 INSTITUTIONAL 或 CUSTOM。

### 不推荐：直接把新 PDF 放进 data/raw/

禁止把新 PDF 直接丢进 `data/raw/` 根目录。原因：

1. `start.bat` 默认**不启动 watcher**（`START_WATCHER=0`），只启动 Web 服务。
2. 需要 watcher 时手动 `START_WATCHER=1 start.bat` 或直接 `python watcher.py`。
3. 由于缺少 DOI / title / year / domain 等元数据，产物变成 **unregistered_converted**。
4. unregistered_converted 不会污染正式 catalog，但后续需要人工补 metadata，反而更麻烦。

直接丢 `data/raw/` **不是正式入库流程**，只是触发自动转换。自动转换结果只进入 unregistered_converted 队列。

### watcher 的定位

`watcher.py` 是自动转换辅助工具，**不是推荐的正式文献入库入口**：

- 扫描 `data/raw/` 根目录，自动转换新 PDF。
- 默认产出 **unregistered_converted**（manifest 有记录，无 catalog 条目）。
- 不会直接写入正式 catalog / index / domain catalog / bib。
- 适合"先批量转了再说"的场景。
- **不适合严肃整理文献库**。

如果你希望文献元数据干净，走 `外部文件夹 → register_manual_pdf → import_pending_pdf --apply`，而不是把 PDF 丢进 `data/raw/`。

如果不希望 raw 根目录被自动转换，**不要启动 watcher**（手动运行 `python -m src.server` 只启动服务）。

### Web 上传与 batch_convert 的定位

- **Web 上传**：如果没有提供 domain / title / doi / year，转换结果可能是 **unregistered_converted**。
- **`batch_convert.py`**：适合批量转换，但不等价于正式文献整理。日常示例：

  ```bash
  python batch_convert.py data/raw
  ```

  `--api-url` 当前 HTTP adapter 未实现，不要在文档中宣传为加速方案。它更适合 legacy repair 或临时批量转换，不是最推荐的新文献入库流程。

- **`rebuild_library.py`**：legacy repair tool，不作为日常入库入口。

### 所有 PDF 来源的统一原则

无论 PDF 来源是什么——手动下载、DOI/OA fetch、institutional fetch、Web 上传、watcher 自动发现、batch_convert 批量转换——最终都必须被归入以下两类之一：

1. **正式文献（converted）**：有完整的 manifest + catalog + library_index + domain catalog + bib 记录。
2. **未注册转换结果（unregistered_converted）**：已转换但缺少正式元数据，需后续补 metadata 或人工整理。

**不要制造裸的 manifest-only converted**。如果某个路径只写 manifest 不写 catalog/index/domain，那只能用于 debug/repair，不能作为正常入库路径。

### 导入后

- **paper_id 命名**：`{year}_{author}_{中文描述}`（如 `2023_wang_有限粒径颗粒阻力模型`），通过 `--paper-id` 指定。
- **验证**：检查 paper.md 前几行确认内容与预期一致。如 DOI 元数据与实际 PDF 不符，立即删除：

  ```bash
  python scripts/remove_paper.py <paper_id> --apply
  ```

- **补全 catalog**：入库后用 `/prompt/catalog-entry` 补全文献理解条目（ai_summary / tags / selection_hints / citation）。
- 入库后的文献 status 为 **unsummarized**，不自动生成 AI summary。

### PDF 获取渠道速查

**API 额度**：
- OpenAlex 每日 ~30–50 次请求（429 超限后 UTC 零点重置）
- Semantic Scholar ~100 次/分钟（429 后等 ~1 分钟恢复）
- Unpaywall 有持续 422 错误（URL 编码问题），非临时故障
- Sci-Hub 公开镜像在中国大陆网络不可达（SSL/403）

**Publisher TDM / Institutional 通道**：
- Wiley TDM：`10.1002/` `10.1111/` `10.1029/`，需 `WILEY_TDM_TOKEN`
- Springer 直链：`10.1007/` `10.1186/` `10.1038/` `10.1147/`，无需密钥
- Elsevier TDM：`10.1016/`，需 `ELSEVIER_API_KEY`
- 这些通道独立于 OpenAlex/S2 API 额度
- 启用：在 access policy 中显式启用对应模式 + 设环境变量或 `.env`

**推荐 fetch 策略**：设好 TDM token → `fetch_pdf_batch.py --domain <domain> --limit 100` → `import_pending_pdf.py --apply`。所有成功结果只进入 pending，不自动入库。

## 常见开发任务

```bash
# 冒烟测试
curl http://localhost:8080/status
curl http://localhost:8080/status/runtime
curl http://localhost:8080/papers

# 批量转换（CLI runner）
python batch_convert.py data/raw
# watcher 单次扫描
python watcher.py --once
# 从旧版重建 papers
python scripts/rebuild_library.py

# 校验
python scripts/audit_library.py
python scripts/validate_catalog.py
python scripts/validate_bib.py
python scripts/validate_domain_library.py
python scripts/audit_library.py --strict
python scripts/validate_write_job.py --job <id>

# 领域视图重建
python scripts/migrate_to_domain_library.py --apply

# discovery / fetch
python scripts/discover_papers.py "风吹雪 升华 破碎" --domain blowing_snow_physics --max-candidates 30

# PDF 获取（支持多后端 access policy，默认 oa_only）
export FETCH_PROXY=http://127.0.0.1:7890   # 走代理（可选）
python scripts/fetch_oa_pdf.py 10.xxxx/yyyy --domain blowing_snow_physics --dry-run
python scripts/fetch_oa_pdf.py 10.xxxx/yyyy --domain blowing_snow_physics
python scripts/fetch_pdf.py 10.xxxx/yyyy --domain blowing_snow_physics --access-mode oa_only
python scripts/fetch_pdf.py 10.xxxx/yyyy --domain blowing_snow_physics --access-mode institutional
python scripts/fetch_pdf.py 10.xxxx/yyyy --domain blowing_snow_physics --access-mode browser_assisted
python scripts/register_manual_pdf.py paper.pdf --doi 10.xxxx/yyyy --domain blowing_snow_physics
python scripts/import_pending_pdf.py data/raw/blowing_snow_physics/pending/paper.pdf --domain blowing_snow_physics --apply
python scripts/fetch_pdf_batch.py --domain blowing_snow_physics --limit 50 --dry-run

# pending PDF
python scripts/list_pending_pdfs.py
python scripts/import_pending_pdf.py <pdf> --domain ... --domains ... --title ... --doi ... --year ...

# compact
python scripts/compact_domain_catalog.py --domains blowing_snow_physics aeolian_snow_transport --output <json>

# 综述写作
python scripts/write_review.py create --topic "..."
python scripts/write_review.py match --job <id> --domains blowing_snow_physics aeolian_snow_transport
python scripts/write_review.py confirm-papers --job <id> --papers ...
# ... deep-read → mark-deep-read → story → mark-story → tex → mark-tex → copy-figures → validate
```

## 验收命令

```bash
python scripts/migrate_to_domain_library.py --apply
python scripts/validate_catalog.py
python scripts/validate_bib.py
python scripts/validate_domain_library.py
python scripts/compact_domain_catalog.py --domains blowing_snow_physics aeolian_snow_transport
pytest -q
python scripts/pack_repo.py
```

要求：全部通过；不访问真实网络；不真实调用 MinerU；允许跨领域重复索引；禁止物理重复存储。

## 禁止事项

- 不要恢复 ChromaDB / embedding / RAG。
- 不要引入 LLM client，不要让任何流程自动调用大模型。
- 不要把 domain catalog 当唯一事实源；不要因同一 paper 出现在两个 domain catalog 就判定错误。
- 不要因 zip 里缺 `data/papers` 正文就让测试失败（只能 warning）。
- 不要把 pending PDF 自动入 catalog 为已总结状态。
- 不要让入库流程绕过 duplicate detection。
- 不要硬编码 `data/papers/<paper_id>/paper.md` 作为唯一读取方式。
