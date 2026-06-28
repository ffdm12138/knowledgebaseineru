# 第三方 PDF 下载工具整合 → 改动 Plan

> 验证方式：通过 Clash 代理 `127.0.0.1:7890` 实时搜索 GitHub API（4 组关键词，78+ 结果）。  
> 搜索时间：2026-06-27

---

## 一、已验证的仓库

通过 7890 代理从 GitHub API 搜索并确认存在的项目（按 ⭐ 排序）：

| 项目 | ⭐ | 许可 | 实际仓库 |
|------|---|------|---------|
| metachris/pdfx | 1075 | Apache-2.0 | ✅ 存在 |
| bibcure/scihub2pdf | 222 | AGPL-3.0 | ✅ 存在 |
| Agents365-ai/paper-fetch | 142 | MIT | ✅ 存在 |
| **ltczding-gif/ref-downloader** | **119** | **MIT** | ✅ **已验证，已有 LICENSE 全文** |
| braun-steven/arxiv-downloader | 68 | MIT | ✅ 存在 |
| InvincibleGuy777/sci-hub-crawler | 30 | MIT | ✅ 存在 |
| jxtse/auto-paper-harvester | 25 | NONE | ✅ 存在 |
| computron/fulltext-article-downloader | 18 | BSD-3 | ✅ 存在 |
| hanhan6688/DoiHarvest | 5 | NONE | ✅ 存在 |

### 用户提供的仓库名勘误

| 用户写的 | 搜索结果 |
|---------|---------|
| nicolay-r/ref-downloader ❌ | **ltczding-gif/ref-downloader** ✅ |
| LuisDGM/auto-paper-harvester ❌ | **jxtse/auto-paper-harvester** ✅ |
| GanjinZero/DoiHarvest ❌ | **hanhan6688/DoiHarvest** ✅ |
| stephanlazar/paperdl ❌ | 搜索无结果 |
| nicotine189/sci-papers-downloader ❌ | 搜索无结果 |
| Himself65/LYH_DOI_Tools ❌ | 搜索无结果 |
| icankeep/scihub-cli ❌ | 搜索无结果 |

---

## 二、改动 Plan（按执行顺序）

### Phase 0：Sci-Hub 加入 OA resolver chain（⚠️ **已废弃，不得执行**）

> **此方案与 `PROJECT_CONTRACT.md` 冲突，已废弃。**  
> - `oa_only` 模式 **不得** 包含 Sci-Hub。  
> - Sci-Hub 只能通过 `AccessMode.CUSTOM` + `allow_scihub=True` 显式启用。  
> - 默认批量 fetch 不使用 Sci-Hub。

**历史记录（仅供参考，不代表当前架构）**：

| 改动 | 文件 | 说明 |
|------|------|------|
| 添加 scihub 到 OA resolver 列表 | `src/fetch/access_policy.py` | `_oa_resolvers()` 末尾加 `"scihub"` |
| 添加 `_SciHubResolver` 类 | `src/fetch/fetch_pipeline.py` | 行内类，调用 `resolve_scihub()` |
| 添加到 name_map | `src/fetch/fetch_pipeline.py` | `"scihub": _SciHubResolver` |
| 更新测试 | `tests/test_access_policy.py` | 添加 `"scihub"` 到期望列表 |

**历史 resolver chain（已废弃）**：
```
Unpaywall → OpenAlex → S2 → arXiv → Publisher OA → Sci-Hub
```

**当前 resolver chain（oa_only）**：
```
Unpaywall → OpenAlex → S2 → arXiv → Publisher OA (不含 Sci-Hub)
```

### Phase 1：ref-downloader 桥接器

**理由**：唯一通过 7890 代理验证存在 + MIT 许可 + 功能互补（机构登录态访问 20+ 付费出版商）

| 改动 | 文件 | 工作量 |
|------|------|--------|
| 新增 `RefDownloaderResolver` | `src/fetch/resolvers/ref_downloader_bridge.py` | ~80 行 |
| 加入 `_build_resolvers` | `src/fetch/fetch_pipeline.py` | +2 行 |
| 测试（mock subprocess） | `tests/test_ref_downloader_bridge.py` | ~60 行 |

**设计**：
- 不直接 import ref-downloader 的 Python 代码
- 通过 `subprocess.run(["ref-downloader", doi, ...])` 调用 CLI
- 解析 JSON 输出报告 → 写入 pending queue
- 用户需自行 `pip install ref-downloader` + 配置 Edge 登录态

### Phase 2：preprint platform resolver（bioRxiv / PMC OA）

**理由**：paper-fetch (⭐142) 和 paperdl 的 7 平台架构已验证有效

