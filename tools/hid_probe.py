# -*- coding: utf-8 -*-
"""
HID 命令通道探测器(逆向第二步)。

利用 SnxHidLib.ini 里已知的设备识别命令:
    CheckDeviceCmd = AA 42 89 5A FF 71 62 CC   (8 字节)

策略:对 QK100 的每个 vendor-defined 接口,尝试用不同方式发送这条命令,
并读回响应。能收到合理响应的接口,就是配置软件用来收发命令的通道。

只发送厂商自带的"问询/识别"命令,不写入任何配置 → 安全的只读探测。

会尝试的写入方式(逐一试,记录哪种有回应):
  A) write([report_id=0x00] + cmd + padding)   普通 output report
  B) send_feature_report([0x00] + cmd + padding) feature report
不同固件二选一,这里都试。
"""
import sys
import time

VID = 0x05AC
PID = 0x024F

# 已知设备识别命令
CHECK_CMD = bytes.fromhex("AA42895AFF7162CC")

# 候选 vendor 接口的 usage_page(从枚举结果挑出的 0xFFxx 私有页)
VENDOR_PAGES = [0xFF13, 0xFFFF, 0xFF68]

# 常见 report 总长度(含可能的 report-id 字节),逐一尝试
TRY_LENS = [65, 64, 33, 32, 9, 8]


def hexs(b):
    return " ".join(f"{x:02X}" for x in bytes(b))


def list_targets():
    import hid
    targets = []
    for d in hid.enumerate(VID, PID):
        up = d.get("usage_page", 0)
        if up in VENDOR_PAGES:
            targets.append(d)
    return targets


def try_path(d):
    import hid
    up = d.get("usage_page", 0)
    path = d.get("path")
    print("\n" + "=" * 60)
    print(f"接口 usage_page=0x{up:04X} iface={d.get('interface_number')}")
    print(f"path={path}")

    try:
        h = hid.device()
        h.open_path(path)
    except Exception as e:
        print(f"  打开失败: {e}")
        return
    try:
        h.set_nonblocking(1)
        # 清空可能的残留输入
        for _ in range(3):
            h.read(64)

        for ln in TRY_LENS:
            # 方式 A: output report (report_id=0x00 前缀)
            pkt = bytearray([0x00]) + CHECK_CMD
            pkt += bytes(ln - len(pkt)) if ln > len(pkt) else b""
            pkt = bytes(pkt[:ln]) if ln >= len(pkt) else bytes(pkt)
            try:
                n = h.write(pkt)
                time.sleep(0.05)
                resp = h.read(max(ln, 64))
                if resp:
                    print(f"  [A len={ln}] write={n} 收到响应({len(resp)}B): {hexs(resp[:32])}")
                else:
                    # 再多等一会儿读一次
                    time.sleep(0.1)
                    resp = h.read(max(ln, 64))
                    if resp:
                        print(f"  [A len={ln}] write={n} 延迟响应({len(resp)}B): {hexs(resp[:32])}")
                    else:
                        print(f"  [A len={ln}] write={n} 无响应")
            except Exception as e:
                print(f"  [A len={ln}] 写失败: {e}")

            # 方式 B: feature report
            try:
                feat = bytearray([0x00]) + CHECK_CMD
                feat += bytes(ln - len(feat)) if ln > len(feat) else b""
                feat = bytes(feat[:ln])
                h.send_feature_report(feat)
                time.sleep(0.05)
                got = h.get_feature_report(0x00, max(ln, 64))
                if got and any(got):
                    print(f"  [B len={ln}] feature 回读({len(got)}B): {hexs(got[:32])}")
            except Exception as e:
                pass  # feature 不支持很正常,不刷屏
    finally:
        h.close()


def main():
    try:
        import hid  # noqa
    except Exception as e:
        print("import hid FAILED:", e)
        sys.exit(2)

    targets = list_targets()
    print(f"找到 {len(targets)} 个 vendor 接口待探测")
    if not targets:
        print("没找到 vendor 接口,键盘可能未连接")
        sys.exit(1)
    for d in targets:
        try_path(d)
    print("\n探测结束。哪个接口有'非全 0、且与发送内容不同'的响应,即命令通道。")


if __name__ == "__main__":
    main()
