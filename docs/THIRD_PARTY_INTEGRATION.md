# 第三方 PDF 下载工具整合设计与改动 Plan

> **状态说明**：代理端口 7890 当前不在线（`127.0.0.1:7890` 无响应），无法通过代理验证 GitHub 仓库的实时许可信息。以下分析基于训练数据中各项目公开信息。标记 `[待验证]` 的项目是网络条件恢复后须通过 7890 代理复查的。

---

## 一、改动范围总览

本轮改动涉及：
1. `config/settings.py` — 确认 `FETCH_PROXY` 配置（已有）
2. `src/fetch/resolvers/` — 新增 2 个 resolver 实现
3. `docs/THIRD_PARTY_INTEGRATION.md` — 开源许可汇总（本文）
4. `README.md` — 新增「已使用开源项目」章节
5. `CLAUDE.md` / `AGENTS.md` — 新增第三方工具使用说明
6. `tests/` — 新增 resolver 测试

---

## 二、按项目逐一分析

### 2.1 ref-downloader ⭐115

**仓库**：github.com/nicolay-r/ref-downloader [待验证]  
**已知许可**：Apache 2.0  
**技术栈**：Python + Chrome/Edge DevTools Protocol (CDP)

#### 核心机制

```
ref-downloader <DOI>
  → 通过 Crossref API 获取参考文献 DOI 列表
  → 对每个 DOI 尝试 20+ 出版商直链（ACS/Nature/Elsevier/Wiley/IEEE/RSC/IOP 等）
  → 复用本地 Edge/Chrome 浏览器的学校/机构登录态（DevTools Protocol）
  → 打开每个出版商页面 → 自动下载
  → 输出 JSON 报告
```

#### 关键依赖层

| 依赖 | 作用 | 已存在本项目？ |
|------|------|--------------|
| `requests` | HTTP 请求 | ✅ 已有 |
| `crossref-api` | 获取参考文献 DOI | ✅ 已有 `search_crossref` |
| `Chrome/Edge CDP` | 浏览器自动控制 | ❌ 无 |
| `selenium` / `playwright` | 浏览器控制底层 | ❌ 无 |

#### 整合判定：**适合，但非核心依赖**

本项目已有的等价能力：
- Crossref 查询 → 已有 `resolve_crossref.py`
- OA PDF 下载 → 已有 `resolvers/oa_resolvers.py`
- sidecar/报告 → 已有 `FetchResult`

ref-downloader 的核心独特价值是**复用浏览器机构登录态访问 20+ 付费出版商**。这个能力通过现有 `InstitutionalBrowserResolver` 占位已预留。

#### 改动：新增 `ref_downloader_bridge.py`

```python
class RefDownloaderResolver(PdfResolver):
    name = "ref_downloader"
    access_modes = ("institutional", "custom")

    def resolve(self, context: ResolveContext) -> FetchResult:
        """
        通过子进程调用 ref-downloader CLI：
          ref-downloader <doi> --output <dir> --browser edge
        读取输出 JSON 报告，转换为 FetchResult。
        不直接 import ref-downloader Python 包。
        """
        # 检查 ref-downloader 是否可用
        # subprocess.run(["ref-downloader", "--version"], capture_output=True)
        # 如果不可用 → 返回 requires_user_action=True
        # 提示用户: pip install ref-downloader
```

---

### 2.2 auto-paper-harvester ⭐23

**仓库**：github.com/LuisDGM/auto-paper-harvester [待验证]  
**已知许可**：MIT  
**技术栈**：Python + Playwright + Crossref/OpenAlex/Unpaywall

#### 核心架构（三层降级）

```
Layer 1: 出版商 TDM API（ACS / Elsevier / Wiley / RSC 等）
Layer 2: Crossref → OpenAlex → Unpaywall OA
Layer 3: Playwright 控制浏览器（机构登录态兜底）
```

#### 与覆盖本项目对比

| 层 | auto-paper-harvester | 本项目 |
|---|---------------------|--------|
| OA | Crossref → OpenAlex → Unpaywall | Unpaywall → OpenAlex → S2 → arXiv → Publisher |
| TDM | ACS / Elsevier / Wiley TDM | `PublisherTDMResolver` 占位 |
| Browser | Playwright | `InstitutionalBrowserResolver` 占位 |
| 补充材料 | ✅ 支持 | `FetchResult.supplementary_*` 已定义 |

#### 整合判定：**借鉴架构，不依赖代码**

本项目已有 OA 层覆盖更广（多了一个 Semantic Scholar）。auto-paper-harvester 的补充材料支持和 DOI 前缀路由（24 个前缀→19 个家族）值得借鉴。

#### 改动：新增 `supplemental_resolver.py` + 前缀路由

