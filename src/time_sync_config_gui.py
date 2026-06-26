# -*- coding: utf-8 -*-
"""
QK 键盘时间校正 —— 定时任务配置 GUI
=====================================

一个基于 tkinter 的图形配置工具,让你无需记命令即可:
  * 打开 / 关闭「自动校时」总开关
  * 设置每天执行校时的时间点 (支持多个 = 每天多次)
  * 一键应用 (写入 Windows 计划任务) / 移除全部任务
  * 查看当前已生效的计划任务状态
  * 立即手动校时一次 (测试)

实现说明
--------
- 底层通过 Windows `schtasks` 为每个时间点创建一个计划任务,
  任务名统一前缀 TASK_PREFIX,便于批量增删。
- 任务静默运行: 调用 pythonw.exe 执行 time_sync_hid.py --quiet,
  无黑窗、无交互,结果写入 time_sync.log。
- 配置 (开关 + 时间点列表) 保存到 time_sync_schedule.json,
  既用于 GUI 回显,也是「当前应有状态」的记录。

零额外依赖: 仅用 Python 自带的 tkinter / json / subprocess。
"""
import os
import re
import sys
import json
import subprocess
import datetime
import tkinter as tk
from tkinter import ttk, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "time_sync_hid.py")
CONFIG = os.path.join(HERE, "time_sync_schedule.json")
TASK_PREFIX = "QK_TimeSync_"          # 计划任务名前缀
LOG_PATH = os.path.join(HERE, "time_sync.log")


# ----------------------------------------------------------------------------
# 解析 pythonw.exe 路径 (静默运行, 无控制台黑窗)
# ----------------------------------------------------------------------------
def find_pythonw():
    # 1) 与当前解释器同目录的 pythonw.exe
    cand = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if os.path.exists(cand):
        return cand
    # 2) PATH 中的 pythonw
    from shutil import which
    p = which("pythonw")
    if p:
        return p
    # 3) 退而求其次用 python.exe (会有黑窗一闪)
    return sys.executable


PYTHONW = find_pythonw()


def find_python_console():
    """返回控制台版 python.exe (用于测试时捕获输出与退出码)。"""
    cand = os.path.join(os.path.dirname(sys.executable), "python.exe")
    if os.path.exists(cand):
        return cand
    from shutil import which
    p = which("python")
    if p:
        return p
    return sys.executable


PYTHON_CONSOLE = find_python_console()


# ----------------------------------------------------------------------------
# 配置读写
# ----------------------------------------------------------------------------
def load_config():
    if os.path.exists(CONFIG):
        try:
            with open(CONFIG, "r", encoding="utf-8") as f:
                d = json.load(f)
            d.setdefault("enabled", False)
            d.setdefault("times", [])
            return d
        except Exception:
            pass
    return {"enabled": False, "times": []}


def save_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------------------
# schtasks 操作
# ----------------------------------------------------------------------------
def _run(cmd):
    """运行命令, 返回 (returncode, stdout+stderr)。隐藏黑窗。"""
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    cp = subprocess.run(cmd, capture_output=True, text=True,
                        encoding="gbk", errors="ignore", startupinfo=si)
    return cp.returncode, (cp.stdout or "") + (cp.stderr or "")


def task_name_for(hhmm):
    """把 'HH:MM' 转成合法任务名后缀, 如 12:00 -> QK_TimeSync_1200。"""
    return TASK_PREFIX + hhmm.replace(":", "")


def list_existing_tasks():
    """返回当前系统里属于本工具的计划任务 (名称, 触发时间) 列表。"""
    rc, out = _run(["schtasks", "/Query", "/FO", "CSV", "/NH"])
    tasks = []
    if rc != 0:
        return tasks
    for line in out.splitlines():
        # CSV: "\TaskName","Next Run Time","Status"
        m = re.match(r'"\\?([^"]+)"', line.strip())
        if not m:
            continue
        name = m.group(1)
        base = name.split("\\")[-1]
        if base.startswith(TASK_PREFIX):
            tasks.append(base)
    return sorted(set(tasks))


def create_task(hhmm):
    """为某个 HH:MM 创建每日计划任务。返回 (ok, msg)。"""
    name = task_name_for(hhmm)
    # 命令: pythonw.exe "time_sync_hid.py" --quiet
    tr = f'"{PYTHONW}" "{SCRIPT}" --quiet'
    cmd = ["schtasks", "/Create", "/TN", name, "/TR", tr,
           "/SC", "DAILY", "/ST", hhmm, "/F"]
    rc, out = _run(cmd)
    return rc == 0, out.strip()


