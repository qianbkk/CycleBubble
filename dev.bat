@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM ===== 配置端口（想换端口改这里）=====
set "PORT=8000"

echo ===================================
echo  CycleBubble 后端启动 (端口 %PORT%)
echo ===================================
echo.

REM =============================================
REM  Step 1: 检查 Python
REM =============================================
where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)
echo [OK] Python 已找到

REM =============================================
REM  Step 2: 检查依赖（全局 Python）
REM =============================================
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo [1/3] 安装依赖（首次运行需联网）...
    python -m pip install --index-url http://pypi.org/simple --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [错误] 依赖安装失败
        echo 提示: 网络受限？尝试运行 python -m pip install -r requirements.txt 手动安装
        pause
        exit /b 1
    )
    echo [2/3] 依赖安装完成
) else (
    echo [1/3] 依赖已安装
    echo [2/3] 跳过 pip install
)
echo [3/3] 准备启动
echo.

REM =============================================
REM  Step 3: 检查端口冲突
REM =============================================
netstat -ano | findstr ":%PORT% " >nul 2>&1
if not errorlevel 1 (
    echo [警告] 端口 %PORT% 已被占用
    echo 这可能是上一次启动过的程序残留。
    echo.
    echo 请选择:
    echo   [1] 自动关闭占用进程后继续
    echo   [2] 修改 dev.bat 第 6 行 set PORT=XXXX 换端口
    echo.
    set /p "CHOICE=请输入 (1 或 2): "
    if "!CHOICE!"=="1" (
        for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% "') do (
            echo 关闭 PID %%a ...
            taskkill /F /PID %%a 2>nul
        )
        timeout /t 2 >nul
    ) else (
        echo 已取消。请修改 dev.bat 第 6 行设置 PORT。
        pause
        exit /b 1
    )
)

REM =============================================
REM  Step 4: 启动后端（直接用全局 Python）
REM =============================================
echo ===================================
echo  后端启动中
echo  API:   http://localhost:%PORT%/docs
echo  前端:  浏览器打开 index.html
echo         或运行 python -m http.server 8806
echo  停止:  按 Ctrl+C
echo ===================================
echo.

python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port %PORT%

pause