```python
# DOI 前缀→出版商家族路由表（借鉴 auto-paper-harvester）
PUBLISHER_ROUTES = {
    "10.1016": "elsevier",
    "10.1021": "acs",
    "10.1002": "wiley",
    "10.1038": "nature",
    "10.1109": "ieee",
    "10.1088": "iop",
    "10.1098": "royal_society",
    # ... 更多
}

class SupplementalResolver(PdfResolver):
    name = "supplemental"
    access_modes = ("oa_only", "institutional")
    # 下载补充材料到 pending/<doi_slug>_supplement/
```

---

### 2.3 paperdl ⭐59

**仓库**：github.com/stephanlazar/paperdl [待验证]  
**已知许可**：MIT  
**技术栈**：Python + aiohttp/trio 异步框架

#### 已覆盖的平台

| 平台 | 本项目已有？ | paperdl 方式 |
|------|------------|-------------|
| arXiv | ✅ `ArxivResolver` | `arxiv.org` API |
| bioRxiv | ❌ | `api.biorxiv.org` |
| medRxiv | ❌ | `api.medrxiv.org` |
| PMC OA | ❌ | `ncbi.nlm.nih.gov/pmc/tools/oa-service/` |
| ACL Anthology | ❌ | `aclanthology.org` |
| OpenReview | ❌ | `api.openreview.net` |
| PMLR | ❌ | `proceedings.mlr.press` |

#### 整合判定：**低优先级，但可逐个新增平台 resolver**

从覆盖收益最大的开始：bioRxiv/medRxiv → PMC OA → OpenReview → ACL → PMLR

#### 改动：新增 `preprint_resolvers.py`

每个平台一个轻量 resolver，各自一个 API 调用 + PDF 链接提取：

```python
class BiorxivResolver(PdfResolver):
    """https://api.biorxiv.org/details/doi/10.1101/xxxx"""
    name = "biorxiv"
    access_modes = ("oa_only",)

class PmcOaResolver(PdfResolver):
    """https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id=doi:10.xxx"""
    name = "pmc_oa"
    access_modes = ("oa_only",)

class OpenReviewResolver(PdfResolver):
    """https://api.openreview.net/notes?forum=forum_id"""
    name = "openreview"
    access_modes = ("oa_only",)
```

---

### 2.4 Sci-Hub 工具（第二梯队）

#### 对比

| 项目 | 方式 | 本项目已有等价？ |
|------|------|----------------|
| scihub-cli | CLI: `scihub <doi>` → 下载 PDF | ❌ 无 CLI，但有 `resolve_scihub()` |
| scihub-paper-downloader | Python: 返回 Sci-Hub PDF URL | ✅ `fetch_scihub.py` 等价 |
| sci-papers-downloader | Scopus + Unpaywall + Sci-Hub | ❌ 多了一层 Scopus |
| DoiHarvest | 批量 DOI 下载 + 断点续传 | ✅ `_download_pdf()` 已有 atomic write |
| LYH_DOI_Tools | Chrome 扩展，DOI 链接旁显示图标 | ❌ 浏览器扩展，不整合 |

#### 整合判定

- `scihub-cli`：已有等价实现 `fetch_scihub.py`，**不整合**
- `sci-papers-downloader`：其 Scopus 元数据 + DOI 发现逻辑类似我们的 `discover_papers.py`。**可借鉴**Scopus 搜索层（如果用户有 API key）。新增 `search_scopus.py`（可选，需要 API key）
- `LYH_DOI_Tools`：**不直接整合**，在 `docs/` 中记录推荐使用

---

## 三、改动 Plan（按执行顺序）

### Phase 1：基础（已交付）

- ✅ `config/settings.py` — `FETCH_PROXY` 配置
- ✅ `access_policy.py` — 5 种 access mode
- ✅ `FetchResult` — access metadata + supplement 字段
- ✅ `resolvers/` 统一接口
- ✅ `institutional_resolvers.py` / `browser_resolvers.py` — 占位
- ✅ `fetch_pipeline.fetch_pdf()` — 通用入口
- ✅ `fetch_pdf.py` / `register_manual_pdf.py` / `fetch_pdf_batch.py`

### Phase 2：扩展 resolver（本轮新增）

| # | 文件 | 改动 | 借鉴来源 |
|---|------|------|---------|
| 1 | `src/fetch/resolvers/ref_downloader_bridge.py` | 新增 `RefDownloaderResolver` | ref-downloader |
| 2 | `src/fetch/resolvers/supplemental_resolver.py` | 新增 `SupplementalResolver` + 出版商前缀路由 | auto-paper-harvester |
| 3 | `src/fetch/resolvers/preprint_resolvers.py` | 新增 `BiorxivResolver` / `PmcOaResolver` / `OpenReviewResolver` | paperdl |
| 4 | `src/fetch/fetch_pipeline.py` | 扩展 `_build_resolvers` 加入新 resolver | — |
| 5 | `config/settings.py` | 确认无额外配置需要 | — |

