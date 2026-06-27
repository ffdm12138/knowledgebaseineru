"""register_manual_pdf.py 测试（mock，不写真实 pending 目录）。"""
import json
from pathlib import Path

from scripts.register_manual_pdf import main as register_main


def test_register_manual_pdf_creates_sidecar(tmp_path, monkeypatch):
    """注册本地 PDF → pending 目录 + sidecar JSON。"""
    pdf = tmp_path / "test_paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    raw_dir = tmp_path / "raw"
    monkeypatch.setattr("scripts.register_manual_pdf.RAW_DIR", raw_dir)

    monkeypatch.setattr(
        "sys.argv",
        ["register_manual_pdf.py", str(pdf), "--domain", "blowing_snow_physics",
         "--doi", "10.1/test", "--title", "Test", "--year", "2025"],
    )
    ret = register_main()
    assert ret == 0

    # 检查 pending 目录
    pending = raw_dir / "blowing_snow_physics" / "pending"
    assert pending.exists()
    zips = list(pending.glob("*.pdf"))
    assert len(zips) == 1
    sidecars = list(pending.glob("*.json"))
    assert len(sidecars) == 1

    sidecar = json.loads(sidecars[0].read_text(encoding="utf-8"))
    assert sidecar["doi"] == "10.1/test"
    assert sidecar["title"] == "Test"
    assert sidecar["year"] == 2025
    assert sidecar["status"] == "pending"
    assert sidecar["access_mode"] == "local_manual"
    assert sidecar["sha256"]
