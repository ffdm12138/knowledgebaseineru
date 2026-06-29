# MinerU Performance Notes

Use one MinerU conversion at a time by default. Hybrid engine may use several GB of GPU memory per process.

## Diagnostics

```bash
python scripts/check_mineru_processes.py
python scripts/benchmark_mineru.py "E:\papers\test.pdf" --repeat 2
```

For faster repeated conversion, start `mineru-api` manually and set:

```bash
set MINERU_RUNNER=cli_api_proxy
set MINERU_API_URL=http://127.0.0.1:8000
```
