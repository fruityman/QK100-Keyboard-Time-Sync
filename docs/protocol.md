# QK100 HID Time-Sync Protocol / QK100 HID 校时协议

> Reverse-engineered from the official `DeviceDriver.exe` via passive frida capture.
> 通过 frida 被动抓包，逆向官方 `DeviceDriver.exe` 的一次「时间校正」操作得出。
>
> Raw capture archive: [`capture_packets.txt`](./capture_packets.txt)

---

## 1. Device / 设备

| Item | Value |
|------|-------|
| Vendor ID (VID) | `0x05AC` |
| Product ID (PID) | `0x024F` |
| Command interface | `MI_03` |
| Usage Page | `0xFF13` (vendor-defined command channel) |
| Report length | 65 bytes (1 report-id + 64 payload) |

The tool enumerates HID interfaces and opens the one whose `usage_page == 0xFF13`.
工具会枚举 HID 接口并打开 `usage_page == 0xFF13` 的命令通道接口。

---

## 2. Command sequence / 指令序列

To set the clock, the official driver sends **8 Feature Reports** in order, each
65 bytes. After **each** write it immediately performs **one read-back**.

校时时，官方驱动按顺序发送 **8 条 Feature Report**（各 65 字节），并在**每条写入后立即读回一次**。

```
Open command channel (VID=05AC PID=024F, usage_page=0xFF13, MI_03)
  -> send 8 Feature Reports (65 bytes each):
       1  Enter mode A     (04 18)
       2  Sub-command      (04 28)
       3  ★ Set time       (5A 00 5A | YY MM DD HH MM SS | 00 WD | AA 55)
       4  Commit           (04 02)
       5  Enter mode B     (04 18)
       6  Sub-command      (04 17)
       7  Status packet    (02 07 02 ... AA 55)
       8  Commit           (04 02)
  -> after each write, immediately do one HidD_GetFeature (read-back handshake)
  -> done, keyboard clock updated
```

### ★ Critical: write-then-read-back handshake / 关键：写后读回握手

> The firmware state machine advances **only** when each `HidD_SetFeature` (write)
> is immediately followed by a `HidD_GetFeature` (read-back).
> 固件状态机依赖每条写入后紧跟一条读回来推进。
>
> Write-only (no read-back) makes the commands **silently fail** (state machine
> spins in place). Adding the read-back makes the time update immediately.
> 只写不读会导致命令完全不生效；补上读回后时间立即更新。

This is implemented by the `--no-readback` flag being **off** by default; do not
turn it off except for controlled experiments.
代码默认开启读回握手；除对照实验外不要用 `--no-readback` 关闭它。

---

## 3. Time field encoding / 时间字段编码

The set-time packet (report-id stripped) is:
去掉 report-id 后的时间包为：

```
5A 00 5A [YY MM DD HH MM SS] 00 [WD] ... AA 55
```

Each field stores the **decimal value directly as one byte** — it is **NOT BCD**
(verified by capture).
每个字段直接把**十进制真实值当作一个字节**存入，**不是 BCD**（抓包实测确认）。

| Field / 字段 | Meaning / 说明 | Example (2026-06-25 18:56:54, Thu) |
|------|------|------|
| YY (年) | last two digits / 年份后两位 | `26` |
| MM (月) | 1–12 | `06` |
| DD (日) | 1–31 | `25` |
| HH (时) | 0–23 | `18` |
| MM (分) | 0–59 | `56` |
| SS (秒) | 0–59 | `54` |
| WD (周) | Mon=1 … Sun=7 / 周一=1…周日=7 | `04` |

---

## 4. Re-capturing after a firmware change / 固件升级后重新抓包

If a firmware update changes the sequence, re-capture passively and diff:
如果固件升级导致序列变化，可被动重新抓包后比对：

```powershell
python tools/hid_sniff_frida.py
```

Then update the sequence templates in `src/time_sync_hid.py`.
然后更新 `src/time_sync_hid.py` 中的序列模板。
