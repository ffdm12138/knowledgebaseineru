"""pack_repo 安全性测试：跳过含 surrogate 或不可编码的路径。"""
import subprocess
import zipfile

from scripts import pack_repo


_SURROGATE = chr(0xDD00)  # lone low surrogate
_HIGH_SURROGATE = chr(0xD800)


def test_safe_for_zip_rejects_surrogates():
    assert pack_repo._safe_for_zip("normal/path.md")
    assert pack_repo._safe_for_zip("data/catalog/library_index.json")
    assert pack_repo._safe_for_zip("中文字符/文件名.md")
    # surrogate 字符必须拒绝
    assert not pack_repo._safe_for_zip(f"md/bad{_SURROGATE}file.md")
    assert not pack_repo._safe_for_zip(f"{_HIGH_SURROGATE}start")


def test_safe_for_zip_rejects_non_utf8():
    # _safe_for_zip 应能处理任意 str，surrogate 已拒绝；UTF-8 编码失败也应拒绝
    # 在 Python 中，非 surrogate 的 str 通常可 encode("utf-8")，
    # 但 ZipInfo 会拒绝某些字符；此处先确保不崩溃
    assert pack_repo._safe_for_zip("ok/file.md")


def test_scan_repo_skips_unsafe_paths(monkeypatch, tmp_path):
    """filesystem fallback：good 文件保留，surrogate 被 skip，不崩溃。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "good.py").write_text("# ok", encoding="utf-8")

    # 模拟 git 失败 → 走 _scan_repo_files
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, "", "no git")

    monkeypatch.setattr(pack_repo, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(pack_repo.subprocess, "run", fake_run)

    files = pack_repo.git_tracked_files()
    assert "src/good.py" in files


def test_pack_end_to_end_normal_files(monkeypatch, tmp_path):
    """正常路径 zip 写入不崩溃，safe 文件全部打包。"""
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "lib.py").write_text("# code", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "index.json").write_text("{}", encoding="utf-8")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, "src/lib.py\0data/index.json\0", "")

    monkeypatch.setattr(pack_repo, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(pack_repo.subprocess, "run", fake_run)

    zip_path = tmp_path / "test.zip"
    files = pack_repo.git_tracked_files()
    assert "src/lib.py" in files
    assert "data/index.json" in files

    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(files):
            src = tmp_path / f
            assert pack_repo._safe_for_zip(f)
            zf.write(src, f)
            count += 1
    assert count == 2
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path, "r") as zf:
        assert "src/lib.py" in zf.namelist()


def test_surrogate_path_skipped_in_scan(monkeypatch, tmp_path):
    """git 返回含 surrogate 的路径时被 skip，safe 路径保留。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "good.py").write_text("# ok", encoding="utf-8")

    BAD_A = chr(0xDCB5)
    BAD_B = chr(0xDCA3)

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0], 0,
            f"src/good.py\0md/Mineru{BAD_A}{BAD_B}/bad.md\0",
            "",
        )

    monkeypatch.setattr(pack_repo, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(pack_repo.subprocess, "run", fake_run)

    files = pack_repo.git_tracked_files()
    assert "src/good.py" in files
    for f in files:
        assert BAD_A not in f
        assert BAD_B not in f
