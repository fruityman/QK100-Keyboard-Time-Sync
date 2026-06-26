@echo off
chcp 65001 >nul
REM ================================================================
REM QK Keyboard 时间校正 - 一键运行启动器 (HID 直发版)
REM ----------------------------------------------------------------
REM 双击本文件即可把键盘 TFT 时钟校准为当前系统时间。
REM 通过 HID Feature Report 直接向键盘命令通道发送官方同款序列,
REM 不再依赖启动官方程序 / 图像识别点击, 几秒完成, 无需屏幕解锁交互。
REM 运行结果同时写入 time_sync.log。
REM ================================================================
cd /d "%~dp0"

REM 默认使用 PATH 中的 python; 如需指定可改成完整路径。
set "PYEXE=python"

echo ================================================
echo   QK Keyboard 时间校正 (HID 直发) - 开始运行
echo   将把键盘时间校准为当前系统时间
echo ================================================
echo.

REM PYTHONIOENCODING 确保中文输出不乱码; 输出同时上屏并追加到日志
set PYTHONIOENCODING=utf-8
"%PYEXE%" "%~dp0time_sync_hid.py" --send --backend ctypes

echo. >> "%~dp0time_sync.log"
echo [%date% %time%] 运行了一次 HID 时间校正 >> "%~dp0time_sync.log"

echo.
echo ================================================
echo   运行结束。请确认键盘 TFT 屏时间已更新、键盘可正常打字。
echo ================================================
pause
