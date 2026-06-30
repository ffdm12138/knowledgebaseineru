# MinerU Performance Notes

Use one MinerU conversion at a time by default. Hybrid engine may use several GB of GPU memory per process.
MinerU conversion requires GPU / MinerU 正式转换必须使用 GPU by default.
CPU/no-GPU conversion is debug-only via `MINERU_ALLOW_CPU=true` or explicit
`MINERU_REQUIRE_GPU=false`.

## Diagnostics

```bash
python scripts/check_mineru_processes.py
python scripts/benchmark_mineru.py "E:\papers\test.pdf" --repeat 2
```

For faster repeated conversion, start persistent `mineru-api` first. On Windows,
`start_fast_api_mode.bat` is the local helper for this path; otherwise start
`mineru-api` according to the local MinerU installation. Then set:

```bash
set MINERU_REQUIRE_GPU=true
set CUDA_VISIBLE_DEVICES=0
set MINERU_RUNNER=cli_api_proxy
set MINERU_API_URL=http://127.0.0.1:8000
```

PowerShell:

```powershell
$env:MINERU_REQUIRE_GPU="true"
$env:CUDA_VISIBLE_DEVICES="0"
$env:MINERU_RUNNER="cli_api_proxy"
$env:MINERU_API_URL="http://127.0.0.1:8000"
```

Linux / bash:

```bash
export MINERU_REQUIRE_GPU=true
export CUDA_VISIBLE_DEVICES=0
export MINERU_RUNNER=cli_api_proxy
export MINERU_API_URL=http://127.0.0.1:8000
```
