# Zotero 集成设计（预留）

## 目标

- 从 Zotero 导出 BibTeX/BetterBibTeX 读取 DOI
- 检查 Zotero 是否已有 PDF
- 把 pending/imported PDF 与 Zotero item 对齐

## 数据结构

```python
@dataclass
class ZoteroAttachmentCandidate:
    doi: str
    title: str
    pdf_path: str
    item_key: str
    collection: str
```

## 接口

`src/integrations/zotero.py`：

```python
def export_doi_list(items: list[dict]) -> list[str]:
    """从 Zotero API items 提取 DOI 列表。"""
```

不依赖 pyzotero 库。后续扩展时：

1. 通过 Zotero API 读取 collections 和 items
2. 提取 DOI 与本地 library_index 对比
3. 缺失 PDF 时生成 download/review 任务
4. 已有 PDF 时标记对齐

## 不实现

- 不自动写入 Zotero 附件
- 不依赖 Zotero 作为 PDF 存储
- 不要求 Zotero 运行
