# -*- coding: utf-8 -*-
"""GUI 端到端冒烟测试（主机左侧 + 常规属性下拉布局）。

连接 -> 设备下拉自动打开 -> 模式/纸张/分辨率下拉填充 -> 扫描 -> 自动保存 -> 预览

用法: python tests/gui_smoke.py [host] [port]
成功后退出码 0。
"""
from __future__ import annotations

import os
import sys
import time
import tkinter as tk

sys.path.insert(0, ".")

from sanewin.gui import SaneGui  # noqa: E402
from sanewin import gui as gui_mod  # noqa: E402
from sanewin import gui as gui_pkg  # noqa: E402

# 冒烟测试中禁用模态弹窗
gui_mod.messagebox.showerror = lambda *a, **k: print("MSGBOX-ERROR:", a[1] if len(a) > 1 else a)
gui_mod.messagebox.showinfo = lambda *a, **k: print("MSGBOX-INFO:", a[1] if len(a) > 1 else a)
gui_mod.messagebox.askyesno = lambda *a, **k: False

HOST = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.230"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 6566

root = tk.Tk()
gui = SaneGui(root)
gui._auto_start = lambda: None  # 禁用启动自动连接
state = {"step": "connect", "t0": time.time()}
saved_files_before = set(os.listdir(gui.save_dir))


def tick() -> None:
    try:
        _tick_inner()
    except Exception:
        import traceback
        traceback.print_exc()
        root.destroy()


def _tick_inner() -> None:
    if time.time() - state["t0"] > 120:
        print("FAIL: 超时")
        root.destroy()
        return
    if state["step"] == "connect":
        if gui.client is not None and gui.devices:
            print(f"连接 OK，设备 {len(gui.devices)} 台")
            print(f"默认分辨率: {gui.res_var.get()}")
            gui.device_var.set(gui.devices[0].name)
            gui.on_device_selected()
            state["step"] = "open"
            state["t0"] = time.time()
        root.after(300, tick)
    elif state["step"] == "open":
        if gui.descriptors:
            print(f"自动打开设备 OK，选项 {len(gui.descriptors)} 个")
            print(f"模式下拉: {gui.mode_combo['values']}  默认: {gui.mode_var.get()}")
            print(f"纸张下拉: {gui.paper_combo['values']}  默认: {gui.paper_var.get()}")
            print(f"分辨率下拉: {gui.res_combo['values']}  默认: {gui.res_var.get()}")
            print(f"常用选项索引: {gui.opt_index}")
            # 配置持久化
            gui_pkg.save_config(host=HOST, port=PORT, last_device=gui.devices[0].name)
            cfg = gui_pkg.load_config()
            print(f"配置持久化: host={cfg.get('host')} port={cfg.get('port')} "
                  f"last_device={cfg.get('last_device')}")
            gui.res_var.set("75")
            if "灰度" in gui.mode_combo["values"]:
                gui.mode_var.set("灰度")
            elif gui.mode_combo["values"]:
                gui.mode_var.set(gui.mode_combo["values"][0])
            gui.on_scan()
            state["step"] = "scan"
            state["t0"] = time.time()
        root.after(300, tick)
    elif state["step"] == "scan":
        if gui.frames:
            print(f"扫描 OK：{len(gui.frames)} 页 "
                  f"{gui.frames[0].params.pixels_per_line}x{gui.frames[0].params.lines} "
                  f"format={gui.frames[0].params.format} depth={gui.frames[0].params.depth}")
            print(f"会话帧数: {len(gui._session)}")
            new_files = set(os.listdir(gui.save_dir)) - saved_files_before
            print(f"自动保存到 {gui.save_dir}: {new_files}")
            print(f"预览加载: {gui._full_photo is not None} "
                  f"({gui._img_w}x{gui._img_h})")
            print(f"保存按钮: PDF={gui.btn_save_pdf['state']} "
                  f"PNG={gui.btn_save_png['state']} BMP={gui.btn_save_bmp['state']}")
            root.destroy()
        elif gui._busy:
            root.after(300, tick)
        else:
            print("FAIL: 扫描未产生图像")
            root.destroy()


root.after(200, lambda: (gui.host_var.set(HOST), gui.port_var.set(str(PORT)),
                         gui.on_connect()))
root.after(400, tick)
root.mainloop()
