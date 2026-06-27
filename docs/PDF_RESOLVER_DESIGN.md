# PDF Resolver 架构设计

## 架构概览

```
DOI / title / metadata
  → access policy
  → resolver chain
  → candidate PDF / landing page / manual action
  → pending PDF sidecar
  → import_pending_pdf.py
```

## Access Policy

`src/fetch/access_policy.py` 定义五种模式：

| Mode | 启用 resolver | 说明 |
|------|---------------|------|
| `oa_only` | unpaywall, openalex, semantic_scholar, arxiv, publisher_oa | 默认，纯 OA |
| `institutional` | OA + publisher_tdm, institutional_browser | 允机构权限 |
| `browser_assisted` | OA + browser_assisted | 只返回 landing page |
| `local_manual` | local_manual | 本地已有 PDF |
| `custom` | OA + 外部命令插件 | 可扩展 |

## Resolver Chain

每个 resolver 实现：

```python
class PdfResolver:
    name: str
    access_modes: tuple[str, ...]
    def enabled(self, policy) -> bool: ...
    def resolve(self, context: ResolveContext) -> FetchResult: ...
```

chain 顺序由 `AccessPolicy.enabled_resolver_names()` 决定。首个返回 `success=True` 且 `requires_user_action=False` 的 resolver 命中即返回。

## 现有 OA 源

- OpenAlex — `src/fetch/fetch_openalex.py`
- Semantic Scholar — `src/fetch/fetch_semantic_scholar.py`
- Crossref/Publisher OA — `src/fetch/fetch_publisher.py`
- Unpaywall — `src/fetch/fetch_unpaywall.py`
- arXiv — `src/fetch/fetch_arxiv.py`

## 借鉴外部项目

### ref-downloader

借鉴点：Crossref 获取文献 DOI、机构 Edge 登录态访问、断点续传、Zotero 集成。

本项目采用：新增 `InstitutionalBrowserResolver` 占位。

### auto-paper-harvester

借鉴点：三层降级（publisher TDM → OA → Playwright browser）；补充材料支持。

本项目采用：先抽象 resolver chain，后续扩展 `PublisherTDMResolver`，保留 mock/dry-run。

### paperdl

借鉴点：多 platform connector（arXiv / OpenReview / bioRxiv / PMC OA 等）；异步搜索/下载框架。

本项目采用：可新增 `preprint_resolvers.py`，不硬依赖 paperdl。

### sci-papers-downloader 等

借鉴点：metadata search + Unpaywall primary + fallback 分层结构；sidecar/下载报告。

本项目采用：只借鉴架构，不把任意单站点写死进核心流程。

## 补充材料

`FetchResult` 支持 `supplementary_urls` / `supplementary_paths` / `has_supplementary` 字段。
后续可扩展 `data/raw/<domain>/pending/<doi_slug>_supplement/`。

## 测试要求

- 所有 resolver 测试必须 mock 网络请求
- 必须覆盖 `to_dict`/`from_dict` 新旧 sidecar 兼容
- batch fetch 测试必须 mock 单个 DOI fetch
- 文档测试确保 `access policy` / `oa_only` / `resolver chain` 等关键词存在