| 改动 | 文件 | 工作量 |
|------|------|--------|
| 新增 `BiorxivResolver` | `src/fetch/resolvers/preprint_resolvers.py` | ~30 行 |
| 新增 `PmcOaResolver` | `src/fetch/resolvers/preprint_resolvers.py` | ~30 行 |
| 测试（mock API） | `tests/test_preprint_resolvers.py` | ~40 行 |

**API 接口**：
- bioRxiv: `GET https://api.biorxiv.org/details/doi/10.1101/xxxx` → JSON → `collection[0].pdf_url`
- PMC OA: `GET https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id=doi:10.xxx` → XML → PDF link

### Phase 3：文档更新（已完成 ✅）

| 改动 | 文件 |
|------|------|
| 已使用的开源项目表格 | `README.md` |
| PDF 获取用法说明 | `CLAUDE.md` / `AGENTS.md` |
| 第三方整合 Plan | `docs/PDF_RESOLVER_INTEGRATION_PLAN.md` |
| PDF Resolver 架构设计 | `docs/PDF_RESOLVER_DESIGN.md` |
| 核心契约更新 | `docs/PROJECT_CONTRACT.md` |

---

## 三、已变更的文件清单（当前阶段已完成）

### 架构层

| 文件 | 改动 |
|------|------|
| `src/fetch/access_policy.py` | 新增 5 种 access mode、`enabled_resolver_names()`、`clone_with()` |
| `src/fetch/models.py` | FetchResult 新增 10 个字段（access metadata + supplement） |
| `src/fetch/fetch_pipeline.py` | 新增 `fetch_pdf()` 通用入口 + `_build_resolvers()` + `_SciHubResolver` |
| `src/fetch/fetch_scihub.py` | 3 个 Sci-Hub 镜像 fallback，带代理支持 |
| `src/fetch/resolvers/base.py` | `PdfResolver` 统一接口 + `ResolveContext` |
| `src/fetch/resolvers/oa_resolvers.py` | 5 个 OA resolver 包装 |
| `src/fetch/resolvers/institutional_resolvers.py` | PublisherTDM + InstitutionalBrowser 占位 |
| `src/fetch/resolvers/browser_resolvers.py` | BrowserAssistedResolver |
| `src/fetch/resolvers/local_resolvers.py` | LocalManualResolver |
| `src/fetch/resolvers/custom_resolvers.py` | ExternalCommandResolver（子进程插件） |

### CLI

| 文件 | 说明 |
|------|------|
| `scripts/fetch_pdf.py` | 通用 PDF 获取 CLI，支持 `--access-mode` |
| `scripts/register_manual_pdf.py` | 本地 PDF 注册到 pending |
| `scripts/fetch_pdf_batch.py` | 批量 DOI 下载，支持 `--resume` / `--dry-run` / `--limit` |

### 集成存根

| 文件 | 说明 |
|------|------|
| `src/integrations/zotero.py` | Zotero 集成接口占位 |
| `docs/ZOTERO_INTEGRATION.md` | Zotero 集成设计文档 |

---

## 四、当前 resolver chain 工作状态

```
Unpaywall      → ⚠️ 422（匿名限速）
OpenAlex       → ⚠️ 429（限速）
Semantic Scholar → ⚠️ 429（限速）
arXiv          → ✅ 正常
Publisher OA   → ⚠️ 部分 400（缺 TDM token）
Sci-Hub        → ⚠️ 403/SSL（当前镜像被封）
```

### 已下载成果

**11 篇 PDF** ~46 MB：
- abl_pbl: 3 篇（Frontiers, ACP, AMT）
- aeolian: 3 篇（AGU, Nature, PLOS）
- blowing_snow: 5 篇（PLOS×2, arXiv, Frontiers, MDPI）

---

## 五、后续可执行项

### 🔧 立即能做（无需新依赖）
1. 等 OpenAlex/S2 限速恢复后继续搜 DOI + 批量下载
2. 用 `FETCH_PROXY=http://127.0.0.1:7890` + `fetch_pdf_batch.py` 批量跑（oa_only 模式）
3. ~~Sci-Hub 镜像恢复后可自动 fallback~~（已废弃：Sci-Hub 不在 oa_only 链中）

### 📦 需编码（Phase 1-2）
4. `ref_downloader_bridge.py` — 机构权限下载（~80 行，有测试）
5. `preprint_resolvers.py` — bioRxiv/PMC OA 平台（~60 行，有测试）

---

## 六、验收

```bash
python scripts/migrate_to_domain_library.py --apply
python scripts/validate_catalog.py
python scripts/validate_bib.py
python scripts/validate_domain_library.py
pytest -q
python scripts/pack_repo.py
```

期望：273+ passed，zip 包含所有新文件和文档。
