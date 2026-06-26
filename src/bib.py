"""全局 BibTeX 管理

data/catalog/references.bib 是全库级 BibTeX 汇总，由 literature_catalog.json 的
citation.bibtex 字段同步而来。写作任务从这里抽取相关条目生成 references.bib。
"""
import re
from pathlib import Path
from loguru import logger

from config.settings import CATALOG_DIR

GLOBAL_BIB_PATH = CATALOG_DIR / "references.bib"


def _entry_type_and_key(block: str) -> tuple[str, str]:
    """从单个 bibtex 块提取 (type, key)，如 (@article{key, ...) → ('article','key')"""
    m = re.match(r"@(\w+)\s*\{\s*([^,\s]+)", block.strip())
    if not m:
        return ("", "")
    return m.group(1).lower(), m.group(2)


def parse_blocks(bib_text: str) -> dict[str, str]:
    """把 bib 文本拆成 {bib_key: block_text}。简单括号匹配，足以处理受控 bib。"""
    blocks = {}
    i = 0
    n = len(bib_text)
    while i < n:
        if bib_text[i] == "@":
            # 找到 type{ 后第一个 { 开始括号匹配
            brace_start = bib_text.find("{", i)
            if brace_start == -1:
                break
            depth = 0
            j = brace_start
            while j < n:
                if bib_text[j] == "{":
                    depth += 1
                elif bib_text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            block = bib_text[i:j + 1]
            _, key = _entry_type_and_key(block)
            if key:
                blocks[key] = block.strip()
            i = j + 1
        else:
            i += 1
    return blocks


def load_global_bib() -> dict[str, str]:
    """读取全局 references.bib，返回 {bib_key: block}"""
    if not GLOBAL_BIB_PATH.exists():
        return {}
    return parse_blocks(GLOBAL_BIB_PATH.read_text(encoding="utf-8"))


def sync_from_catalog(catalog_data: dict) -> int:
    """从 literature_catalog.json 同步生成 references.bib。返回条目数。"""
    blocks = []
    for p in catalog_data.get("papers", []):
        cit = p.get("citation", {}) or {}
        bt = (cit.get("bibtex") or "").strip()
        if bt:
            blocks.append(bt)
    text = "% 由 literature_catalog.json 自动同步生成，请勿手动编辑。\n\n" + "\n\n".join(blocks) + "\n"
    GLOBAL_BIB_PATH.parent.mkdir(parents=True, exist_ok=True)
    GLOBAL_BIB_PATH.write_text(text, encoding="utf-8")
    logger.info(f"同步 references.bib: {len(blocks)} 条")
    return len(blocks)


def get_entries_for_keys(bib_keys: list[str]) -> str:
    """从全局 bib 抽取指定 key 的条目，返回 bib 文本"""
    blocks = load_global_bib()
    out = []
    missing = []
    for k in bib_keys:
        if k in blocks:
            out.append(blocks[k])
        else:
            missing.append(k)
    if missing:
        logger.warning(f"references.bib 缺少 key: {missing}")
    return "\n\n".join(out) + "\n"


def validate(catalog_data: dict, bib_text: str | None = None) -> list[str]:
    """校验 catalog 与 references.bib 一致性。返回错误列表。"""
    errors = []
    bib_keys_in_file = set()
    if bib_text is None:
        if GLOBAL_BIB_PATH.exists():
            bib_keys_in_file = set(parse_blocks(GLOBAL_BIB_PATH.read_text(encoding="utf-8")).keys())
    else:
        bib_keys_in_file = set(parse_blocks(bib_text).keys())

    seen = set()
    for p in catalog_data.get("papers", []):
        ctx = f"paper_id={p.get('paper_id', '?')}"
        cit = p.get("citation", {}) or {}
        bk = cit.get("bib_key")
        bt = (cit.get("bibtex") or "").strip()
        if not bk:
            errors.append(f"{ctx} 无 bib_key")
            continue
        if bk in seen:
            errors.append(f"{ctx} bib_key 重复: {bk}")
        seen.add(bk)
        if not bt:
            errors.append(f"{ctx} 无 bibtex")
        else:
            for field in ["title", "author", "year"]:
                if not re.search(rf"\b{field}\s*=", bt, re.IGNORECASE):
                    errors.append(f"{ctx} bibtex 缺少 {field} 字段")
            doi = p.get("doi")
            if doi and f"doi" not in bt.lower():
                errors.append(f"{ctx} catalog 有 doi 但 bibtex 未写 doi")
        if bib_keys_in_file and bk not in bib_keys_in_file:
            errors.append(f"{ctx} bib_key={bk} 在 references.bib 中找不到")
    return errors
