"""结构收敛验收：app.py（Gradio）上传路径不得直接写 raw，必须走单一管道。

Gradio 曾用 shutil.copy2(file.name, RAW_DIR/filename) 绕过 FastAPI 的
sha256 + 上传锁 + converting 状态机，导致两套不一致的写入体系。本测试静态
守护这一收敛：app.py 的上传函数 (upload_and_convert) 只能作为 UI 层，
所有上传必须走 src.upload_service。

注：delete_paper 用 shutil.rmtree 删除 papers 目录是合理的删除语义，
与上传管道无关，不在本测试约束内。
"""
import ast
from pathlib import Path

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


def _source() -> str:
    return APP_PATH.read_text(encoding="utf-8")


def _func_body(src: str, name: str) -> str:
    """提取指定函数体的源码片段，用于上传路径专属检查。"""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    return ""


def _find_func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def test_app_uses_upload_service():
    """app.py 必须通过 upload_service 上传。"""
    src = _source()
    assert ("upload_from_bytes" in src or "upload_from_path" in src
            or "upload_core" in src), \
        "app.py 必须调用 upload_service 的 upload_from_bytes/upload_from_path/upload_core"


def test_upload_path_does_not_call_shutil_copy():
    """上传函数体内不得出现 shutil.copy2 / shutil.copy（直写 raw 的旧手法）。"""
    body = _func_body(_source(), "upload_and_convert")
    assert body, "app.py 必须定义 upload_and_convert"
    assert "shutil.copy" not in body, \
        "upload_and_convert 不得用 shutil.copy* 直写 raw 目录"


def test_upload_path_does_not_write_raw_dir():
    """上传函数体内不得直接引用 RAW_DIR 写文件（应由 upload_service 内部管理）。"""
    body = _func_body(_source(), "upload_and_convert")
    assert "RAW_DIR" not in body, \
        "upload_and_convert 不得引用 RAW_DIR（应交由 upload_service）"


def test_upload_path_does_not_call_manifest_upsert():
    """上传函数体内不得直接 manifest.upsert（须由 upload_service 完成）。"""
    body_node = _find_func(ast.parse(_source()), "upload_and_convert")
    assert body_node is not None
    for node in ast.walk(body_node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "upsert":
                raise AssertionError(
                    f"upload_and_convert 不得直接调用 .upsert()（行 {node.lineno}）")


def test_upload_path_does_not_call_converter_convert():
    """上传函数体内不得直接 converter.convert（须由 upload_service 完成）。"""
    body_node = _find_func(ast.parse(_source()), "upload_and_convert")
    assert body_node is not None
    for node in ast.walk(body_node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "convert":
                raise AssertionError(
                    f"upload_and_convert 不得直接调用 converter.convert()（行 {node.lineno}）")


def test_upload_path_does_not_call_cleaner_extract():
    """上传函数体内不得直接 cleaner.extract（须由 upload_service 完成）。"""
    body_node = _find_func(ast.parse(_source()), "upload_and_convert")
    assert body_node is not None
    for node in ast.walk(body_node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "extract":
                raise AssertionError(
                    f"upload_and_convert 不得直接调用 cleaner.extract()（行 {node.lineno}）")
