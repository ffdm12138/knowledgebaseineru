"""MinerU 文献资产库 Web UI (Gradio)

重构后定位：文献资产库 + AI 摘要目录 + 按需全文阅读。
不再做语义检索 / RAG。所有 prompt 仅生成、不调 LLM。

功能：
- 上传 PDF/DOCX 等文件，自动转换 -> 清理 -> 入文献库
- 文献列表 / 全文查看 / 删除
- 三类 Prompt 生成（单篇目录条目 / 目录规划阅读 / 全文写作）

启动: conda activate mineru && python app.py
访问: http://localhost:7860
"""
import sys
from pathlib import Path

import gradio as gr

sys.path.insert(0, str(Path(__file__).parent))

from config.settings import (
    RAW_DIR, MINERU_TMP_DIR, PAPERS_DIR,
    MINERU_BACKEND, MINERU_EFFORT, MINERU_METHOD, MINERU_LANG,
)
from src.converter import MinerUConverter
from src.cleaner import MinerUOutputCleaner
from src.manifest import PaperManifest
from src.library import PaperLibrary
from src.catalog import Catalog
from src.prompt_builder import PromptBuilder
from src.naming import derive_paper_id

# ========== 初始化 ==========
converter = MinerUConverter()
cleaner = MinerUOutputCleaner()
manifest = PaperManifest()
library = PaperLibrary(manifest=manifest)
catalog = Catalog()
prompt_builder = PromptBuilder(catalog=catalog, library=library)


# ========== 核心功能 ==========

def upload_and_convert(file, progress=gr.Progress()):
    """上传文件并转换清理入库"""
    if file is None:
        return "请选择文件"
    import shutil
    filename = Path(file.name).name
    save_path = RAW_DIR / filename
    shutil.copy2(file.name, str(save_path))

    paper_id = derive_paper_id(filename)
    progress(0.1, desc="MinerU 转换中...")
    result = converter.convert(save_path, MINERU_TMP_DIR / paper_id,
                                backend=MINERU_BACKEND, method=MINERU_METHOD,
                                lang=MINERU_LANG, effort=MINERU_EFFORT)
    if not result["success"]:
        return f"❌ 转换失败: {result.get('error')}"

    progress(0.7, desc="清理输出中...")
    clean = cleaner.extract(result["output_dir"], paper_id, overwrite=True)
    if not clean["success"]:
        return f"❌ 清理失败: {clean.get('error')}"

    manifest.upsert(paper_id=paper_id, raw_pdf=str(save_path),
                    markdown=clean["markdown_path"], images_dir=clean["images_dir"],
                    status="converted", images_count=clean["images_count"],
                    md_chars=clean["char_count"])
    progress(1.0, desc="完成")
    return f"""✅ 转换完成

📄 paper_id: `{paper_id}`
📝 字符: {clean['char_count']}
🖼️ 图片: {clean['images_count']}
📁 Markdown: {clean['markdown_path']}"""


def list_papers():
    """列出文献库"""
    papers = manifest.list_all()
    stats = manifest.stats()
    if not papers:
        return "文献库为空，请先上传文档"
    out = f"## 文献库概览\n\n- 文献总数: **{stats['total_papers']}** 篇\n- 总字符: {stats['total_md_chars']}\n- 总图片: {stats['total_images']}\n\n"
    out += "| # | paper_id | 原始文件 | 字符 | 图 |\n|---|----------|----------|------|----|\n"
    for i, p in enumerate(papers, 1):
        raw = Path(p["raw_pdf"]).name
        out += f"| {i} | `{p['paper_id']}` | {raw} | {p['md_chars']} | {p['images_count']} |\n"
    return out


def view_markdown(paper_id):
    """查看某篇全文"""
    pid = paper_id.strip()
    if not pid:
        return "请输入 paper_id"
    md = library.read_markdown(pid, max_chars=8000)
    if md is None:
        return f"未找到 paper.md: {pid}"
    return md


def gen_catalog_entry_prompt(paper_id):
    """生成单篇目录条目补全 prompt"""
    pid = paper_id.strip()
    if not pid:
        return "请输入 paper_id"
    out = prompt_builder.build_catalog_entry_prompt(pid)
    if not out.get("success"):
        return f"失败: {out.get('error')}"
    return out["prompt"]


def gen_plan_prompt(question):
    """生成目录规划阅读 prompt"""
    q = question.strip()
    if not q:
        return "请输入研究问题"
    out = prompt_builder.build_catalog_planning_prompt(q)
    if not out.get("success"):
        return f"失败: {out.get('error')}"
    return out["prompt"]


def gen_fulltext_prompt(question, paper_ids_text):
    """生成基于全文的写作 prompt"""
    q = question.strip()
    if not q:
        return "请输入研究问题"
    ids = [s.strip() for s in paper_ids_text.split(",") if s.strip()]
    if not ids:
        return "请输入 paper_id 列表（逗号分隔）"
    out = prompt_builder.build_fulltext_prompt(q, ids)
    if not out.get("success"):
        return f"失败: {out.get('error')}"
    return out["prompt"]


