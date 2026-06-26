<#
.SYNOPSIS
    QK100-Keyboard-Time-Sync  一键构建便携版 / One-click portable build.

.DESCRIPTION
    本脚本完整复现便携版的构建过程, 产出一个开箱即用的 zip:
      1. 下载嵌入式 Python (embeddable, 64-bit) 到临时工作区
      2. 从本机已安装的同主版本 Python 补齐 tkinter (_tkinter.pyd + tcl/tk + tkinter 包)
      3. 补齐 hid 扩展模块 (hid.cp3xx-win_amd64.pyd, 用于 HID 设备枚举)
      4. 修改 ._pth 启用本地包导入
      5. 复制 src/ 源码到 app/, 并把日志/配置路径改写到便携包根目录
      6. 生成便携版启动 bat (校时一次.bat / 打开配置.bat) 与使用说明.txt
      7. 压缩成单个 zip

    This script reproduces the entire portable build and outputs a ready-to-run zip.

.PARAMETER PyVersion
    要下载的嵌入式 Python 版本 / Embedded Python version to download. 默认 3.10.6。

.PARAMETER HostPython
    本机已安装、用于补齐 tkinter/hid 的 Python 解释器 (须与 PyVersion 同主次版本, 如 3.10)。
    Host Python used to harvest tkinter/hid (must match PyVersion's major.minor).
    默认自动探测 PATH 中的 python。

.PARAMETER OutDir
    zip 输出目录 / Output directory for the zip. 默认仓库根目录。

.EXAMPLE
    pwsh -File build/build_portable.ps1

.EXAMPLE
    pwsh -File build/build_portable.ps1 -PyVersion 3.10.6 -HostPython "C:\Python310\python.exe"
#>
[CmdletBinding()]
param(
    [string]$PyVersion  = "3.10.6",
    [string]$HostPython = "",
    [string]$OutDir     = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

function Info($m) { Write-Host "[build] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[ ok  ] $m" -ForegroundColor Green }
function Die($m)  { Write-Host "[fail ] $m" -ForegroundColor Red; exit 1 }

# ---- 路径准备 / paths ------------------------------------------------------
$RepoRoot = Split-Path -Parent $PSScriptRoot          # build/ 的上级 = 仓库根
$SrcDir   = Join-Path $RepoRoot "src"
$DocsDir  = Join-Path $RepoRoot "docs"
if (-not $OutDir) { $OutDir = $RepoRoot }

$PkgName  = "QK100时间校正-便携版"
$Work     = Join-Path $RepoRoot "build\_work"
$Pkg      = Join-Path $Work $PkgName
$Runtime  = Join-Path $Pkg "runtime"
$App      = Join-Path $Pkg "app"

Info "仓库根 / repo root : $RepoRoot"
Info "嵌入式 Python 版本 : $PyVersion"

# ---- 解析主次版本 (3.10.6 -> 3.10 -> 310) ----------------------------------
if ($PyVersion -notmatch '^(\d+)\.(\d+)\.(\d+)$') { Die "PyVersion 格式应为 X.Y.Z, 例如 3.10.6" }
$MajMin = "$($Matches[1]).$($Matches[2])"             # 3.10
$Tag    = "$($Matches[1])$($Matches[2])"             # 310
$EmbedZipName = "python-$PyVersion-embed-amd64.zip"
$EmbedUrl     = "https://www.python.org/ftp/python/$PyVersion/$EmbedZipName"
$PthFile      = Join-Path $Runtime "python$Tag._pth"

# ---- 探测本机 Python (补 tkinter/hid 的来源) -------------------------------
if (-not $HostPython) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $HostPython = $cmd.Source } else { Die "未找到本机 python, 请用 -HostPython 指定 (需 $MajMin 版本)" }
}
if (-not (Test-Path $HostPython)) { Die "HostPython 不存在: $HostPython" }

