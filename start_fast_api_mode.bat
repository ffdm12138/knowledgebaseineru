@echo off
chcp 65001 >nul
echo ========================================
echo   MinerU 文献资产库 v3.4 - 加速模式
echo   Runner: cli_api_proxy (CLI + --api-url)
echo   需先启动 mineru-api 常驻服务
echo ========================================
echo.

cd /d "%~dp0"

:: CUDA 路径（硬编码默认值，不依赖 shell 环境变量）
set CUDA_PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6
set PATH=%CUDA_PATH%\bin;%PATH%

:: mineru-api 加速配置
set MINERU_RUNNER=cli_api_proxy
set MINERU_REQUIRE_GPU=true
set MINERU_API_URL=http://127.0.0.1:8000
set MINERU_BACKEND=hybrid-engine
set MINERU_EFFORT=medium
set MINERU_METHOD=auto

:: watcher 默认不启动
set START_WATCHER=0

call conda activate mineru
if %errorlevel% neq 0 (
    echo [!] 请先安装 Miniconda 并创建 mineru 环境
    pause
    exit /b 1
)

echo [1/3] 启动 mineru-api 常驻服务 (端口 8000，模型常驻 GPU)...
echo      首次启动约需 30-60 秒加载 VLM 模型到 GPU (约 6-8 GB 显存)
echo      后续所有转换通过 --api-url 复用此服务，避免每次冷启动
echo.
start "MinerU-API" cmd /c "set CUDA_PATH=%CUDA_PATH%&& set PATH=%CUDA_PATH%\bin;%PATH%&& conda activate mineru && mineru-api --port 8000 --enable-vlm-preload true"

:: 等 mineru-api 启动（最多等 60 秒）
echo 等待 mineru-api 就绪...
set /a WAIT=0
:wait_loop
timeout /t 2 /nobreak >nul
set /a WAIT+=2
curl -s http://127.0.0.1:8000/health >nul 2>&1
if %errorlevel% equ 0 goto api_ready
if %WAIT% geq 60 goto api_timeout
goto wait_loop

:api_timeout
echo [!] mineru-api 启动超时，请检查 CUDA 环境和 mineru 安装
echo     手动检查: curl http://127.0.0.1:8000/health
pause
exit /b 1

:api_ready
echo [OK] mineru-api 已就绪

if "%START_WATCHER%"=="1" (
    echo [2/3] 启动文件夹监控 (可选的 watcher)...
    start "MinerU-Watcher" cmd /c "set CUDA_PATH=%CUDA_PATH%&& set PATH=%CUDA_PATH%\bin;%PATH%&& set MINERU_RUNNER=cli_api_proxy&& set MINERU_REQUIRE_GPU=true&& set MINERU_API_URL=http://127.0.0.1:8000&& conda activate mineru && python watcher.py --interval 30"
)

echo [3/3] 启动文献库 Web 服务 (端口8080)...
echo      访问: http://localhost:8080
echo      API文档: http://localhost:8080/docs
echo      Runtime: http://localhost:8080/status/runtime
echo.
python -m src.server

pause
