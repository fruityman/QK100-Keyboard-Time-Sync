# -*- coding: utf-8 -*-
"""
Frida 全自动抓包(逆向第三步)。

流程:
  1) frida spawn 启动 DeviceDriver.exe 并注入,hook 住 HID 写入 API。
  2) 后台线程复用 time_sync.py 的查找/点击逻辑,自动执行
       TFT图标 -> 时间校正 -> 应用
     来触发真实的"时间校正"命令。
  3) 主线程实时收集所有被 hook 到的写入字节包,带时间戳。
  4) 触发完成后等待数秒收尾,把所有捕获的包打印 + 写入 capture_packets.txt。

无需手动点击。运行时请勿操作鼠标键盘(约 15 秒)。
"""
import sys
import time
import threading
import datetime
import frida

EXE = r"C:\Software\QK Config\DeviceDriver.exe"
OUT = "capture_packets.txt"

JS = r"""
'use strict';
function hexdump_bytes(p, len) {
    if (len <= 0 || len > 512) return '(len=' + len + ' skipped)';
    try {
        var ab = p.readByteArray(len);          // frida 17: NativePointer.readByteArray -> ArrayBuffer
        var bytes = new Uint8Array(ab);
        var s = '';
        for (var i = 0; i < bytes.length; i++) {
            var h = bytes[i].toString(16).toUpperCase();
            if (h.length < 2) h = '0' + h;
            s += h + ' ';
        }
        return s.trim();
    } catch (e) { return '(read err ' + e + ')'; }
}
function resolveExport(mod, name) {
    try { return Process.getModuleByName(mod).getExportByName(name); }
    catch (e) {
        try { return Module.getExportByName(mod, name); } catch (e2) { return null; }
    }
}
function hookHid(name) {
    var addr = resolveExport('hid.dll', name);
    if (!addr) { send({t:'info', m:name+' not found'}); return; }
    Interceptor.attach(addr, {
        // BOOLEAN HidD_SetFeature(HANDLE h, PVOID buf, ULONG len)
        onEnter: function (args) {
            var len = args[2].toInt32();
            send({t:'hid', api:name, h:handleToStr(args[0]),
                  len:len, hex:hexdump_bytes(args[1], len)});
        }
    });
    send({t:'info', m:'hooked '+name});
}
function handleToStr(h) {
    try { return '0x' + h.toString(16); } catch (e) { return '?'; }
}
// ---- 句柄 -> 设备路径 映射: hook CreateFileW/CreateFileA, 记录每个返回句柄打开的是哪个设备 ----
function hookCreateFile(name, isWide) {
    var addr = resolveExport('kernel32.dll', name);
    if (!addr) { send({t:'info', m:name+' not found'}); return; }
    Interceptor.attach(addr, {
        onEnter: function (args) {
            try {
                this.path = isWide ? args[0].readUtf16String() : args[0].readUtf8String();
            } catch (e) { this.path = '(read err)'; }
        },
        onLeave: function (retval) {
            var h = handleToStr(retval);
            // 只关心 HID 设备路径 (含 hid# 或 \\?\hid 之类), 但也全量上报便于回溯
            send({t:'open', api:name, h:h, path:this.path});
        }
    });
    send({t:'info', m:'hooked '+name});
}
function hookWriteFile() {
    var addr = resolveExport('kernel32.dll', 'WriteFile');
    if (!addr) { send({t:'info', m:'WriteFile not found'}); return; }
    Interceptor.attach(addr, {
        // BOOL WriteFile(HANDLE h, LPCVOID buf, DWORD nBytes, LPDWORD written, OVERLAPPED*)
        onEnter: function (args) {
            var len = args[2].toInt32();
            if (len > 0 && len <= 96) {
                send({t:'wf', h:handleToStr(args[0]), len:len, hex:hexdump_bytes(args[1], len)});
            }
        }
    });
    send({t:'info', m:'hooked WriteFile'});
}
function hookDeviceIoControl() {
    var addr = resolveExport('kernel32.dll', 'DeviceIoControl');
    if (!addr) { send({t:'info', m:'DeviceIoControl not found'}); return; }
    Interceptor.attach(addr, {
        // BOOL DeviceIoControl(HANDLE h, DWORD code, LPVOID inBuf, DWORD inSize, ...)
        onEnter: function (args) {
            var inSize = args[3].toInt32();
            if (inSize > 0 && inSize <= 96) {
                send({t:'ioctl', h:handleToStr(args[0]),
                      code:'0x'+args[1].toInt32().toString(16),
                      len:inSize, hex:hexdump_bytes(args[2], inSize)});
            }
        }
    });
    send({t:'info', m:'hooked DeviceIoControl'});
}
hookCreateFile('CreateFileW', true);
hookCreateFile('CreateFileA', false);
hookHid('HidD_SetOutputReport');
hookHid('HidD_SetFeature');
hookWriteFile();
hookDeviceIoControl();
send({t:'info', m:'=== hooks installed (passive listen only, no active send) ==='});
"""

captured = []          # (ts_str, kind, api, len, hex, handle, path)
handle_paths = {}      # handle_str -> 最近一次该句柄 CreateFile 打开的设备路径
opens = []             # (ts_str, api, handle, path) 全部 CreateFile 记录
lock = threading.Lock()
trigger_log = []


