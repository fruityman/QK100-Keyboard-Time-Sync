# -*- coding: utf-8 -*-
"""
QK100 时间校正 —— HID 直发版 (谨慎复刻官方完整序列)
====================================================

背景
----
通过 frida 被动抓包,完整捕获了官方程序 DeviceDriver.exe 执行一次
"时间校正"时,经 HidD_SetFeature(IOCTL_HID_SET_FEATURE=0xb0191) 向
键盘命令通道发出的全部写入序列(见 capture_packets.txt)。

本脚本严格复刻官方那 8 条 Feature Report 写入,只把其中第 3 条的
时间字段替换为"当前系统时间"。除时间数值外,每个字节都与官方一致。

安全设计 (吸取上次键盘被写挂、需拔电池复位的教训)
------------------------------------------------
1. 默认 dry-run: 不加 --send 时只打印将发送的字节,绝不写入设备。
2. --send 才真发,且发送后立即暂停,提示你检查键盘是否仍正常。
3. 只打开官方使用的同一接口: MI_03 / usage_page=0xFF13。
4. 通道与长度: Feature Report,共 65 字节(首字节为 report-id 0x00)。

时间字段编码 (抓包实测确认: 纯数值, 非 BCD)
------------------------------------------
抓包基准: 2026-06-25 17:23:54 周四
原文(去 report-id 后): 5A 00 5A 1A 06 19 11 17 36 00 04 ... AA 55

逐字段验证 (字节的十六进制【值】 == 十进制真实值):
  报告体偏移        值      含义
  body[1..3] = 5A 00 5A    命令头(设置时间)
  body[4]    = 0x1A = 26   年(后两位)   26       -> 0x1A
  body[5]    = 0x06 = 6    月            6        -> 0x06
  body[6]    = 0x19 = 25   日            25       -> 0x19
  body[7]    = 0x11 = 17   时            17       -> 0x11
  body[8]    = 0x17 = 23   分            23       -> 0x17
  body[9]    = 0x36 = 54   秒            54       -> 0x36
  body[10]   = 0x00        固定 00
  body[11]   = 0x04 = 4    星期(周一=1..周日=7), 2026-06-25 是周四 = 4
  body[12..] = 00 填充
  body[末2]  = AA 55       包尾标记

关键: 这【不是 BCD】。每个字段就是把十进制真实值当作一个字节存入,
      因此 Python 里直接 body[i] = 真实十进制值 即可
      (例如 day=25 -> 字节 0x19, second=54 -> 字节 0x36)。
"""
import os
import sys
import time
import datetime
import argparse

VID = 0x05AC
PID = 0x024F
TARGET_USAGE_PAGE = 0xFF13   # MI_03 vendor-defined 命令通道(官方所用)
REPORT_LEN = 65              # 含首字节 report-id 0x00

# ---------------------------------------------------------------------------
# 官方完整 8 条写入序列模板 (来自 capture_packets.txt 逐字节复刻)
# 每条均为 65 字节,首字节 0x00 为 report-id。
# 第 3 条 (TIME) 的时间字段会在运行时按当前时间替换。
# ---------------------------------------------------------------------------

def _pad(hexstr, total=REPORT_LEN, tail=b""):
    """把给定的前缀 hex 字节用 0x00 填充到 total 长度;tail 为尾部固定字节。"""
    head = bytes.fromhex(hexstr.replace(" ", ""))
    body_len = total - len(tail)
    if len(head) > body_len:
        raise ValueError("head too long")
    return head + bytes(body_len - len(head)) + tail


# 抓包原文(去重后的 8 条真实写入,严格按时间戳顺序):
#  1) 00 04 18 ...
#  2) 00 04 28 ... (offset9=01)
#  3) 00 5A 00 5A [YY MM DD HH MM SS] 00 [WD] ... AA 55   <- 设置时间
#  4) 00 04 02 ...
#  5) 00 04 18 ...
#  6) 00 04 17 ... (offset9=01)
#  7) 00 00 00 00 00 00 00 02 07 02 ... AA 55             <- 状态/读回
#  8) 00 04 02 ...

PKT1_ENTER_A   = _pad("00 04 18")
PKT2_SUB_28    = bytes.fromhex(
    "00 04 28 00 00 00 00 00 00 01".replace(" ", "")
) + bytes(REPORT_LEN - 10)
PKT4_COMMIT    = _pad("00 04 02")
PKT5_ENTER_B   = _pad("00 04 18")
PKT6_SUB_17    = bytes.fromhex(
    "00 04 17 00 00 00 00 00 00 01".replace(" ", "")
) + bytes(REPORT_LEN - 10)
PKT7_STATUS    = bytes.fromhex(
    "00 00 00 00 00 00 00 02 07 02".replace(" ", "")
) + bytes(REPORT_LEN - 2 - 10) + bytes.fromhex("AA55")
PKT8_COMMIT    = _pad("00 04 02")


