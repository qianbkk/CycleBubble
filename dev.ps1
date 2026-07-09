# CycleBubble 开发环境启动脚本 (PowerShell)
$ErrorActionPreference = 'Stop'

Write-Host "==================================="
Write-Host " CycleBubble 开发环境启动"
Write-Host "==================================="
Write-Host ""

# 检查 Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "[错误] 未找到 Python，请先安装 Python 3.10+" -ForegroundColor Red
    exit 1
}

# 创建虚拟环境
if (-not (Test-Path "venv")) {
    Write-Host "[1/3] 创建 Python 虚拟环境..." -ForegroundColor Cyan
    python -m venv venv
}

# 激活虚拟环境
Write-Host "[2/3] 激活虚拟环境..." -ForegroundColor Cyan
& "venv\Scripts\Activate.ps1"

# 安装依赖
Write-Host "[3/3] 安装/更新依赖..." -ForegroundColor Cyan
pip install -q -r requirements.txt

Write-Host ""
Write-Host "==================================="
Write-Host " 启动后端服务" -ForegroundColor Green
Write-Host " API: http://localhost:8000"
Write-Host " 文档: http://localhost:8000/docs"
Write-Host "==================================="
Write-Host ""

# 启动 FastAPI
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000