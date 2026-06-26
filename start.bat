@echo off
chcp 65001 >nul
echo ========================================
echo   MinerU 知识库服务 v3.4
echo   API服务端口: 8000 (mineru-api)
echo   Web服务端口: 8080 (知识库)
echo   代理端口 7890 已避开
echo ========================================
echo.

cd /d "%~dp0"

:: 设置CUDA路径 (lmdeploy需要)
set CUDA_PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6
set PATH=%CUDA_PATH%\bin;%PATH%

call conda activate mineru
if %errorlevel% neq 0 (
    echo [!] 请先安装Miniconda并创建mineru环境
    pause
    exit /b 1
)

echo [1/3] 启动 mineru-api 常驻服务 (端口8000)...
echo      模型将预加载到GPU，首次启动较慢
echo.
start "MinerU-API" cmd /c "set CUDA_PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6 && conda activate mineru && mineru-api --port 8000 --enable-vlm-preload true"

echo [*] 等待API服务就绪 (约20秒)...
timeout /t 20 /nobreak >nul

echo [2/3] 启动文件夹监控 (自动转换新增文件)...
echo      监控目录: data\raw
echo      检查间隔: 30秒
echo.
start "MinerU-Watcher" cmd /c "set CUDA_PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6 && conda activate mineru && python watcher.py --interval 30"

echo [3/3] 启动知识库Web服务 (端口8080)...
echo      访问: http://localhost:8080
echo      API文档: http://localhost:8080/docs
echo.
python -m src.server

pause
