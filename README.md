# QK100 Keyboard Time Sync · QK100 键盘时间校正

> Sync the TFT clock on a QK100 keyboard to your system time in seconds — directly
> over HID, with no official app, no image-recognition clicking, and no screen unlock.
>
> 通过 HID 直发，几秒把 QK100 键盘 TFT 屏上的时钟校准为系统时间——不启动官方程序、
> 不做图像识别点击、不需要解锁屏幕交互。

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows%2064--bit-blue.svg)
![Python](https://img.shields.io/badge/python-3.10-blue.svg)

**Language / 语言:** [English](#english) · [中文](#中文)

---

<a name="english"></a>
## English

### What it does

This tool replays the exact HID Feature Report sequence that the official
`DeviceDriver.exe` sends when performing a "time correction", but substitutes the
current system time. It talks straight to the keyboard's vendor command channel
(`MI_03`, `usage_page = 0xFF13`) and finishes in a couple of seconds.

The protocol was reverse-engineered via passive frida capture. See
[`docs/protocol.md`](./docs/protocol.md) for the full sequence and time-field encoding.

### Two ways to use it

#### Option A — Portable (no Python needed) ⭐ recommended for end users

Download `QK100时间校正-便携版.zip` from the
[**Releases**](../../releases) page, unzip anywhere, and double-click:

| File | Action |
|------|--------|
| `校时一次.bat` | Sync the keyboard clock to current system time, right now |
| `打开配置.bat` | Open the GUI (daily auto-sync scheduling / test) |

The zip bundles an embedded Python runtime (with tkinter + hid), so **no
installation is required**. Windows 64-bit only.

> Note: the daily scheduled task is registered in Windows, so it does **not**
> travel with the folder. After copying to a new PC, open the GUI once and click
> "Apply" to recreate the task at the new location.

#### Option B — From source (you have Python 3.10)

```powershell
# 1) install the only runtime dependency
pip install hid

# 2) clone
git clone https://github.com/fruityman/QK100-Keyboard-Time-Sync.git
cd QK100-Keyboard-Time-Sync/src

# 3) preview the bytes WITHOUT sending (safe dry-run)
python time_sync_hid.py

# 4) actually sync to current system time
python time_sync_hid.py --send --backend ctypes
```

Or just double-click `src/run_time_sync.bat` (sync once) /
`src/打开定时配置.bat` (open GUI).

### Command-line options

| Option | Effect |
|--------|--------|
| *(no `--send`)* | **Dry-run**: print bytes only, don't write to device |
| `--send` | Actually send to the keyboard |
| `--backend ctypes` | Write backend (default): `CreateFileW` + `HidD_SetFeature`, identical to official |
| `--backend hidapi` | Use hidapi's `send_feature_report` (fallback) |
| `--time "YYYY-MM-DD HH:MM:SS"` | Write a specific time (e.g. to verify the screen changes) |
| `--gap 0.012` | Seconds between commands (official ~12 ms) |
| `--quiet` | Silent mode for scheduled tasks (implies `--send`, no countdown) |
| `--no-readback` | Disable write-then-read-back handshake (**not recommended** — commands won't take effect) |

### Auto-sync (GUI)

Because this method needs no screen interaction, it can run safely as a Windows
Scheduled Task. The GUI (`打开配置.bat` / `time_sync_config_gui.py`) lets you:

- toggle daily auto-sync on/off and add multiple time points (e.g. `09:00`, `18:00`);
- **Apply** to write the schedule into Windows Task Scheduler;
- **Sync now** instantly; **Test** by writing `2020-01-01 08:30:00` so you can
  confirm the screen jumps; **Refresh / View log**.

> Recommended first run: **Test** → watch the screen jump to 2020-01-01 →
> **Sync now** to restore current time. This verifies the full write+restore path.

Scheduled tasks run `pythonw.exe time_sync_hid.py --quiet` — no console window,
~1–2 s, and nothing stays resident (zero idle overhead).

### Building the portable zip yourself

```powershell
# requires a local Python 3.10 (with tkinter) and: pip install hid
powershell -ExecutionPolicy Bypass -File build/build_portable.ps1
```

This downloads the embedded Python, harvests tkinter + hid from your local 3.10,
rewrites paths, generates the launchers, and produces `QK100时间校正-便携版.zip`.
See [`build/build_portable.ps1`](./build/build_portable.ps1) for parameters.

### Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| "command channel not found" | Keyboard not connected, or not in wired/receiver mode. Reconnect. |
| "CreateFileW open device failed" | Interface held exclusively / permission. Try running as admin. |
| Sent OK but screen unchanged | Make sure `--no-readback` is NOT used (read-back is the key). |
| Keyboard misbehaves | Unplug USB / pull battery to reset, then sync again. |

### Repository layout

```
QK100-Keyboard-Time-Sync/
├─ src/                       # source (use directly if you have Python)
│   ├─ time_sync_hid.py       # core: HID direct-write time sync
│   ├─ time_sync_config_gui.py# GUI scheduler
│   ├─ run_time_sync.bat      # double-click: sync once
│   └─ 打开定时配置.bat        # double-click: open GUI
├─ docs/
│   ├─ protocol.md            # HID protocol (reverse-engineered)
│   └─ capture_packets.txt    # raw frida capture archive
├─ tools/                     # capture / debug helpers
│   ├─ hid_sniff_frida.py
│   ├─ hid_enum.py
│   └─ hid_probe.py
├─ build/
│   └─ build_portable.ps1     # one-click portable build
├─ README.md  ·  LICENSE  ·  CHANGELOG.md  ·  .gitignore
```

### Disclaimer

> **This is an unofficial, third-party tool provided for learning and personal use,
> with NO warranty of any kind.** It interacts with a private HID protocol that was
> reverse-engineered and may change with firmware updates. Writing directly to HID
> devices carries inherent risk; in rare cases a keyboard may stop responding
> (recoverable by unplugging USB / removing the battery to reset). **Use at your own
> risk.** This project is not affiliated with, authorized by, or endorsed by the
> keyboard manufacturer. All trademarks belong to their respective owners. The
> authors are not liable for any damage arising from use of this software.

### License

[MIT](./LICENSE). The portable build additionally bundles third-party components
(CPython, Tcl/Tk, hidapi/`hid`), each under its own license.

---

<a name="中文"></a>
## 中文

### 它是做什么的

本工具复刻官方 `DeviceDriver.exe` 执行一次「时间校正」时发出的 HID Feature Report
序列，只把其中的时间字段换成当前系统时间。它直接与键盘的厂商命令通道
（`MI_03`，`usage_page = 0xFF13`）通信，几秒完成。

协议通过 frida 被动抓包逆向得到，完整序列与时间字段编码见
[`docs/protocol.md`](./docs/protocol.md)。

### 两种使用方式

#### 方式 A — 便携版（无需 Python）⭐ 推荐给普通用户

在 [**Releases**](../../releases) 页面下载 `QK100时间校正-便携版.zip`，
解压到任意位置，然后双击：

| 文件 | 作用 |
|------|------|
| `校时一次.bat` | 立即把键盘时钟校准为当前系统时间 |
| `打开配置.bat` | 打开图形界面（设置每日自动校时 / 测试） |

zip 内自带 Python 运行时（含 tkinter + hid），**无需安装**。仅支持 64 位 Windows。

> 注意：每日定时任务登记在 Windows 系统里，**不随文件夹一起拷走**。拷到新电脑后，
> 打开 GUI 点一次「应用设置」，即可按新位置重建定时任务。

#### 方式 B — 从源码运行（已装 Python 3.10）

```powershell
# 1) 安装唯一的运行依赖
pip install hid

# 2) 克隆
git clone https://github.com/fruityman/QK100-Keyboard-Time-Sync.git
cd QK100-Keyboard-Time-Sync/src

# 3) 干跑预览，不发送（安全）
python time_sync_hid.py

# 4) 真正校准为当前系统时间
python time_sync_hid.py --send --backend ctypes
```

也可直接双击 `src/run_time_sync.bat`（校时一次）/ `src/打开定时配置.bat`（打开 GUI）。

### 命令行参数

| 参数 | 作用 |
|------|------|
| *(不加 `--send`)* | **干跑**：只打印将发送的字节，不写入设备 |
| `--send` | 真正发送到键盘 |
| `--backend ctypes` | 写入后端（默认）：`CreateFileW` + `HidD_SetFeature`，与官方一致 |
| `--backend hidapi` | 改用 hidapi 的 `send_feature_report`（备用） |
| `--time "YYYY-MM-DD HH:MM:SS"` | 写入指定时间（如用于验证屏幕跳变） |
| `--gap 0.012` | 相邻命令间隔秒数（官方约 12 ms） |
| `--quiet` | 定时任务用的静默模式（隐含 `--send`，无倒计时） |
| `--no-readback` | 关闭写后读回握手（**不建议**，关掉后命令不生效） |

### 自动校时（图形工具）

由于本方案不依赖屏幕交互，可安全交给 Windows 计划任务后台静默运行。GUI
（`打开配置.bat` / `time_sync_config_gui.py`）可以：

- 开关每日自动校时，并添加多个时间点（如 `09:00`、`18:00`）；
- 点「应用设置」把配置写入 Windows 计划任务；
- 「立即校时一次」即时校准；「测试」写入 `2020-01-01 08:30:00` 用于确认屏幕跳变；
  「刷新状态 / 查看日志」。

> 建议首次使用先走一遍：**测试** → 看屏幕跳到 2020-01-01 → **立即校时一次** 校回当前
> 时间，即可完整验证「能写入 + 能恢复」整条链路。

定时任务以 `pythonw.exe time_sync_hid.py --quiet` 运行——无黑窗、约 1–2 秒、不驻留
（平时零开销）。

### 自己构建便携版 zip

```powershell
# 需要本机有 Python 3.10 (含 tkinter), 并: pip install hid
powershell -ExecutionPolicy Bypass -File build/build_portable.ps1
```

脚本会下载嵌入式 Python，从本机 3.10 提取 tkinter + hid，改写路径，生成启动器，
并产出 `QK100时间校正-便携版.zip`。参数见 [`build/build_portable.ps1`](./build/build_portable.ps1)。

### 排查

| 现象 | 原因 / 处理 |
|------|------|
| 未找到命令通道接口 | 键盘没连接，或不在有线/接收器模式，插好后重试 |
| CreateFileW 打开设备失败 | 接口被独占或权限不足，可用管理员身份运行 |
| 发送成功但屏幕没变 | 确认没有加 `--no-readback`（读回握手是生效关键） |
| 键盘异常 | 立即拔 USB / 拔电池复位，再重新校时 |

### 目录结构

见上方英文部分「Repository layout」。

### 免责声明

> **本工具为非官方第三方工具，仅供学习与个人使用，不提供任何形式的担保。** 它操作的是
> 通过逆向得到的私有 HID 协议，可能随固件升级而变化；直接写入 HID 设备本身存在风险，
> 极少数情况下键盘可能出现无响应（可通过拔 USB / 拔电池复位恢复）。**使用风险自负。**
> 本项目与键盘厂商无任何关联，未获其授权或认可；所有商标归各自所有者。作者不对因使用
> 本软件造成的任何损失承担责任。

### 许可证

[MIT](./LICENSE)。便携版额外打包了第三方组件（CPython、Tcl/Tk、hidapi/`hid`），
各自遵循其原始许可证。
