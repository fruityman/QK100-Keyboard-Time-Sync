# Changelog

All notable changes to this project are documented here.
本项目所有重要变更记录于此。

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [1.0.1] - 2026-06-30

### Fixed / 修复
- Portable build no longer garbles Chinese characters in the bundled Python
  scripts. The build script (`build/build_portable.ps1`) previously read the
  UTF-8 sources via `Get-Content -Raw` (decoded as GBK on Chinese Windows) and
  wrote them back with `Set-Content -Encoding utf8` (added a BOM), corrupting
  all Chinese text and breaking the scripts at runtime. It now reads/writes all
  generated files (py / bat / txt) as UTF-8 **without BOM**.
  修复便携版打包后 `app/` 内 Python 脚本中文乱码导致脚本无法运行的问题：
  构建脚本原先用 `Get-Content -Raw`（中文系统按 GBK 误解码）读取 UTF-8 源文件，
  再用 `Set-Content -Encoding utf8`（写入 BOM）写回，导致中文全部损坏。现统一
  以 **UTF-8 无 BOM** 读写所有生成文件（py / bat / txt）。

## [1.0.0] - 2026-06-26

### Added / 新增
- HID direct-write time sync (`time_sync_hid.py`): replays the official
  keyboard command sequence over HID Feature Reports to set the TFT clock.
  HID 直发校时核心脚本：通过 HID Feature Report 复刻官方指令序列校准键盘 TFT 时钟。
- GUI scheduler (`time_sync_config_gui.py`): enable/disable daily auto-sync,
  multiple time points, instant sync, and a test action.
  图形定时配置工具：每日自动校时开关、多时间点、立即校时、测试。
- One-click launchers (`run_time_sync.bat`, `打开定时配置.bat`).
  一键启动器。
- Portable build script (`build/build_portable.ps1`) that bundles an embedded
  Python runtime (with tkinter + hid) into a ready-to-run zip.
  便携版一键构建脚本：打包内嵌 Python 运行时生成开箱即用 zip。
- Protocol documentation (`docs/protocol.md`) and frida capture archive.
  协议文档与抓包存档。

[1.0.1]: https://github.com/fruityman/QK100-Keyboard-Time-Sync/releases/tag/v1.0.1
[1.0.0]: https://github.com/fruityman/QK100-Keyboard-Time-Sync/releases/tag/v1.0.0