def build_time_packet(dt):
    """
    构造第 3 条"设置时间"包 (65 字节)。
    时间字段为【纯数值】编码(非 BCD): 直接把十进制真实值存入对应字节。
    例如 day=25 -> 0x19, second=54 -> 0x36 (详见模块顶部 docstring 的逐字段验证)。
    """
    yy = dt.year % 100          # 后两位, 2026 -> 26
    mo = dt.month
    da = dt.day
    hh = dt.hour
    mi = dt.minute
    ss = dt.second
    wd = dt.isoweekday()        # 周一=1 .. 周日=7

    body = bytearray(REPORT_LEN)
    body[0] = 0x00              # report-id
    body[1] = 0x5A
    body[2] = 0x00
    body[3] = 0x5A
    body[4] = yy                # 年(后两位)的真实数值
    body[5] = mo                # 月
    body[6] = da                # 日
    body[7] = hh                # 时
    body[8] = mi                # 分
    body[9] = ss                # 秒
    body[10] = 0x00             # 固定 00
    body[11] = wd               # 星期
    # 中间全 00
    body[REPORT_LEN - 2] = 0xAA
    body[REPORT_LEN - 1] = 0x55
    return bytes(body)


def hexs(b):
    return " ".join(f"{x:02X}" for x in bytes(b))


LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "time_sync.log")
# 当天去重标记文件: 记录最近一次成功校时的日期 (YYYY-MM-DD)。
STAMP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".last_sync_date")

# 来源标记 -> 日志中显示的中文说明
_SOURCE_LABELS = {
    "schedule": "定时校时",
    "boot": "开机校时",
    "wake": "唤醒校时",
    "manual": "手动校时",
}


def _source_label(source):
    return _SOURCE_LABELS.get(source, "静默校时")


def _already_synced_today():
    """若今日已成功校时过, 返回 True。用于开机/唤醒任务当天去重。"""
    try:
        if not os.path.exists(STAMP_PATH):
            return False
        with open(STAMP_PATH, "r", encoding="utf-8") as f:
            last = f.read().strip()
        return last == datetime.date.today().isoformat()
    except Exception:
        return False


def _mark_synced_today():
    """记录今日已校时 (写入日期戳文件)。"""
    try:
        with open(STAMP_PATH, "w", encoding="utf-8") as f:
            f.write(datetime.date.today().isoformat())
    except Exception:
        pass


def _log_skipped(source):
    """当天去重命中时, 记录一条跳过日志。"""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{stamp}] {_source_label(source)}({source}) -> 今日已校时, 跳过\n")
    except Exception:
        pass


def _log_result(quiet, dt, ok, err, source="schedule"):
    """静默模式把每次校时结果追加写入 time_sync.log。"""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status = "成功" if ok else f"失败({err})"
            f.write(f"[{stamp}] {_source_label(source)}({source}) -> "
                    f"写入 {dt:%Y-%m-%d %H:%M:%S} : {status}\n")
    except Exception:
        pass


def find_target_path():
    """枚举定位 MI_03 / usage_page=0xFF13 命令通道,返回设备路径(bytes)。"""
    import hid
    for d in hid.enumerate(VID, PID):
        if d.get("usage_page", 0) == TARGET_USAGE_PAGE:
            return d["path"]
    raise RuntimeError(
        f"未找到命令通道接口 (VID={VID:04X} PID={PID:04X} "
        f"usage_page=0x{TARGET_USAGE_PAGE:04X})。键盘是否连接/有线模式?"
    )


def open_target():
    """[hidapi 后端] 打开命令通道。返回 (hid.device, path)。"""
    import hid
    path = find_target_path()
    h = hid.device()
    h.open_path(path)
    return h, path


