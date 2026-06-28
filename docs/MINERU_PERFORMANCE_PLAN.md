# MinerU 转换性能优化方案

> 状态：诊断阶段（不贸然改变默认 runner）

## 背景

当前默认配置：

```text
MINERU_RUNNER=cli
MINERU_REQUIRE_GPU=true
MINERU_BACKEND=hybrid-engine
MINERU_EFFORT=medium
```

CLI 模式为每个 PDF 启动独立 mineru 进程，批量转换时每篇都会经历模型冷启动。GPU preflight 只能证明机器有 GPU，不能保证 MinerU 每个推理阶段都高效复用 GPU。

## 诊断工具

### 1. `scripts/benchmark_mineru.py` — 单 PDF 基准测试

```bash
python scripts/benchmark_mineru.py "E:\papers_to_import\test.pdf"
python scripts/benchmark_mineru.py "E:\papers_to_import\test.pdf" --repeat 3
python scripts/benchmark_mineru.py "E:\papers_to_import\test.pdf" --method ocr --effort high
python scripts/benchmark_mineru.py "E:\papers_to_import\test.pdf" --keep-output
```

行为：
- 不写 manifest / catalog / library_index（不污染文献库）
- 转到临时目录
- 输出 timing summary + GPU snapshots (idle vs final)
- 写出 JSON 摘要到 `data/logs/benchmark_summary.json`

### 2. `data/logs/mineru_runs/<paper_id>_<timestamp>.json` — 每次转换的性能日志

每次 `MinerUConverter.convert_via_cli()` 自动记录：
- paper_id / pdf_path / file_size
- runner / backend / method / effort / lang
- MINERU_REQUIRE_GPU / CUDA_PATH / CUDA_VISIBLE_DEVICES
- preflight_gpu 结果
- mineru command
- start_time / end_time / elapsed_seconds
- return_code
- stdout/stderr 尾部
- output_dir / markdown_path / images_count
- nvidia_smi_before / nvidia_smi_after

### 3. `nvidia-smi -l 1` 实时监控

转换时开另一个终端：

```bash
nvidia-smi -l 1
```

观察：
- GPU 显存明显上涨 + GPU-Util 有波动 → GPU 启用但可能冷启动
- GPU 显存几乎不动，GPU-Util 长期 0 → 没用 GPU / 回退 CPU
- GPU 显存占了但 Util 很低，CPU 很高 → 卡在 PDF 解析/OCR/IO

### 4. `/status/runtime` 接口

```bash
curl http://127.0.0.1:8080/status/runtime
```

重点看 `gpu.nvidia_smi`、`gpu.ok`、`runtime.cuda_path`、`runtime.require_gpu`。

## 可能的优化方向

### 方案 A：CLI 批量稳定模式（当前默认）✅

- **优点**：简单可靠，每个 PDF 独立进程，互不干扰
- **缺点**：每个 PDF 启动一次 mineru 进程，模型冷启动耗时累加
- **适用**：少量 PDF 转换（<10 篇），单篇 latency 可接受

### 方案 B：mineru-api 常驻服务（需实现 HTTP upload adapter）

- **优点**：模型预加载到 GPU，批量转换共享同一模型实例，避免冷启动
- **缺点**：
  - 需要实现 HTTP upload adapter（当前 `convert_via_api()` 返回结构化失败）
  - 需要处理服务健康检查、错误恢复、请求队列
  - API + CLI 不能同时运行（双模型占 GPU 导致 OOM）
  - GPU 显存长期被占用
- **前提条件**：
  1. 实现 `convert_via_api()` 的 HTTP upload 逻辑
  2. 实现服务健康检查 + 自动拉起/恢复
  3. 确保 watcher/upload/import 全部走同一个 runner
  4. 通过充分测试和 GPU 显存评估

### 方案 C：单进程 worker 队列（需确认 MinerU Python API 稳定性）

- **优点**：项目内统一控制，不依赖独立 HTTP 服务
- **缺点**：需要确认 MinerU Python API 是否可稳定调用（当前只封装了 CLI）
- **风险**：MinerU 内部状态管理不一定暴露给 Python API

## 当前诊断优先级

1. 用 `nvidia-smi -l 1` 确认 GPU 是否实际被 MinerU 使用
2. 用 `scripts/benchmark_mineru.py` 对典型 PDF 测单篇耗时
3. 查看 `data/logs/mineru_runs/*.json` 中 GPU snapshot before/after 判断显存变化
4. 重复转换同一 PDF 看是否每篇耗时相近（冷启动 vs 模型复用）

## 不要做

- 不要未经实现和测试就切换默认 runner 为 api
- 不要在 HTTP upload adapter 未实现时宣称 API 加速
- 不要绕过 MinerURuntime / MinerUConverter 直接调用 mineru 子进程
- 不要让 API + CLI 同时占用 GPU