$hostVer = & $HostPython -c "import sys;print('%d.%d'%sys.version_info[:2])"
if ($hostVer.Trim() -ne $MajMin) {
    Die "本机 Python 版本 ($hostVer) 与嵌入式版本 ($MajMin) 不匹配; tkinter/hid 二进制必须同版本。请用 -HostPython 指定 $MajMin。"
}
$HostHome = Split-Path -Parent $HostPython
Ok "本机 Python: $HostPython (v$hostVer)"

# ---- 清理并建工作区 / fresh workspace --------------------------------------
if (Test-Path $Work) { Remove-Item -Recurse -Force $Work }
New-Item -ItemType Directory -Force -Path $Runtime, $App | Out-Null

# ---- 1) 下载并解压嵌入式 Python --------------------------------------------
$EmbedZip = Join-Path $Work $EmbedZipName
Info "下载嵌入式 Python: $EmbedUrl"
try { Invoke-WebRequest -Uri $EmbedUrl -OutFile $EmbedZip -UseBasicParsing }
catch { Die "下载失败 (检查网络或版本号): $($_.Exception.Message)" }
Expand-Archive -Path $EmbedZip -DestinationPath $Runtime -Force
Ok "嵌入式 Python 解压完成"

# ---- 2) 补齐 tkinter (从本机精确同版本裁剪) --------------------------------
$DLLs = Join-Path $HostHome "DLLs"
$Lib  = Join-Path $HostHome "Lib"
$TclH = Join-Path $HostHome "tcl"
foreach ($f in @("_tkinter.pyd","tcl86t.dll","tk86t.dll")) {
    $p = Join-Path $DLLs $f
    if (-not (Test-Path $p)) { Die "缺少 $p (本机 Python 未含 tkinter?)" }
    Copy-Item $p -Destination $Runtime -Force
}
Copy-Item (Join-Path $Lib "tkinter") -Destination (Join-Path $Runtime "tkinter") -Recurse -Force
New-Item -ItemType Directory -Force -Path (Join-Path $Runtime "tcl") | Out-Null
Copy-Item (Join-Path $TclH "tcl8.6") -Destination (Join-Path $Runtime "tcl\tcl8.6") -Recurse -Force
Copy-Item (Join-Path $TclH "tk8.6")  -Destination (Join-Path $Runtime "tcl\tk8.6")  -Recurse -Force
Ok "tkinter / tcl / tk 已补齐"

