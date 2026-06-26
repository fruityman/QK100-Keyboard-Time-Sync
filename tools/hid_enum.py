# -*- coding: utf-8 -*-
"""
枚举本机所有 HID 设备,重点列出键盘相关(VID 匹配)的全部接口及其能力。
用于逆向第一步:搞清楚键盘暴露了哪些 vendor-defined 接口、各自的
report 长度/usage_page,从而确定哪个接口是配置软件用来收发命令的通道。
"""
import sys

# 候选键盘 VID/PID(从 Get-PnpDevice 结果里挑出的可疑项)
# 0x05AC 通常是 Apple,但很多国产键盘会借用;0x0DB0 是 Micro Star/部分外设
CANDIDATE_VIDS = {0x05AC, 0x0DB0, 0x1462}


def main():
    try:
        import hid
    except Exception as e:
        print("import hid FAILED:", e)
        sys.exit(2)

    print("=== hidapi enumerate all devices ===")
    devs = hid.enumerate()
    print("total HID interfaces:", len(devs))

    # 先全量打印一份精简列表,便于你肉眼认出键盘
    print("\n--- ALL (vid,pid | usage_page/usage | product) ---")
    for d in devs:
        vid = d.get("vendor_id", 0)
        pid = d.get("product_id", 0)
        up = d.get("usage_page", 0)
        us = d.get("usage", 0)
        prod = d.get("product_string") or ""
        manu = d.get("manufacturer_string") or ""
        print(f"  {vid:04X}:{pid:04X}  up=0x{up:04X} us=0x{us:04X}  "
              f"[{manu}] {prod}  iface={d.get('interface_number')}")

    # 再重点列出候选键盘的接口细节
    print("\n--- CANDIDATE keyboards (full detail) ---")
    for d in devs:
        if d.get("vendor_id") in CANDIDATE_VIDS:
            print("  " + "-" * 50)
            for k in ("path", "vendor_id", "product_id", "usage_page",
                      "usage", "interface_number", "manufacturer_string",
                      "product_string", "release_number"):
                v = d.get(k)
                if isinstance(v, int) and k in ("vendor_id", "product_id",
                                                "usage_page", "usage"):
                    print(f"    {k} = 0x{v:04X}")
                else:
                    print(f"    {k} = {v!r}")


if __name__ == "__main__":
    main()