def now():
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


def on_message(message, data):
    if message.get("type") == "send":
        p = message["payload"]
        t = p.get("t")
        if t == "info":
            print(f"[frida] {p['m']}")
        elif t == "open":
            h = p.get("h", "")
            path = p.get("path", "")
            with lock:
                handle_paths[h] = path
                opens.append((now(), p.get("api", "CreateFile"), h, path))
            # 仅打印 HID 相关的打开,避免刷屏
            if path and ("hid#" in path.lower() or "\\hid" in path.lower()
                         or "vid_" in path.lower()):
                print(f"[open] {p.get('api')} {h} -> {path}")
        else:
            if t == "ioctl":
                api = f"DeviceIoControl(code={p.get('code')})"
            elif t == "wf":
                api = "WriteFile"
            else:
                api = p.get("api", t)
            handle = p.get("h", "")
            path = handle_paths.get(handle, "")
            rec = (now(), t, api, p["len"], p["hex"], handle, path)
            with lock:
                captured.append(rec)
            short = path.split("#")[1] if (path and "#" in path) else path
            print(f">>> [{rec[0]}] {api} h={handle} ({short}) len={rec[3]}  {rec[4]}")
    elif message.get("type") == "error":
        print("[frida-error]", message.get("description"))


def auto_trigger():
    """后台:复用 time_sync 的点击逻辑自动触发一次时间校正。"""
    try:
        import time_sync as ts
        print(f"[trigger] {now()} 开始自动点击触发时间校正...")
        steps = [
            (ts.TPL_TFT, "TFT图标"),
            (ts.TPL_TIMESYNC, "时间校正"),
            (ts.TPL_APPLY, "应用"),
        ]
        for tpl, name in steps:
            pos = ts.find_button(tpl, name)
            if not pos:
                print(f"[trigger] 未找到 {name},中止")
                return
            mark = now()
            print(f"[trigger] {mark} 即将点击 {name} @ {pos}  <-- 关注此刻前后的包")
            trigger_log.append((mark, name, pos))
            ts.click_at(pos[0], pos[1], name)
        print(f"[trigger] {now()} 点击流程完成")
    except Exception as e:
        print("[trigger] 异常:", e)


def find_pid(name="DeviceDriver.exe"):
    import subprocess
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True)
    for line in out.stdout.splitlines():
        parts = [x.strip('"') for x in line.split(",")]
        if len(parts) >= 2 and parts[0].lower() == name.lower():
            try:
                return int(parts[1])
            except ValueError:
                pass
    return None


def main():
    import subprocess
    # 优先复用已在运行且界面就绪的程序;只有不存在时才启动并长等待。
    pid = find_pid()
    if pid:
        print(f"检测到 DeviceDriver.exe 已在运行 (pid={pid}),直接复用,不重启。")
    else:
        print("未发现运行中的程序,启动并等待设备识别就绪(15s) ...")
        subprocess.Popen([EXE], cwd=r"C:\Software\QK Config")
        time.sleep(15.0)  # 键盘复位后首启需较长时间检测设备
        pid = find_pid()
        if not pid:
            print("找不到 DeviceDriver.exe 进程")
            sys.exit(2)

    print(f"attach 到 pid={pid} ...")
    try:
        session = frida.attach(pid)
    except Exception as e:
        print("attach 失败(可能需管理员权限):", e)
        sys.exit(2)
    script = session.create_script(JS)
    script.on("message", on_message)
    script.load()
    print("hook 已安装(纯被动监听)。开始自动点击触发,请勿操作鼠标键盘。")

    th = threading.Thread(target=auto_trigger, daemon=True)
    th.start()
    th.join(timeout=60)

    time.sleep(3.0)  # 收尾包

    try:
        session.detach()
    except Exception:
        pass

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(f"# capture at {datetime.datetime.now()}\n")
        f.write(f"# system time now = {datetime.datetime.now()}\n\n")
        f.write("## trigger clicks:\n")
        for mark, name, pos in trigger_log:
            f.write(f"  {mark}  click {name} @ {pos}\n")

        # 句柄 -> 设备路径 映射(本次抓包关键产物: 用来确认命令到底发往哪个接口)
        f.write(f"\n## handle -> device path ({len(handle_paths)}):\n")
        for h, path in handle_paths.items():
            f.write(f"  {h}  ->  {path}\n")

        f.write(f"\n## all CreateFile opens ({len(opens)}):\n")
        for ts_str, api, h, path in opens:
            f.write(f"  [{ts_str}] {api} {h} -> {path}\n")

        f.write(f"\n## captured writes ({len(captured)}):\n")
        for ts_str, kind, api, ln, hx, handle, path in captured:
            f.write(f"  [{ts_str}] {api} h={handle} path={path} len={ln}\n      {hx}\n")
    print(f"\n共捕获 {len(captured)} 条写入,{len(handle_paths)} 个句柄映射,已保存到 {OUT}")
    print("(保留程序进程,未杀掉,避免界面异常。如需关闭请手动关。)")


if __name__ == "__main__":
    main()