# ---------------------------------------------------------------------------
# ctypes 后端: 直接复刻官方调用 —— CreateFileW 打开设备, HidD_SetFeature 写入。
# 这与官方 DeviceDriver.exe 的底层调用完全一致(裸 65 字节, report-id 在首字节)。
# ---------------------------------------------------------------------------
class CtypesHidDevice:
    def __init__(self, path):
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        self.wintypes = wintypes

        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        FILE_SHARE_READ = 0x00000001
        FILE_SHARE_WRITE = 0x00000002
        OPEN_EXISTING = 3

        if isinstance(path, bytes):
            path_str = path.decode("ascii", "ignore")
        else:
            path_str = path

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.k32 = k32
        CreateFileW = k32.CreateFileW
        CreateFileW.restype = wintypes.HANDLE
        CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                wintypes.HANDLE]

        h = CreateFileW(path_str,
                        GENERIC_READ | GENERIC_WRITE,
                        FILE_SHARE_READ | FILE_SHARE_WRITE,
                        None, OPEN_EXISTING, 0, None)
        if h == wintypes.HANDLE(-1).value or h is None:
            err = ctypes.get_last_error()
            raise OSError(f"CreateFileW 打开设备失败, GetLastError={err}")
        self.handle = h

        hid_dll = ctypes.WinDLL("hid", use_last_error=True)
        self.hid_dll = hid_dll
        self.HidD_SetFeature = hid_dll.HidD_SetFeature
        self.HidD_SetFeature.restype = wintypes.BOOLEAN
        self.HidD_SetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
        # 写后读回握手需要的 HidD_GetFeature
        self.HidD_GetFeature = hid_dll.HidD_GetFeature
        self.HidD_GetFeature.restype = wintypes.BOOLEAN
        self.HidD_GetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]

    def send_feature_report(self, data):
        ctypes = self.ctypes
        buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(bytes(data))
        ok = self.HidD_SetFeature(self.handle, buf, len(data))
        if not ok:
            err = ctypes.get_last_error()
            raise OSError(f"HidD_SetFeature 失败, GetLastError={err}")
        return len(data)

    def get_feature_report(self, report_id, length):
        """读回 Feature Report (官方每写一条后都做这个握手)。返回 list[int]。"""
        ctypes = self.ctypes
        buf = (ctypes.c_ubyte * length)()
        buf[0] = report_id & 0xFF
        ok = self.HidD_GetFeature(self.handle, buf, length)
        if not ok:
            err = ctypes.get_last_error()
            raise OSError(f"HidD_GetFeature 失败, GetLastError={err}")
        return list(buf)

    def close(self):
        try:
            self.k32.CloseHandle(self.handle)
        except Exception:
            pass


def open_target_ctypes():
    """[ctypes 后端] 用 CreateFileW+HidD_SetFeature 打开命令通道。返回 (dev, path)。"""
    path = find_target_path()
    return CtypesHidDevice(path), path


def build_sequence(dt):
    """返回官方完整 8 条写入序列 (按发送顺序)。"""
    return [
        ("1 进入模式A (04 18)", PKT1_ENTER_A),
        ("2 子命令 (04 28)",     PKT2_SUB_28),
        ("3 ★设置时间",          build_time_packet(dt)),
        ("4 提交 (04 02)",       PKT4_COMMIT),
        ("5 进入模式B (04 18)",  PKT5_ENTER_B),
        ("6 子命令 (04 17)",     PKT6_SUB_17),
        ("7 状态/读回 (02 07 02)", PKT7_STATUS),
        ("8 提交 (04 02)",       PKT8_COMMIT),
    ]


