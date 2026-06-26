"""打包 git 跟踪的所有文件为 zip，放在项目根目录。

用途：GitHub/Gitee 提交后有缓存延迟，zip 可直接下载分发。
排除自身和 .zip 文件，避免死循环。

用法：
    python scripts/pack_repo.py              # 生成 mineru_snapshot.zip
    python scripts/pack_repo.py --name v2   # 生成 mineru_snapshot_v2.zip
"""
import subprocess
import zipfile
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
ZIP_NAME_BASE = "mineru_snapshot"


def git_tracked_files() -> list[str]:
    """返回 git ls-files 列出的所有跟踪文件（相对路径）"""
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        print(f"[WARN] git ls-files failed: {result.stderr}")
        return []
    files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
    print(f"  Found {len(files)} git-tracked files")
    return files


def main():
    suffix = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--name" else ""
    zip_name = f"{ZIP_NAME_BASE}_{suffix}.zip" if suffix else f"{ZIP_NAME_BASE}.zip"
    zip_path = PROJECT_ROOT / zip_name

    files = git_tracked_files()
    if not files:
        print("[ERROR] No tracked files, aborting")
        sys.exit(1)

    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(files):
            src = PROJECT_ROOT / f
            if not src.exists():
                print(f"  [SKIP] missing: {f}")
                continue
            # 排除自身以防万一
            if src.resolve() == Path(__file__).resolve():
                continue
            zf.write(src, f)
            count += 1

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"[OK] Packed: {zip_name} ({count} files, {size_mb:.1f} MB)")
    print(f"     {zip_path}")


if __name__ == "__main__":
    main()