def delete_task(name):
    rc, out = _run(["schtasks", "/Delete", "/TN", name, "/F"])
    return rc == 0, out.strip()


def delete_all_tasks():
    msgs = []
    for name in list_existing_tasks():
        ok, m = delete_task(name)
        msgs.append(f"{'OK' if ok else 'FAIL'} {name}: {m}")
    return msgs


def apply_schedule(enabled, times):
    """
    使系统计划任务与配置一致:
      - 先清掉本工具所有旧任务
      - 若 enabled, 按 times 重新创建
    返回操作日志字符串列表。
    """
    logs = []
    # 1) 清旧
    for name in list_existing_tasks():
        ok, m = delete_task(name)
        logs.append(f"删除旧任务 {name}: {'成功' if ok else '失败 '+m}")
    # 2) 按需新建
    if enabled:
        for hhmm in times:
            ok, m = create_task(hhmm)
            logs.append(f"创建 {hhmm}: {'成功' if ok else '失败 '+m}")
    else:
        logs.append("自动校时已关闭, 未创建任何任务。")
    return logs


def run_once_now():
    """立即静默校时一次 (测试用)。"""
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    subprocess.Popen([PYTHONW, SCRIPT, "--quiet"], startupinfo=si)


# 测试用的固定时间: 与当前明显不同, 便于肉眼确认屏幕是否跳变。
TEST_TIME = "2020-01-01 08:30:00"


def run_test_now():
    """
    发送一个明显不同的【测试时间】到键盘, 用于确认整条链路工作正常。
    用 python.exe (非 pythonw) 起一个可见控制台窗口, 便于看到发送过程与结果;
    并把结果写入日志。返回 (ok, msg)。
    """
    cmd = [PYTHON_CONSOLE, SCRIPT, "--quiet", "--time", TEST_TIME]
    rc, out = _run(cmd)
    return rc == 0, out.strip()