def main():
    ap = argparse.ArgumentParser(description="QK100 时间校正 HID 直发 (默认 dry-run)")
    ap.add_argument("--send", action="store_true",
                    help="真正发送到键盘 (不加此参数则仅打印,不写入)")
    ap.add_argument("--gap", type=float, default=0.012,
                    help="相邻命令间隔秒数 (官方实测约 12ms),默认 0.012")
    ap.add_argument("--no-readback", action="store_true",
                    help="不做写后读回握手 (默认会读回,复刻官方 写一条->读一条 的时序)")
    ap.add_argument("--backend", choices=["ctypes", "hidapi"], default="ctypes",
                    help="写入后端: ctypes=直调 CreateFileW+HidD_SetFeature(完全复刻官方,默认); "
                         "hidapi=用 hidapi 的 send_feature_report")
    ap.add_argument("--time", dest="time_str", default=None,
                    help="指定要写入的时间(用于验证命令是否生效),格式 "
                         "'YYYY-MM-DD HH:MM:SS'。不加则用当前系统时间。"
                         "验证时建议设一个明显与当前不同的值,如 '2020-01-01 08:30:00'")
    ap.add_argument("--quiet", action="store_true",
                    help="静默模式(供计划任务调用): 跳过 3 秒倒计时和交互提示,"
                         "结果写入 time_sync.log。隐含 --send。")
    ap.add_argument("--source", dest="source", default="schedule",
                    help="校时来源标记, 写入日志用于区分触发方式: "
                         "schedule=每日定时(默认), boot=开机/登录, wake=睡眠唤醒, manual=手动。")
    ap.add_argument("--once-per-day", action="store_true",
                    help="当天去重: 若今日已成功校时过则直接跳过 (供开机/唤醒任务调用, "
                         "保证一天最多触发一次)。")
    args = ap.parse_args()
    if args.quiet:
        args.send = True

    # 当天去重: 开机与唤醒可能在同一天各触发一次, 用日期戳文件保证一天只校一次。
    if args.once_per_day and _already_synced_today():
        _log_skipped(args.source)
        return 0

    if args.time_str:
        try:
            now = datetime.datetime.strptime(args.time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            print(f"[错误] --time 格式应为 'YYYY-MM-DD HH:MM:SS',你传入: {args.time_str!r}")
            return 2
    else:
        now = datetime.datetime.now()
    seq = build_sequence(now)

    print("=" * 64)
    print(f"目标设备 : VID={VID:04X} PID={PID:04X} usage_page=0x{TARGET_USAGE_PAGE:04X} (MI_03)")
    src = "指定测试时间 (--time)" if args.time_str else "当前系统时间"
    print(f"写入时间 : {now:%Y-%m-%d %H:%M:%S} (周{now.isoweekday()})  [{src}]")
    print(f"模式     : {'真实发送 (--send)' if args.send else 'DRY-RUN 仅打印,不发送'}")
    print(f"写入后端 : {args.backend}")
    print(f"序列长度 : {len(seq)} 条 Feature Report (各 {REPORT_LEN} 字节)")
    print("=" * 64)
    for name, pkt in seq:
        assert len(pkt) == REPORT_LEN, f"{name} 长度异常: {len(pkt)}"
        print(f"[{name}]")
        print(f"    {hexs(pkt)}")
    # 单独高亮时间包解码
    tp = seq[2][1]
    print("-" * 64)
    print("时间包字段解码 (去 report-id 后):")
    print(f"    头 5A 00 5A | 年={tp[4]} 月={tp[5]} 日={tp[6]} "
          f"时={tp[7]} 分={tp[8]} 秒={tp[9]} | 固定={tp[10]} 周={tp[11]} | 尾 AA 55")
    print("=" * 64)

    if not args.send:
        print("\n[DRY-RUN] 未发送任何数据。确认上面字节无误后,加 --send 真正发送。")
        return 0

    # ---- 真实发送 ----
    if not args.quiet:
        print("\n[!] 即将真实发送到键盘。3 秒后开始,请把手放在键盘电池/USB 旁待命...")
        for i in (3, 2, 1):
            print(f"    {i} ...")
            time.sleep(1.0)

    try:
        import hid  # noqa
    except Exception as e:
        print("import hid 失败:", e)
        return 2

    h = None
    ok_all = False
    try:
        if args.backend == "ctypes":
            h, path = open_target_ctypes()
        else:
            h, path = open_target()
        print(f"[已打开] ({args.backend}) {path}")
        for idx, (name, pkt) in enumerate(seq, 1):
            n = h.send_feature_report(pkt)
            print(f"  -> 发送第 {idx} 条 [{name}] 写入字节={n}")
            # 写后读回握手: 官方每条 HidD_SetFeature 后都跟一条 IOCTL_HID_GET_FEATURE。
            # 固件状态机可能依赖这个读回才推进,缺它则整个序列空转。
            if not args.no_readback:
                try:
                    rb = h.get_feature_report(0x00, REPORT_LEN)
                    print(f"        读回: {hexs(rb)}")
                except Exception as e:
                    print(f"        [读回失败,继续] {e}")
            time.sleep(args.gap)
        print("\n[完成] 8 条序列已全部发送。")
        ok_all = True
    except Exception as e:
        print(f"[发送出错] {e}")
        _log_result(args.quiet, now, False, str(e), args.source)
        return 1
    finally:
        if h is not None:
            try:
                h.close()
            except Exception:
                pass

    if args.quiet:
        _log_result(args.quiet, now, ok_all, "", args.source)
        if ok_all:
            _mark_synced_today()   # 记录当天已校时, 供开机/唤醒去重
        return 0

    print("\n" + "!" * 64)
    print("请立即检查键盘:")
    print("  1) 键盘能否正常打字? (按几个键试试)")
    print("  2) TFT 屏上的时间是否已更新为当前系统时间?")
    print("  3) 如有任何异常 (无响应/卡死),立即拔电池或拔 USB 复位。")
    print("!" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