# ---- 3) 补齐 hid 扩展模块 (设备枚举所需) -----------------------------------
$hidPyd = Get-ChildItem (Join-Path $Lib "site-packages") -Recurse -Filter "hid.cp$Tag-win_amd64.pyd" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $hidPyd) {
    Die "本机未安装 hid 模块。请先: `"$HostPython`" -m pip install hid (或 hidapi), 再重跑。"
}
Copy-Item $hidPyd.FullName -Destination $Runtime -Force
Ok "hid 模块已补齐: $($hidPyd.Name)"

# ---- 4) 修改 ._pth, 启用本地导入 -------------------------------------------
if (Test-Path $PthFile) {
    @("python$Tag.zip", ".", "", "import site") | Set-Content -Path $PthFile -Encoding ascii
    Ok "已更新 $([System.IO.Path]::GetFileName($PthFile))"
} else {
    Info "未找到 $PthFile (版本布局可能不同), 跳过 ._pth 修改"
}

# ---- 5) 复制源码到 app/ 并改写日志/配置路径到包根目录 ----------------------
Copy-Item (Join-Path $SrcDir "time_sync_hid.py")        -Destination $App -Force
Copy-Item (Join-Path $SrcDir "time_sync_config_gui.py") -Destination $App -Force
if (Test-Path (Join-Path $DocsDir "capture_packets.txt")) {
    Copy-Item (Join-Path $DocsDir "capture_packets.txt") -Destination $App -Force
}

# 5a) time_sync_hid.py : LOG_PATH -> 便携包根目录 (app/ 的上级)
$hidApp = Join-Path $App "time_sync_hid.py"
$c = Get-Content $hidApp -Raw
$old = 'LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "time_sync.log")'
$new = @'
# 便携版: 日志写到便携包根目录 (app/ 的上级), 方便用户直接查看。
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_PORTABLE_ROOT = os.path.dirname(_APP_DIR)
LOG_PATH = os.path.join(_PORTABLE_ROOT, "time_sync.log")
'@
if ($c.Contains($old)) { $c = $c.Replace($old, $new); Set-Content $hidApp $c -Encoding utf8; Ok "已改写 app/time_sync_hid.py 日志路径" }
else { Info "time_sync_hid.py 未匹配到原始 LOG_PATH 行 (可能已改), 跳过" }

# 5b) time_sync_config_gui.py : CONFIG / LOG_PATH -> 便携包根目录 (逐行稳健替换)
$guiApp = Join-Path $App "time_sync_config_gui.py"
$g = Get-Content $guiApp -Raw
$changed = $false
# 在 HERE 定义行后插入 PORTABLE_ROOT (仅插一次)
$hereLine = 'HERE = os.path.dirname(os.path.abspath(__file__))'
if ($g.Contains($hereLine) -and -not $g.Contains("PORTABLE_ROOT")) {
    $g = $g.Replace($hereLine, $hereLine + "`n# 便携版: 配置与日志写到便携包根目录 (app/ 的上级), 方便用户直接查看。`nPORTABLE_ROOT = os.path.dirname(HERE)")
    $changed = $true
}
$cfgOld = 'CONFIG = os.path.join(HERE, "time_sync_schedule.json")'
$cfgNew = 'CONFIG = os.path.join(PORTABLE_ROOT, "time_sync_schedule.json")'
if ($g.Contains($cfgOld)) { $g = $g.Replace($cfgOld, $cfgNew); $changed = $true }
$logOld = 'LOG_PATH = os.path.join(HERE, "time_sync.log")'
$logNew = 'LOG_PATH = os.path.join(PORTABLE_ROOT, "time_sync.log")'
if ($g.Contains($logOld)) { $g = $g.Replace($logOld, $logNew); $changed = $true }
if ($changed) { Set-Content $guiApp $g -Encoding utf8; Ok "已改写 app/time_sync_config_gui.py 配置/日志路径" }
else { Info "time_sync_config_gui.py 未匹配到路径行 (可能已改), 跳过" }

# ---- 6) 生成便携版启动 bat 与使用说明 --------------------------------------
$batSync = @'
@echo off
chcp 65001 >nul
rem ===== QK100 键盘时间校正 - 便携版: 立即校时一次 =====
rem %~dp0 = 本 bat 所在目录 (便携包根目录), 解包到任何位置都能用。
cd /d "%~dp0"
echo ============================================================
echo  QK100 键盘时间校正 - 立即校准为当前系统时间
echo ============================================================
echo.
"%~dp0runtime\python.exe" "%~dp0app\time_sync_hid.py" --quiet
echo.
echo ------------------------------------------------------------
echo  已发送。请检查键盘 TFT 屏时间是否已更新、键盘能否正常打字。
echo  结果也已写入 time_sync.log。
echo ------------------------------------------------------------
echo.
pause
'@
Set-Content -Path (Join-Path $Pkg "校时一次.bat") -Value $batSync -Encoding utf8

$batGui = @'
@echo off
chcp 65001 >nul
rem ===== QK100 键盘时间校正 - 便携版: 打开图形配置工具 =====
rem 设置 tcl/tk 库路径 (嵌入式 Python 跑 GUI 需要), 路径相对本 bat。
cd /d "%~dp0"
set "TCL_LIBRARY=%~dp0runtime\tcl\tcl8.6"
set "TK_LIBRARY=%~dp0runtime\tcl\tk8.6"
rem 用 pythonw.exe 启动 GUI, 无黑窗。
start "" "%~dp0runtime\pythonw.exe" "%~dp0app\time_sync_config_gui.py"
'@
Set-Content -Path (Join-Path $Pkg "打开配置.bat") -Value $batGui -Encoding utf8

$readme = @'
============================================================
 QK100 键盘时间校正 —— 便携版 使用说明
============================================================

