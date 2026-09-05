@echo off
chcp 65001 >nul
echo ========================================
echo   注册 Windows 定时任务：交易日全策略筛选
echo ========================================
echo.

:: 获取当前脚本所在目录的绝对路径
set "PROJECT_DIR=%~dp0"
:: 去掉末尾反斜杠
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

:: Python 路径（使用 venv 中的 python）
set "PYTHON_PATH=%PROJECT_DIR%\venv\Scripts\python.exe"

:: 检查 Python 是否存在
if not exist "%PYTHON_PATH%" (
    echo [错误] 未找到 Python: %PYTHON_PATH%
    echo 请确认 venv 目录存在且已安装 Python
    pause
    exit /b 1
)

echo 项目目录: %PROJECT_DIR%
echo Python路径: %PYTHON_PATH%
echo 任务名称: StockRunStrategies
echo 执行时间: 每日 20:02（StockDailyUpdate 今天20:00后成功完成才执行）
echo.

:: 删除已有任务（如果存在）
schtasks /delete /tn "StockRunStrategies" /f >nul 2>&1

:: 创建定时任务
schtasks /create ^
    /tn "StockRunStrategies" ^
    /tr "\"%PYTHON_PATH%\" \"%PROJECT_DIR%\runStrategiesAfterDailyUpdate.py\"" ^
    /sc daily ^
    /st 20:02 ^
    /rl HIGHEST ^
    /f

if %ERRORLEVEL% equ 0 (
    echo.
    echo [成功] 定时任务已注册！
    echo 任务将在每日 20:02 启动，StockDailyUpdate 今天20:00后成功完成才执行
    echo.
    echo 可通过以下命令查看任务状态：
    echo   schtasks /query /tn "StockRunStrategies" /v
    echo.
    echo 可通过以下命令手动触发：
    echo   schtasks /run /tn "StockRunStrategies"
    echo.
    echo 可通过以下命令删除任务：
    echo   schtasks /delete /tn "StockRunStrategies" /f
) else (
    echo.
    echo [错误] 定时任务注册失败！
    echo 请以管理员权限运行此脚本。
)

pause