### Phase 3：文档更新

| # | 文件 | 改动 |
|---|------|------|
| 1 | `docs/THIRD_PARTY_INTEGRATION.md` | ✅ 本文 |
| 2 | `README.md` | 新增「已使用开源项目」章节 + 许可声明 |
| 3 | `CLAUDE.md` / `AGENTS.md` | 新增第三方工具使用说明 |
| 4 | `tests/` | 新增 `test_ref_downloader_bridge.py` / `test_preprint_resolvers.py` / `test_supplemental_resolver.py` |

### Phase 4：测试

| 测试文件 | 覆盖 |
|---------|------|
| `test_ref_downloader_bridge.py` | CLI 不可用时返回 action_hint；mock subprocess 调用成功 |
| `test_preprint_resolvers.py` | bioRxiv / PMC OA / OpenReview mock API 调用 |
| `test_supplemental_resolver.py` | 前缀路由匹配；补充材料字段序列化 |

---

## 四、README.md 新增「已使用开源项目」章节

```markdown
## 开源项目与许可

本项目依赖以下开源项目，按许可类型分类：

### Apache 2.0
- [MinerU](https://github.com/opendatalab/MinerU) — PDF/DOCX 文档解析引擎（MinerU Open Source License，基于 Apache 2.0，商用需注意月活/营收门槛，见 [MinerU LICENSE](https://github.com/opendatalab/MinerU/blob/master/LICENSE.md)）
- [requests](https://github.com/psf/requests) — HTTP 库
- [gradio](https://github.com/gradio-app/gradio) — Web UI

### MIT
- [fastapi](https://github.com/fastapi/fastapi) — Web API 框架
- [pydantic](https://github.com/pydantic/pydantic) — 数据模型
- [loguru](https://github.com/Delgan/loguru) — 日志
- [pytest](https://github.com/pytest-dev/pytest) — 测试框架

### BSD-3
- [uvicorn](https://github.com/encode/uvicorn) — ASGI 服务器

### AGPL v3
- [PyMuPDF](https://github.com/pymupdf/PyMuPDF) — PDF 文件操作

### Unlicense
- [filelock](https://github.com/tox-dev/py-filelock) — 文件锁

### 间接引用（不直接依赖，子进程调用或借鉴架构）
- [ref-downloader](https://github.com/nicolay-r/ref-downloader) — Apache 2.0，用于机构权限 PDF 获取
- [auto-paper-harvester](https://github.com/LuisDGM/auto-paper-harvester) — MIT，借鉴三层降级架构
- [paperdl](https://github.com/stephanlazar/paperdl) — MIT，借鉴多平台预印本查询
```

---

## 五、CLAUDE.md / AGENTS.md 新增使用说明

在「PDF 获取与第三方工具」章节补充：

```bash
# ── 第三方工具集成（须自行安装）──

# ref-downloader: 机构权限批量下载
pip install ref-downloader
# 配置 Edge 登录态后
python scripts/fetch_pdf.py 10.xxxx/yyyy --access-mode institutional

# Sci-Hub 仅作 CUSTOM + allow_scihub=True 的隔离调试，不属于 OA/institutional 默认链
python -c "from src.fetch.fetch_scihub import resolve_scihub; r = resolve_scihub('10.xxxx/yyyy'); print(r.success, r.pdf_url)"

# 批量下载（OA only，不使用 Sci-Hub）
export FETCH_PROXY=http://127.0.0.1:7890
python scripts/fetch_pdf_batch.py --domain blowing_snow_physics --limit 100
# Sci-Hub 不在 oa_only 链中，需 CUSTOM + allow_scihub=True 显式启用

# 手动注册已有 PDF
python scripts/register_manual_pdf.py local.pdf --doi 10.xxxx/yyyy --domain blowing_snow_physics
```

---

## 六、改动工作量估算

| 改动 | 文件数 | 新增代码 | 已有代码修改 | 测试数 |
|------|--------|---------|------------|-------|
| Phase 1（已完成） | 10+ | ~800 行 | ~100 行 | 27 |
| Phase 2 resolver 扩展 | 4 | ~250 行 | ~30 行 | 15 |
| Phase 3 文档 | 4 | ~150 行 | ~50 行 | 3 |
| Phase 4 测试 | 3 | ~200 行 | — | 15 |

---

## 七、验收条件

```bash
python scripts/migrate_to_domain_library.py --apply
python scripts/validate_catalog.py
python scripts/validate_bib.py
python scripts/validate_domain_library.py
pytest -q
python scripts/pack_repo.py
```

要求：
- 273+ passed
- 不访问真实网络（mock API 调用）
- 新 resolver 不破坏旧 fetch_oa_pdf 行为
- 已引用项目许可正确标注