这是一个「解包即用」的便携版本：包内自带 Python 运行时，
拷到任意一台 Windows 64 位电脑、解压后直接双击即可使用，
无需安装 Python、无需配置任何环境。


【目录里有什么】
------------------------------------------------------------
  校时一次.bat        ← 双击：立即把键盘时间校准为当前系统时间
  打开配置.bat        ← 双击：打开图形配置工具(设置每日定时 / 测试)
  runtime\            ← 自带的 Python 运行时(请勿删改、勿单独移动)
  app\                ← 程序脚本(请勿删改)
  使用说明.txt        ← 本文件
  time_sync.log       ← 运行后自动生成的日志
  time_sync_schedule.json ← 定时配置(应用设置后自动生成)


【怎么用 —— 最常见的两种】
------------------------------------------------------------
1) 只想立刻校一次时间：
   直接双击「校时一次.bat」，会弹出一个窗口显示发送过程，
   完成后检查键盘屏幕时间是否已更新。可随时重复。

2) 想设置「每天自动校时」或先测试一下：
   双击「打开配置.bat」，会打开图形界面，可以：
     - 勾选「启用每日自动校时」并添加时间点(如 09:00、18:00)，
       点「应用设置」即写入 Windows 计划任务，到点自动校时；
     - 点「测试」：发送一个明显不同的测试时间(2020-01-01 08:30:00)，
       用于确认程序与键盘通信正常(看屏幕是否跳到该值)；
     - 点「立即校时一次」：把时间校回当前系统时间；
     - 「刷新状态 / 查看日志」：查看已生效的定时任务与历史记录。

   ★ 建议首次使用先走一遍：测试 → 看屏幕跳到 2020-01-01
     → 再「立即校时一次」校回，即可验证「能写入 + 能恢复」整条链路。


【换电脑 / 换位置后的注意事项】★重要
------------------------------------------------------------
- 整个文件夹可以随意拷贝、改名、放到任意盘符路径，校时与 GUI 都能直接用
  (程序用相对自身位置定位运行时，不依赖固定路径)。

- 但「每日定时任务」是登记在 Windows 系统里的，不随文件夹一起拷走。
  所以拷到新电脑(或移动到新位置)后，如果要用「定时」功能，
  需要在新电脑上打开「打开配置.bat」，重新点一次「应用设置」即可，
  程序会按新位置自动重建定时任务。

- 校时一次、测试、打开 GUI —— 这些拷过去都能立即用，无需任何额外操作。


【常见问题】
------------------------------------------------------------
Q: 双击 bat 中文显示乱码？
A: 不影响功能。若想正常显示，可右键 bat「编辑」确认，或直接用 GUI。

Q: 提示找不到键盘 / 发送失败？
A: 确认键盘已连接(有线模式或无线接收器已插好)，再重试。

Q: 杀毒软件拦截？
A: 本工具仅做本地 HID 通信与创建计划任务，无网络行为，可放心放行。

Q: 能在 32 位系统用吗？
A: 不能。本便携版自带的是 64 位 Python 运行时，需 64 位 Windows。


【适用机型】
------------------------------------------------------------
  QK100 键盘 (VID=05AC, PID=024F, 命令通道 MI_03 / usage_page=0xFF13)
'@
Set-Content -Path (Join-Path $Pkg "使用说明.txt") -Value $readme -Encoding utf8
Ok "便携版 bat 与使用说明已生成"

# ---- 7) 压缩成单个 zip ------------------------------------------------------
# 清理可能的缓存
Get-ChildItem $Pkg -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
$ZipPath = Join-Path $OutDir "$PkgName.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path $Pkg -DestinationPath $ZipPath -CompressionLevel Optimal
$sizeMB = [math]::Round((Get-Item $ZipPath).Length / 1MB, 2)
Ok "打包完成: $ZipPath ($sizeMB MB)"

# ---- 收尾 ------------------------------------------------------------------
Info "构建工作区保留在: $Work (可手动删除)"
Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host " 便携版构建成功! / Portable build complete!" -ForegroundColor Green
Write-Host "  -> $ZipPath" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