# ----------------------------------------------------------------------------
# GUI
# ----------------------------------------------------------------------------
HHMM_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("QK100 键盘时间校正 - 定时配置")
        self.resizable(False, False)
        self.cfg = load_config()

        pad = {"padx": 10, "pady": 6}

        # 顶部: 总开关
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="we", **pad)
        self.enabled_var = tk.BooleanVar(value=self.cfg.get("enabled", False))
        ttk.Checkbutton(top, text="启用每日自动校时", variable=self.enabled_var,
                        command=self._on_toggle).pack(side="left")
        self.status_lbl = ttk.Label(top, text="", foreground="gray")
        self.status_lbl.pack(side="right")

        # 中部: 时间点列表 + 增删
        mid = ttk.LabelFrame(self, text="每天执行的时间点 (24 小时制, 可多个 = 每天多次)")
        mid.grid(row=1, column=0, sticky="we", **pad)

        self.listbox = tk.Listbox(mid, height=6, width=28)
        self.listbox.grid(row=0, column=0, rowspan=4, padx=8, pady=8)

        ttk.Label(mid, text="时间 (HH:MM)").grid(row=0, column=1, sticky="w", padx=6)
        self.time_entry = ttk.Entry(mid, width=10)
        self.time_entry.grid(row=0, column=2, padx=6)
        self.time_entry.insert(0, "12:00")

        ttk.Button(mid, text="添加", width=8,
                   command=self._add_time).grid(row=1, column=1, columnspan=2, pady=2)
        ttk.Button(mid, text="删除选中", width=8,
                   command=self._del_time).grid(row=2, column=1, columnspan=2, pady=2)
        ttk.Button(mid, text="清空", width=8,
                   command=self._clear_times).grid(row=3, column=1, columnspan=2, pady=2)

        # 底部: 操作按钮
        bot = ttk.Frame(self)
        bot.grid(row=2, column=0, sticky="we", **pad)
        ttk.Button(bot, text="应用设置", command=self._apply).pack(side="left", padx=4)
        ttk.Button(bot, text="立即校时一次", command=self._run_now).pack(side="left", padx=4)
        ttk.Button(bot, text="测试", command=self._run_test).pack(side="left", padx=4)
        ttk.Button(bot, text="刷新状态", command=self._refresh_status).pack(side="left", padx=4)
        ttk.Button(bot, text="查看日志", command=self._view_log).pack(side="left", padx=4)

        # 日志/提示区
        self.log = tk.Text(self, height=8, width=58, state="disabled",
                           background="#f6f6f6")
        self.log.grid(row=3, column=0, sticky="we", **pad)

        # 初始化界面
        for t in self.cfg.get("times", []):
            self.listbox.insert("end", t)
        self._refresh_status()
        self._println(f"pythonw: {PYTHONW}")
        self._println(f"脚本   : {SCRIPT}")

    # ---- 工具 ----
    def _println(self, s):
        self.log.configure(state="normal")
        self.log.insert("end", s + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _current_times(self):
        return list(self.listbox.get(0, "end"))

    # ---- 事件 ----
    def _on_toggle(self):
        self._println(f"自动校时开关 -> {'开' if self.enabled_var.get() else '关'} "
                      f"(点『应用设置』后生效)")

    def _add_time(self):
        t = self.time_entry.get().strip()
        if not HHMM_RE.match(t):
            messagebox.showwarning("格式错误", "请输入 24 小时制 HH:MM, 例如 09:30 或 18:00")
            return
        # 规范成两位
        h, m = t.split(":")
        t = f"{int(h):02d}:{int(m):02d}"
        if t in self._current_times():
            messagebox.showinfo("已存在", f"时间点 {t} 已在列表中")
            return
        self.listbox.insert("end", t)
        self._println(f"添加时间点 {t} (点『应用设置』后生效)")

    def _del_time(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        t = self.listbox.get(sel[0])
        self.listbox.delete(sel[0])
        self._println(f"移除时间点 {t} (点『应用设置』后生效)")

    def _clear_times(self):
        self.listbox.delete(0, "end")
        self._println("已清空时间点列表 (点『应用设置』后生效)")

    def _apply(self):
        enabled = self.enabled_var.get()
        times = self._current_times()
        if enabled and not times:
            messagebox.showwarning("缺少时间点", "已启用自动校时,但没有任何时间点。\n"
                                                "请先添加至少一个时间点,或关闭开关。")
            return
        # 保存配置
        self.cfg = {"enabled": enabled, "times": times}
        save_config(self.cfg)
        # 应用到计划任务
        self._println("=" * 40)
        self._println("正在应用设置到 Windows 计划任务...")
        for line in apply_schedule(enabled, times):
            self._println("  " + line)
        self._println("完成。")
        self._refresh_status()

    def _run_now(self):
        run_once_now()
        self._println("已触发一次静默校时 (结果见 time_sync.log)。约 1-2 秒完成。")

    def _run_test(self):
        # 测试: 写入一个明显不同的时间, 让你肉眼确认屏幕跳变 => 链路正常
        if not messagebox.askokcancel(
                "测试",
                f"将向键盘写入一个【测试时间】:\n    {TEST_TIME}\n\n"
                "用于确认程序与键盘通信正常。\n"
                "发送后请观察键盘 TFT 屏时间是否跳到该值、键盘能否正常打字。\n\n"
                "确认无误后, 再点『立即校时一次』即可把时间校回当前系统时间。\n\n"
                "是否继续?"):
            return
        self._println("=" * 40)
        self._println(f"正在发送测试时间 {TEST_TIME} ...")
        ok, msg = run_test_now()
        if ok:
            self._println("测试发送完成。请检查键盘屏幕是否已跳到 " + TEST_TIME + "。")
            messagebox.showinfo(
                "测试已发送",
                f"已发送测试时间 {TEST_TIME}。\n\n"
                "请确认:\n"
                "1) 键盘 TFT 屏时间是否跳到了该值?\n"
                "2) 键盘能否正常打字?\n\n"
                "确认无误说明程序工作正常。\n"
                "随后点『立即校时一次』即可恢复为当前系统时间。")
        else:
            self._println("测试发送失败: " + msg)
            messagebox.showerror(
                "测试失败",
                "发送测试时间失败:\n\n" + (msg or "未知错误") +
                "\n\n请确认键盘已连接 (有线/接收器在位)。")
        self._refresh_status()

    def _refresh_status(self):
        tasks = list_existing_tasks()
        if tasks:
            txt = f"已生效任务: {len(tasks)} 个"
            color = "green"
        else:
            txt = "当前无定时任务"
            color = "gray"
        self.status_lbl.configure(text=txt, foreground=color)
        self._println("当前系统计划任务: " +
                      (", ".join(t.replace(TASK_PREFIX, "") for t in tasks)
                       if tasks else "无"))

    def _view_log(self):
        if not os.path.exists(LOG_PATH):
            messagebox.showinfo("日志", "暂无日志文件 time_sync.log")
            return
        try:
            os.startfile(LOG_PATH)
        except Exception as e:
            messagebox.showerror("打开失败", str(e))


def main():
    if os.name != "nt":
        print("本工具仅支持 Windows。")
        return 1
    App().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