def delete_paper(paper_id):
    """删除文献"""
    import shutil
    pid = paper_id.strip()
    if not pid:
        return "请输入 paper_id"
    pdir = PAPERS_DIR / pid
    removed = False
    if pdir.exists():
        shutil.rmtree(pdir)
        removed = True
    manifest.delete(pid)
    catalog.delete(pid)
    if not removed and not manifest.has(pid):
        return f"未找到: {pid}"
    return f"已删除: {pid}"


def get_status():
    from datetime import datetime
    stats = manifest.stats()
    return f"""## 系统状态

| 项目 | 状态 |
|------|------|
| 模式 | 文献资产库（无向量检索） |
| 文献数量 | {stats['total_papers']} 篇 |
| 总字符 | {stats['total_md_chars']} |
| 总图片 | {stats['total_images']} |
| 目录条目 | {len(catalog.list_papers())} |
| MinerU 后端 | {MINERU_BACKEND} |
| 更新时间 | {datetime.now().strftime('%H:%M:%S')} |"""


# ========== Gradio UI ==========

THEME = gr.themes.Soft(primary_hue="indigo", neutral_hue="slate")

with gr.Blocks(theme=THEME, title="MinerU 文献资产库",
               css=".gradio-container { max-width: 1200px !important; }") as app:

    gr.Markdown("# 📚 MinerU 文献资产库\n**文献解析 · AI 摘要目录 · 按需全文阅读**")

    with gr.Tabs():
        # Tab 1: 上传
        with gr.TabItem("📤 上传文献"):
            gr.Markdown("上传 PDF/DOCX/PPTX/XLSX/图片，自动转换 → 清理 → 入文献库")
            with gr.Row():
                with gr.Column(scale=1):
                    file_input = gr.File(label="选择文件",
                                         file_types=[".pdf", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg"])
                    upload_btn = gr.Button("🚀 上传并转换", variant="primary")
                with gr.Column(scale=1):
                    upload_status = gr.Markdown(label="状态")
            upload_btn.click(upload_and_convert, inputs=[file_input], outputs=[upload_status])

        # Tab 2: 文献库
        with gr.TabItem("📁 文献库"):
            refresh_btn = gr.Button("🔄 刷新")
            doc_list = gr.Markdown()
            refresh_btn.click(list_papers, outputs=[doc_list])

        # Tab 3: 全文阅读
        with gr.TabItem("📖 全文阅读"):
            pid_input = gr.Textbox(label="paper_id", placeholder="如 1999_dery_吹雪体相模型")
            view_btn = gr.Button("📖 查看全文", variant="primary")
            md_out = gr.Textbox(label="paper.md（前 8000 字符）", lines=24)
            view_btn.click(view_markdown, inputs=[pid_input], outputs=[md_out])

        # Tab 4: Prompt 生成
        with gr.TabItem("🧩 Prompt 生成"):
            gr.Markdown("三类 prompt，**仅生成、不调 LLM**，复制后粘贴给大模型。")
            with gr.Accordion("① 单篇目录条目（让 LLM 读全文补全 catalog 条目）", open=True):
                entry_pid = gr.Textbox(label="paper_id")
                entry_btn = gr.Button("生成")
                entry_out = gr.Textbox(label="Prompt", lines=18)
                entry_btn.click(gen_catalog_entry_prompt, inputs=[entry_pid], outputs=[entry_out])
            with gr.Accordion("② 目录规划阅读（让 LLM 规划该读哪些全文）", open=False):
                plan_q = gr.Textbox(label="研究问题")
                plan_btn = gr.Button("生成")
                plan_out = gr.Textbox(label="Prompt", lines=18)
                plan_btn.click(gen_plan_prompt, inputs=[plan_q], outputs=[plan_out])
            with gr.Accordion("③ 全文写作（读取指定全文组装写作 prompt）", open=False):
                full_q = gr.Textbox(label="研究问题")
                full_ids = gr.Textbox(label="paper_id 列表（逗号分隔）")
                full_btn = gr.Button("生成")
                full_out = gr.Textbox(label="Prompt", lines=18)
                full_btn.click(gen_fulltext_prompt, inputs=[full_q, full_ids], outputs=[full_out])

        # Tab 5: 文献管理
        with gr.TabItem("🗑️ 删除文献"):
            del_input = gr.Textbox(label="paper_id")
            del_btn = gr.Button("🗑️ 删除", variant="stop")
            del_status = gr.Markdown()
            del_btn.click(delete_paper, inputs=[del_input], outputs=[del_status])

        # Tab 6: 状态
        with gr.TabItem("⚙️ 系统状态"):
            gr.Button("🔄 刷新").click(get_status, outputs=[gr.Markdown(value=get_status())])

    app.load(list_papers, outputs=[doc_list])


if __name__ == "__main__":
    app.launch(server_name="127.0.0.1", server_port=7860, share=False, show_error=True)
