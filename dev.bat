@echo off
chcp 65001 >nul
echo ===================================
echo  CycleBubble 开发环境启动
echo ===================================
echo.

REM 检查 Python
where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    exit /b 1
)

REM 创建虚拟环境（如果不存在）
if not exist "venv\" (
    echo [1/3] 创建 Python 虚拟环境...
    python -m venv venv
)

REM 激活虚拟环境
echo [2/3] 激活虚拟环境...
call venv\Scripts\activate.bat

REM 安装依赖（如果未安装）
echo [3/3] 安装/更新依赖...
pip install -q -r requirements.txt

echo.
echo ===================================
echo  启动后端服务
echo  API: http://localhost:8000
echo  文档: http://localhost:8000/docs
echo ===================================
echo.

REM 启动 FastAPI
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000