# -*- coding: utf-8 -*-
"""
sanewin 图形界面（tkinter，零第三方依赖）。

布局：
  ┌─────────────────────────────────────────────────────────┐
  │ 菜单栏：文件 / 设置(保存目录) / 帮助                       │
  ├──────────────────────┬──────────────────────────────────┤
  │ 左侧                  │ 预览区                            │
  │ ── 主机信息 ──         │ 保存目录: ... [选择目录]           │
  │ 主机/端口/用户名/密码  │ 自动缩放 + 滚轮缩放 + 拖拽          │
  │ [连接] [断开]         │ [保存BMP][保存PNG][保存PDF]        │
  │ ── 设备 ──            │                                  │
  │ 设备[下拉，选后自动打开]│                                  │
  │ ── 扫描设置 ──         │                                  │
  │ 模式/纸张规格/分辨率    │                                  │
  │ 连续扫描 [扫描][取消]   │                                  │
  │ [进度条]              │                                  │
  └──────────────────────┴──────────────────────────────────┘

功能：
- 主机信息持久化（~/.sanewin/config.json），启动自动连接并打开上次设备
- 常规属性下拉：模式（彩色/灰度/黑白）、纸张规格、分辨率（自动读设备约束）
- 连续扫描：多页合并，单页存 PNG、多页存 PDF
- 连接中断/设备忙自动重连切换；保存 BMP / PNG / PDF

运行：python -m sanewin.gui
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import List, Optional, Tuple

from .client import SaneClient, SaneError
from .constants import (
    SANEAction,
    SANEConstraintType,
    SANEStatus,
    SANEValueType,
)
from .images import frame_to_bmp, frame_to_png, frames_to_pdf
from .models import SANEControlOptionRequest, SANEDevice, SANEOptionDescriptor

logger = logging.getLogger("sanewin.gui")

# ---------------- 配置持久化（~/.sanewin/config.json） ----------------
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".sanewin")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(**kw) -> None:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        cfg = load_config()
        cfg.update(kw)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:  # noqa: BLE001
        logger.warning("保存配置失败: %s", e)


# ---------------- 中文翻译表 ----------------
MODE_ZH = {
    "Color": "彩色",
    "Grayscale": "灰度",
    "Monochrome": "黑白",
    "Gray": "灰度",
    "Lineart": "黑白",
}
MODE_EN = {zh: en for en, zh in MODE_ZH.items()}

PAPER_ZH = {
    "Letter": "Letter",
    "A4": "A4",
    "A5": "A5",
    "A6": "A6",
    "A8": "A8",
    "A5 (Landscape)": "A5 横向",
    "A6 (Landscape)": "A6 横向",
    "A8 (Landscape)": "A8 横向",
    "B5 [JIS]": "B5",
    "Postcard": "明信片",
    "Postcard (Landscape)": "明信片横向",
    "PlasticCard": "塑料卡片",
    "Maximum": "最大",
    "Manual": "手动",
}
PAPER_EN = {zh: en for en, zh in PAPER_ZH.items()}

# 区域坐标纸张尺寸（毫米）：用于无 scan-area 的后端（如 epson2 的 br-x/br-y）
PAPER_MM = {
    "A4": (210.0, 297.0),
    "Letter": (215.9, 279.4),
    "A5": (148.0, 210.0),
    "A6": (105.0, 148.0),
}

OPTION_ZH = {
    "mode": "扫描模式",
    "scan-area": "纸张规格",
    "resolution": "分辨率",
    "source": "扫描来源",
    "brightness": "亮度",
    "contrast": "对比度",
    "threshold": "阈值",
    "depth": "位深",
}

# 命名方案：显示名 -> 模板（占位符 {date}{time}{mode}{device}{n}）
NAME_SCHEMES = {
    "scan_日期_时间_模式": "scan_{date}_{time}_{mode}",
    "日期_时间": "{date}_{time}",
    "设备_日期_时间": "{device}_{date}_{time}",
    "模式_日期_时间": "{mode}_{date}_{time}",
}
NAME_CUSTOM = "自定义..."


def _zh_mode(v: str) -> str:
    return MODE_ZH.get(v, v)


def _en_mode(v: str) -> str:
    return MODE_EN.get(v, v)


def _zh_paper(v: str) -> str:
    return PAPER_ZH.get(v, v)


def _en_paper(v: str) -> str:
    return PAPER_EN.get(v, v)


class SaneGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.client: Optional[SaneClient] = None
        self.devices: List[SANEDevice] = []
        self.descriptors: List[SANEOptionDescriptor] = []
        self.opt_index: dict = {}          # 常用选项名 -> 选项 index
        self.frames = []
        self._session: List = []           # 连续扫描累积帧
        self._busy = False
        self._cancel = False
        self._msg_queue: "queue.Queue[tuple]" = queue.Queue()
        self._photo = None
        self._full_photo = None
        self._img_w = 0
        self._img_h = 0
        self._preview_scale = 1.0
        self._preview_fit = True
        cfg = load_config()
        self.save_dir = cfg.get("save_dir") or os.path.join(os.getcwd(), "scans")

        root.title("SANE 扫描客户端")
        root.geometry("1180x760")
        root.minsize(960, 620)
        self._build_ui()
        os.makedirs(self.save_dir, exist_ok=True)
        self.root.after(100, self._poll_queue)
        self.root.after(400, self._auto_start)

    # ------------------------------------------------------------ UI 构建

    def _build_ui(self) -> None:
        self._build_menu()

        cols = ttk.Frame(self.root, padding=(8, 4))
        cols.pack(fill=tk.BOTH, expand=True)
        cols.columnconfigure(0, weight=2, uniform="col")
        cols.columnconfigure(1, weight=3, uniform="col")
        cols.rowconfigure(0, weight=1)

        left = ttk.Frame(cols)
        left.grid(row=0, column=0, sticky=tk.NSEW)
        self._build_left_panel(left)

        prev_frame = ttk.LabelFrame(cols, text="预览（滚轮缩放，拖动平移）", padding=4)
        prev_frame.grid(row=0, column=1, sticky=tk.NSEW, padx=(6, 0))
        self._build_preview_panel(prev_frame)

        self.status_var = tk.StringVar(value="未连接")
        ttk.Label(self.root, textvariable=self.status_var, anchor=tk.W,
                  relief=tk.SUNKEN, padding=(6, 2)).pack(fill=tk.X, side=tk.BOTTOM)

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="退出", command=self.root.destroy)
        menubar.add_cascade(label="文件", menu=file_menu)
        set_menu = tk.Menu(menubar, tearoff=0)
        set_menu.add_command(label="保存目录...", command=self._choose_save_dir)
        menubar.add_cascade(label="设置", menu=set_menu)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="关于", command=self._show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)
        self.root.config(menu=menubar)

    def _build_left_panel(self, parent: ttk.Frame) -> None:
        # ---- 主机信息
        host_frame = ttk.LabelFrame(parent, text="主机信息", padding=6)
        host_frame.pack(fill=tk.X)
        cfg = load_config()

        self.host_var = tk.StringVar(value=cfg.get("host", "192.168.1.230"))
        self.port_var = tk.StringVar(value=str(cfg.get("port", 6566)))
        self.user_var = tk.StringVar(value=cfg.get("user", ""))
        self.pass_var = tk.StringVar(value=cfg.get("password", ""))

        rows = [
            ("主机", self.host_var, False),
            ("端口", self.port_var, False),
            ("用户名", self.user_var, False),
            ("密码", self.pass_var, True),
        ]
        for i, (label, var, show) in enumerate(rows):
            ttk.Label(host_frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=2)
            ttk.Entry(host_frame, textvariable=var, width=24,
                      show="*" if show else "").grid(row=i, column=1, padx=(6, 0), pady=2)
        btns = ttk.Frame(host_frame)
        btns.grid(row=len(rows), column=0, columnspan=2, pady=(6, 0), sticky=tk.W)
        self.btn_connect = ttk.Button(btns, text="连接", command=self.on_connect)
        self.btn_connect.pack(side=tk.LEFT)
        self.btn_disconnect = ttk.Button(btns, text="断开", command=self.on_disconnect,
                                         state=tk.DISABLED)
        self.btn_disconnect.pack(side=tk.LEFT, padx=6)
        self.conn_label = ttk.Label(host_frame, text="未连接", foreground="#888")
        self.conn_label.grid(row=len(rows) + 1, column=0, columnspan=2, sticky=tk.W, pady=(4, 0))

        # ---- 设备
        dev_frame = ttk.LabelFrame(parent, text="设备", padding=6)
        dev_frame.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(dev_frame, text="设备").grid(row=0, column=0, sticky=tk.W)
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(dev_frame, textvariable=self.device_var,
                                         width=24, state="readonly")
        self.device_combo.grid(row=0, column=1, padx=(6, 0), sticky=tk.EW)
        self.device_combo.bind("<<ComboboxSelected>>", lambda e: self.on_device_selected())
        dev_frame.columnconfigure(1, weight=1)

        # ---- 扫描设置
        scan_frame = ttk.LabelFrame(parent, text="扫描设置", padding=6)
        scan_frame.pack(fill=tk.X, pady=(8, 0))
        scan_frame.columnconfigure(1, weight=1)

        ttk.Label(scan_frame, text="模式").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.mode_var = tk.StringVar()
        self.mode_combo = ttk.Combobox(scan_frame, textvariable=self.mode_var,
                                       width=16, state="readonly")
        self.mode_combo.grid(row=0, column=1, padx=(6, 0), sticky=tk.EW, pady=2)

        ttk.Label(scan_frame, text="纸张规格").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.paper_var = tk.StringVar(value="")
        self.paper_combo = ttk.Combobox(scan_frame, textvariable=self.paper_var,
                                        width=16, state="readonly")
        self.paper_combo.grid(row=1, column=1, padx=(6, 0), sticky=tk.EW, pady=2)

        ttk.Label(scan_frame, text="分辨率").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.res_var = tk.StringVar(value="200")
        self.res_combo = ttk.Combobox(
            scan_frame, textvariable=self.res_var, width=16,
            values=["75", "100", "150", "200", "300", "600"],
        )
        self.res_combo.grid(row=2, column=1, padx=(6, 0), sticky=tk.EW, pady=2)

        ttk.Label(scan_frame, text="命名规则").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.naming_var = tk.StringVar()
        self.naming_combo = ttk.Combobox(
            scan_frame, textvariable=self.naming_var, width=16, state="readonly",
            values=list(NAME_SCHEMES) + [NAME_CUSTOM],
        )
        self.naming_combo.grid(row=3, column=1, padx=(6, 0), sticky=tk.EW, pady=2)
        self.naming_combo.bind("<<ComboboxSelected>>", self._on_naming_selected)
        cfg = load_config()
        scheme = cfg.get("name_scheme")
        if scheme in self.naming_combo["values"]:
            self.naming_var.set(scheme)
        else:
            self.naming_var.set("scan_日期_时间_模式")

        self.cont_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(scan_frame, text="连续扫描（多页合成 PDF）",
                        variable=self.cont_var).grid(row=4, column=0, columnspan=2,
                                                     sticky=tk.W, pady=(6, 0))

        # ---- 扫描控制
        ctl = ttk.Frame(parent)
        ctl.pack(fill=tk.X, pady=(10, 0))
        self.btn_scan = ttk.Button(ctl, text="扫描", command=self.on_scan, state=tk.DISABLED)
        self.btn_scan.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_cancel = ttk.Button(ctl, text="取消", command=self.on_cancel,
                                     state=tk.DISABLED)
        self.btn_cancel.pack(side=tk.LEFT, padx=6)
        self.progress = ttk.Progressbar(parent, mode="determinate", length=200)
        self.progress.pack(fill=tk.X, pady=(8, 0))

    def _build_preview_panel(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent)
        top.pack(fill=tk.X)
        ttk.Label(top, text="保存目录:").pack(side=tk.LEFT)
        self.save_dir_label = ttk.Label(top, text=self.save_dir, foreground="#555")
        self.save_dir_label.pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="选择目录", command=self._choose_save_dir).pack(side=tk.LEFT)
        ttk.Button(top, text="打开文件夹", command=self.on_open_folder).pack(side=tk.LEFT, padx=4)

        self.canvas = tk.Canvas(parent, bg="#3a3a3a", highlightthickness=1,
                                highlightbackground="#888")
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.canvas.create_text(12, 16, anchor=tk.NW, fill="#ccc",
                                text="扫描结果将显示在这里", tags=("hint",))
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<ButtonPress-1>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B1-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))

        bottom = ttk.Frame(parent)
        bottom.pack(fill=tk.X, pady=(3, 0))
        self.zoom_label = ttk.Label(bottom, text="缩放: —")
        self.zoom_label.pack(side=tk.LEFT)
        self.btn_save_bmp = ttk.Button(bottom, text="保存 BMP", command=self.on_save_bmp,
                                       state=tk.DISABLED)
        self.btn_save_bmp.pack(side=tk.RIGHT, padx=(4, 0))
        self.btn_save_png = ttk.Button(bottom, text="保存 PNG", command=self.on_save_png,
                                       state=tk.DISABLED)
        self.btn_save_png.pack(side=tk.RIGHT, padx=(4, 0))
        self.btn_save_pdf = ttk.Button(bottom, text="保存 PDF", command=self.on_save_pdf,
                                       state=tk.DISABLED)
        self.btn_save_pdf.pack(side=tk.RIGHT)

    # ------------------------------------------------------------ 工具方法

    def _log(self, msg: str, level: int = logging.INFO) -> None:
        logging.getLogger("sanewin").log(level, msg)

    def _run_async(self, fn, on_done=None, on_error=None) -> None:
        def worker():
            try:
                result = fn()
                self._msg_queue.put(("done", result, on_done))
            except Exception as e:  # noqa: BLE001
                self._msg_queue.put(("error", e, on_error))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload, callback = self._msg_queue.get_nowait()
                if kind == "done":
                    if callback:
                        callback(payload)
                elif kind == "progress":
                    self.progress["value"] = payload
                elif kind == "error":
                    self._log(f"错误: {payload}", logging.ERROR)
                    messagebox.showerror("错误", str(payload))
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        for btn in (self.btn_connect, self.btn_disconnect, self.btn_scan):
            try:
                btn.config(state=state)
            except tk.TclError:
                pass

    def _show_about(self) -> None:
        messagebox.showinfo(
            "关于",
            "SANE 扫描客户端\n"
            "FEEYEE + 豆包 协作完成\n\n"
            "技术栈：Python 3 · tkinter 界面 · SANE 网络协议（sanit）\n"
            "零第三方依赖，兼容 SANE 网络服务器（192.168.1.230:6566）\n\n"
            "功能：彩色/灰度扫描 · PDF/PNG/BMP 保存 · 连续扫描 ·\n"
            "主机信息与参数持久化 · 启动自动连接",
        )

    def _choose_save_dir(self) -> None:
        path = filedialog.askdirectory(initialdir=self.save_dir, title="选择扫描保存目录")
        if not path:
            return
        self.save_dir = path
        os.makedirs(self.save_dir, exist_ok=True)
        self.save_dir_label.config(text=path)
        save_config(save_dir=path)
        self._log(f"保存目录: {path}")

    def on_open_folder(self) -> None:
        """打开保存目录（Windows 用资源管理器）。"""
        try:
            os.startfile(self.save_dir)  # type: ignore[attr-defined]
        except AttributeError:
            import subprocess
            subprocess.Popen(["xdg-open", self.save_dir])

    def _auto_start(self) -> None:
        """启动时自动连接上次的主机并打开上次的设备。"""
        cfg = load_config()
        if not cfg.get("host"):
            return
        self._log(f"启动自动连接 {cfg['host']}:{cfg.get('port', 6566)} ...")
        self.host_var.set(cfg["host"])
        self.port_var.set(str(cfg.get("port", 6566)))
        self.user_var.set(cfg.get("user", ""))
        self.pass_var.set(cfg.get("password", ""))
        self.on_connect()

    # ------------------------------------------------------------ 连接

    def _make_client(self, host: str, port: int, user: str, password: str) -> SaneClient:
        client = SaneClient(host, port, user, password)
        status = client.init()
        if status != SANEStatus.SANE_STATUS_GOOD:
            client.disconnect()
            raise SaneError(status, f"init 失败: {status}")
        return client

    def on_connect(self) -> None:
        if self._busy:
            return
        host = self.host_var.get().strip()
        try:
            port = int(self.port_var.get().strip() or "6566")
        except ValueError:
            messagebox.showerror("错误", "端口必须是数字")
            return
        user, password = self.user_var.get(), self.pass_var.get()
        self._set_busy(True)
        self.conn_label.config(text=f"{host}:{port} 连接中...", foreground="#888")
        self._log(f"连接 {host}:{port} ...")

        def work():
            client = self._make_client(host, port, user, password)
            devices = []
            for _ in range(3):
                devices = client.get_devices()
                if devices:
                    break
                time.sleep(0.3)
            return client, devices

        def done(payload):
            client, devices = payload
            self.client = client
            self.devices = devices
            save_config(host=host, port=port, user=user, password=password)
            self.conn_label.config(text=f"{host}:{port} 已连接", foreground="#2e7d32")
            self.status_var.set(f"发现 {len(devices)} 台设备")
            self._log(f"连接 {host}:{port} 成功，发现 {len(devices)} 台设备")
            self._set_busy(False)
            self.btn_disconnect.config(state=tk.NORMAL)
            # 自动打开上次使用的设备
            last = load_config().get("last_device")
            names = [d.name for d in devices]
            if last and last in names:
                self.device_combo["values"] = names
                self.device_var.set(last)
                self._log(f"自动打开上次设备 {last} ...")
                self.on_device_selected()
            else:
                self._fill_device_combo()

        self._run_async(work, done)

    def _fill_device_combo(self) -> None:
        names = [d.name for d in self.devices]
        self.device_combo["values"] = names
        if names:
            self.device_combo.current(0)

    @staticmethod
    def _usable_device(descs: List[SANEOptionDescriptor],
                       client: SaneClient) -> bool:
        """实测设备常用选项（mode/resolution）可否读写。

        epsonscan2 等后端在部分环境下常用选项 GET/SET 一律返回 INVAL，
        此时无法配置（如默认彩色），应视为不可用并尝试其他后端。
        """
        from .models import SANEControlOptionRequest as _Req
        for i, d in enumerate(descs):
            if d.name not in ("mode", "resolution"):
                continue
            if d.type in (SANEValueType.SANE_TYPE_GROUP,
                          SANEValueType.SANE_TYPE_BUTTON):
                continue
            try:
                r = client.control_option(_Req(
                    handle=client.handle, option=i, action=1,
                    value_type=d.type, value_size=d.size))
                if r.status == SANEStatus.SANE_STATUS_GOOD:
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False

    def on_device_selected(self) -> None:
        if self.client is None or self._busy:
            return
        name = self.device_var.get()
        if not name:
            return
        self._set_busy(True)
        self.status_var.set(f"打开 {name} ...")
        self._log(f"自动打开设备 {name}")

        def work():
            candidates = [name] + [d.name for d in self.devices if d.name != name]
            last: Optional[Exception] = None
            for n in candidates:
                try:
                    self._open_with_retry(n)
                    descs = self.client.get_option_descriptors()
                    if not self._usable_device(descs, self.client):
                        self._log(
                            f"设备 {n} 常用选项不可读写（INVAL），尝试其他后端...",
                            logging.WARNING,
                        )
                        last = SaneError(
                            SANEStatus.SANE_STATUS_INVAL,
                            f"设备 {n} 的选项无法设置，已尝试其他设备",
                        )
                        time.sleep(0.5)
                        continue
                    return n, descs
                except SaneError as e:
                    last = e
                    self._log(f"设备 {n} 打开失败: {e}", logging.WARNING)
                    time.sleep(0.5)
                    continue
            raise last if last else SaneError(SANEStatus.SANE_STATUS_IO_ERROR, "打开设备失败")

        def done(payload):
            name, descs = payload
            self.descriptors = descs
            # 实际打开的后端可能与所选不同（自动切换），更新下拉显示
            self.device_var.set(name)
            self._fill_scan_defaults()
            self.conn_label.config(text=name, foreground="#000")
            self.status_var.set(f"已打开 {name}")
            self._log(f"设备 {name} 共 {len(descs)} 个选项")
            save_config(last_device=name)
            self._set_busy(False)

        self._run_async(work, done)

    def on_disconnect(self) -> None:
        if self.client is not None:
            try:
                self.client.exit()
            except Exception:
                pass
            self.client = None
        self.devices = []
        self.descriptors = []
        self.opt_index = {}
        self.frames = []
        self._session = []
        self.device_combo["values"] = []
        self.device_var.set("")
        self.mode_combo["values"] = []
        self.mode_var.set("")
        self.paper_combo["values"] = []
        self.paper_var.set("")
        self.conn_label.config(text="未连接", foreground="#888")
        self.status_var.set("未连接")
        self.btn_disconnect.config(state=tk.DISABLED)
        self.btn_scan.config(state=tk.DISABLED)
        self.canvas.delete("all")
        self.canvas.create_text(12, 16, anchor=tk.NW, fill="#ccc",
                                text="扫描结果将显示在这里", tags=("hint",))
        self._log("已断开")

    def _open_with_retry(self, name: str) -> SaneClient:
        last_error: Optional[Exception] = None
        for attempt in (1, 2):
            client = self.client
            if client is None:
                self._log("重新连接服务器...")
                host = self.host_var.get().strip()
                port = int(self.port_var.get().strip() or "6566")
                client = self._make_client(host, port, self.user_var.get(), self.pass_var.get())
                self.client = client
            try:
                if client.handle >= 0:
                    try:
                        client.close()
                    except (ConnectionError, OSError):
                        client.disconnect()
                        self.client = None
                        continue
                status = client.open(name)
                if status != SANEStatus.SANE_STATUS_GOOD:
                    raise SaneError(
                        status,
                        f"设备 {name} 打开失败（{status}）。"
                        f"若为设备忙（BUSY/IO_ERROR），可能被其他程序占用，请稍候重试。",
                    )
                return client
            except (ConnectionError, OSError) as e:
                last_error = e
                self._log(f"连接中断（{e}），正在重连...")
                try:
                    client.disconnect()
                except Exception:
                    pass
                self.client = None
                if attempt == 2:
                    break
                time.sleep(0.5)
            except SaneError:
                raise
        raise SaneError(
            SANEStatus.SANE_STATUS_IO_ERROR,
            f"打开设备失败：{last_error or '未知错误'}。请确认设备未被占用后重试。",
        )

    def _ensure_device_open(self) -> Optional[str]:
        name = self.device_var.get() or (self.devices[0].name if self.devices else None)
        if name is None:
            return None
        if self.client is None or self.client.handle < 0:
            self._log(f"自动打开设备 {name} ...")
            self.client = self._open_with_retry(name)
            self.descriptors = self.client.get_option_descriptors()
            self._fill_scan_defaults()
        return name

    # ------------------------------------------------------------ 常规属性

    def _fill_scan_defaults(self) -> None:
        """从设备选项填充模式/纸张/分辨率三个下拉，并记录选项 index。"""
        self.opt_index = {}
        mode_list = paper_list = res_values = None
        for i, d in enumerate(self.descriptors):
            if d.name == "mode" and d.constraint.constraint_type == SANEConstraintType.SANE_CONSTRAINT_STRING_LIST:
                mode_list = d.constraint.string_list
                self.opt_index["mode"] = i
            elif d.name == "scan-area" and d.constraint.constraint_type == SANEConstraintType.SANE_CONSTRAINT_STRING_LIST:
                paper_list = d.constraint.string_list
                self.opt_index["scan-area"] = i
            elif d.name == "br-x" and d.type == SANEValueType.SANE_TYPE_FIXED:
                self.opt_index.setdefault("br-x", i)
            elif d.name == "br-y" and d.type == SANEValueType.SANE_TYPE_FIXED:
                self.opt_index.setdefault("br-y", i)
            elif d.name == "resolution":
                self.opt_index["resolution"] = i
                ct = d.constraint.constraint_type
                if ct == SANEConstraintType.SANE_CONSTRAINT_WORD_LIST:
                    res_values = [str(v) for v in d.constraint.word_list]
                elif ct == SANEConstraintType.SANE_CONSTRAINT_RANGE:
                    r = d.constraint.range
                    if r.min > 0:
                        common = [v for v in (75, 100, 150, 200, 300, 600)
                                  if r.min <= v <= r.max]
                        if 200 not in common and r.min <= 200 <= r.max:
                            common.append(200)
                        common.sort()
                        if r.min not in common:
                            common.insert(0, r.min)
                        if r.max not in common:
                            common.append(r.max)
                        res_values = [str(v) for v in common]

        # 模式（默认彩色）
        if mode_list:
            zh = [_zh_mode(m) for m in mode_list]
            self.mode_combo["values"] = zh
            if "彩色" in zh:
                self.mode_var.set("彩色")
            else:
                self.mode_var.set(zh[0])
        else:
            self.mode_combo["values"] = []
            self.mode_var.set("")

        # 纸张规格（默认 A4；无 scan-area 时用 br-x/br-y 区域坐标）
        if paper_list:
            zh = [_zh_paper(p) for p in paper_list]
            self.paper_combo.config(state="readonly")
            self.paper_combo["values"] = zh
            if "A4" in zh:
                self.paper_var.set("A4")
            else:
                self.paper_var.set(zh[0])
            self.paper_mode = "scan-area"
        elif "br-x" in self.opt_index and "br-y" in self.opt_index:
            # epson2 等后端：用 br-x/br-y 毫米坐标模拟纸张规格
            zh = [_zh_paper(p) for p in
                  ("Maximum", "A4", "Letter", "A5", "A6")]
            self.paper_combo.config(state="readonly")
            self.paper_combo["values"] = zh
            self.paper_var.set("A4")
            self.paper_mode = "region"
        else:
            self.paper_combo.config(state=tk.DISABLED)
            self.paper_combo["values"] = []
            self.paper_var.set("（该设备不支持）")
            self.paper_mode = None

        # 分辨率（范围/列表存在则按其生成）
        if res_values:
            self.res_combo["values"] = res_values
            if "200" in res_values:
                self.res_var.set("200")
            else:
                # 无 200 时选最接近 200 的合法值
                nums = [int(v) for v in res_values]
                nearest = min(nums, key=lambda x: abs(x - 200))
                self.res_var.set(str(nearest))
        else:
            self.res_combo["values"] = ["75", "100", "150", "200", "300", "600"]
            self.res_var.set("200")

        self.btn_scan.config(state=tk.NORMAL)

    # ------------------------------------------------------------ 扫描 / 连续扫描

    def on_scan(self) -> None:
        if self.client is None or self._busy:
            return
        if not self.descriptors:
            messagebox.showinfo("提示", "请先打开设备")
            return
        self._cancel = False
        self.frames = []
        self.progress["value"] = 0
        self._set_busy(True)
        self.btn_cancel.config(state=tk.NORMAL)
        mode = _en_mode(self.mode_var.get().strip()) if self.mode_var.get() else None
        paper = _en_paper(self.paper_var.get().strip()) if self.paper_var.get() else None
        try:
            resolution = int(self.res_var.get().strip())
        except ValueError:
            messagebox.showerror("错误", "分辨率必须是数字")
            self._set_busy(False)
            return
        page = len(self._session) + 1
        self.status_var.set(f"扫描第 {page} 页...")
        self._log(f"开始扫描第 {page} 页（模式={mode}，纸张={paper}，分辨率={resolution}）")

        def work():
            name = self._ensure_device_open()
            if name is None:
                raise SaneError(SANEStatus.SANE_STATUS_INVAL, "请先选择设备")
            try:
                return self._do_scan(name, mode, paper, resolution)
            except (ConnectionError, OSError) as e:
                self._log(f"扫描中连接中断（{e}），自动重连后重试...")
                self.client = self._open_with_retry(name)
                self.descriptors = self.client.get_option_descriptors()
                self._fill_scan_defaults()
                return self._do_scan(name, mode, paper, resolution)

        def done(frames):
            self.btn_cancel.config(state=tk.DISABLED)
            if not frames:
                self.status_var.set("已取消")
                self._set_busy(False)
                return
            self.frames = frames
            self._session.extend(frames)
            self._show_preview(frames[0])
            self.status_var.set(f"第 {len(self._session)} 页完成 "
                                f"({frames[0].params.pixels_per_line}x{frames[0].params.lines})")
            self._log(f"第 {len(self._session)} 页完成")
            self.btn_save_bmp.config(state=tk.NORMAL)
            self.btn_save_png.config(state=tk.NORMAL)
            self.btn_save_pdf.config(state=tk.NORMAL)
            if self.cont_var.get():
                self._set_busy(False)
                cont = messagebox.askyesno("连续扫描",
                                           f"已扫描 {len(self._session)} 页，是否继续扫描下一页？")
                if cont:
                    self.progress["value"] = 0
                    self.on_scan()
                    return
            self._finish_session()

        self._run_async(work, done)

    def _finish_session(self) -> None:
        self._set_busy(False)
        if not self._session:
            return
        n = len(self._session)
        if n == 1:
            path = self._save_png(self._session[0], self.save_dir)
        else:
            path = self._save_pdf(self._session, self.save_dir)
        self.status_var.set(f"完成 {n} 页，已保存: {os.path.basename(path)}")
        self._log(f"已保存 {n} 页到 {path}")
        messagebox.showinfo(
            "扫描完成",
            f"共扫描 {n} 页\n模式：{self.mode_var.get().strip() or '默认'}\n\n"
            f"已保存到：\n{path}",
        )

    def _do_scan(self, name: str, mode, paper, resolution: int):
        """在已打开的连接上应用常用属性并执行扫描。"""
        for opt_name, val in (("mode", mode), ("resolution", resolution)):
            if val is None:
                continue
            i = self.opt_index.get(opt_name)
            if i is None:
                continue
            d = self.descriptors[i]
            if d.type in (SANEValueType.SANE_TYPE_BUTTON,
                          SANEValueType.SANE_TYPE_GROUP):
                continue
            self._set_option(i, d, val)

        # 纸张规格：scan-area 字符串 / br-x+br-y 毫米区域
        if paper is not None:
            if self.paper_mode == "scan-area":
                i = self.opt_index.get("scan-area")
                if i is not None:
                    d = self.descriptors[i]
                    self._set_option(i, d, paper)
            elif self.paper_mode == "region" and paper != "Maximum":
                w, h = PAPER_MM.get(paper, PAPER_MM["A4"])
                for opt_name, mm in (("br-x", w), ("br-y", h)):
                    i = self.opt_index.get(opt_name)
                    if i is None:
                        continue
                    d = self.descriptors[i]
                    self._set_option(i, d, float(mm))

        port, byte_order = self.client.start()
        frames = self.client.scan_all_frames(
            port, byte_order, progress_callback=self._on_progress
        )
        if self._cancel:
            return []
        if not frames:
            raise SaneError(SANEStatus.SANE_STATUS_NO_DOCS, "未收到图像帧（可能没有文档）")
        return frames

    def _set_option(self, index: int, desc: SANEOptionDescriptor, value) -> None:
        req = SANEControlOptionRequest(
            handle=self.client.handle, option=index,
            action=int(SANEAction.SANE_ACTION_SET_VALUE),
            value_type=desc.type, value_size=desc.size, values=[value],
        )
        reply = self.client.control_option(req)
        if reply.status != SANEStatus.SANE_STATUS_GOOD:
            zh_name = OPTION_ZH.get(desc.name, desc.name or "(未命名)")
            raise SaneError(
                reply.status,
                f"设置「{zh_name}」={value} 失败（SANE 状态码 {reply.status}）",
            )

    def _on_progress(self, percent: int) -> None:
        self._msg_queue.put(("progress", percent, None))

    def on_cancel(self) -> None:
        self._cancel = True
        self.status_var.set("正在取消...")
        self._log("请求取消扫描")

    # ------------------------------------------------------------ 保存

    @staticmethod
    def _stamp() -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def _device_short(self) -> str:
        """设备简称：取设备名中可读的一段（如 L3110），否则用后端名。"""
        name = self.device_var.get() or ""
        parts = name.split(":")
        for p in parts[1:]:
            p = p.strip()
            if not p:
                continue
            if p.lower() in ("libusb", "esci2", "usb"):
                continue
            if p.isdigit():
                continue
            return p.split(" ")[0]
        return parts[0] if parts and parts[0] else "扫描仪"

    def _name_template(self) -> str:
        scheme = self.naming_var.get()
        if scheme == NAME_CUSTOM:
            return load_config().get("name_template") or "scan_{date}_{time}_{mode}"
        return NAME_SCHEMES.get(scheme, "scan_{date}_{time}_{mode}")

    def _on_naming_selected(self, _event=None) -> None:
        if self.naming_var.get() == NAME_CUSTOM:
            tpl = simpledialog.askstring(
                "自定义命名模板",
                "可用占位符：\n"
                "{date}   日期（20260907）\n"
                "{time}   时间（201521）\n"
                "{mode}   模式（彩色/灰度/黑白）\n"
                "{device} 设备简称（L3110）\n"
                "{n}      页数（多页时 _3页，单页为空）\n\n"
                "示例：扫描_{date}_{mode}",
                initialvalue=load_config().get("name_template")
                            or "scan_{date}_{time}_{mode}",
            )
            if tpl:
                save_config(name_template=tpl)
            else:
                self.naming_var.set(load_config().get("name_scheme",
                                                      "scan_日期_时间_模式"))
        save_config(name_scheme=self.naming_var.get())

    def _make_filename(self, ext: str, pages: int = 1) -> str:
        """按命名规则生成文件名。

        占位符：{date}{time}{mode}{device}{n}；扩展名自动追加。
        例：scan_20260907_201234_彩色.png
            scan_20260907_201234_彩色_3页.pdf
        """
        stamp = self._stamp()
        date_s, time_s = stamp.split("_")
        mode = self.mode_var.get().strip() or "默认"
        tpl = self._name_template()
        s = tpl
        s = s.replace("{date}", date_s)
        s = s.replace("{time}", time_s)
        s = s.replace("{mode}", mode)
        s = s.replace("{device}", self._device_short())
        s = s.replace("{n}", f"{pages}页" if pages > 1 else "")
        # 模板未用 {n} 且为多页时，末尾自动补页数
        if pages > 1 and "{n}" not in tpl:
            s += f"_{pages}页"
        s = s.replace("{ext}", "")
        s = s.strip(" _-")
        if not s:
            s = f"scan_{stamp}"
        return f"{s}.{ext}"

    def _save_png(self, frame, directory: str) -> str:
        path = os.path.join(directory, self._make_filename("png"))
        with open(path, "wb") as f:
            f.write(frame_to_png(frame))
        return path

    def _save_pdf(self, frames, directory: str) -> str:
        path = os.path.join(directory, self._make_filename("pdf", len(frames)))
        with open(path, "wb") as f:
            f.write(frames_to_pdf(frames))
        return path

    def on_save_bmp(self) -> None:
        if not self.frames:
            return
        path = filedialog.asksaveasfilename(
            initialdir=self.save_dir,
            initialfile=f"scan_{self._stamp()}.bmp",
            defaultextension=".bmp", filetypes=[("BMP", "*.bmp")])
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(frame_to_bmp(self.frames[0]))
            self._log(f"已保存 {path}")
            self.status_var.set(f"已保存 {os.path.basename(path)}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("错误", str(e))

    def on_save_png(self) -> None:
        if not self.frames:
            return
        path = filedialog.asksaveasfilename(
            initialdir=self.save_dir,
            initialfile=f"scan_{self._stamp()}.png",
            defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(frame_to_png(self.frames[0]))
            self._log(f"已保存 {path}")
            self.status_var.set(f"已保存 {os.path.basename(path)}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("错误", str(e))

    def on_save_pdf(self) -> None:
        if not self._session:
            return
        path = filedialog.asksaveasfilename(
            initialdir=self.save_dir,
            initialfile=f"scan_{self._stamp()}.pdf",
            defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(frames_to_pdf(self._session))
            self._log(f"已保存 {path}")
            self.status_var.set(f"已保存 {os.path.basename(path)}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("错误", str(e))

    # ------------------------------------------------------------ 预览

    def _show_preview(self, frame) -> None:
        try:
            png = frame_to_png(frame)
            self._full_photo = tk.PhotoImage(data=png)
            self._img_w = self._full_photo.width()
            self._img_h = self._full_photo.height()
            self._preview_fit = True
            self._preview_scale = 1.0
            self._draw_preview()
        except Exception as e:  # noqa: BLE001
            self._log(f"预览失败: {e}", logging.ERROR)

    def _draw_preview(self) -> None:
        if self._full_photo is None:
            return
        cw = max(self.canvas.winfo_width(), 60)
        ch = max(self.canvas.winfo_height(), 60)
        if self._preview_fit:
            self._preview_scale = min(cw / self._img_w, ch / self._img_h)
        max_pixels = 4000 * 4000
        if self._img_w * self._img_h * (self._preview_scale ** 2) > max_pixels:
            self._preview_scale = (max_pixels / (self._img_w * self._img_h)) ** 0.5
        self._preview_scale = min(max(self._preview_scale, 0.02), 8.0)
        if self._preview_scale <= 1.0:
            s = max(1, round(1.0 / self._preview_scale))
            photo = self._full_photo.subsample(s, s)
            dw, dh = self._img_w / s, self._img_h / s
        else:
            z = max(1, int(self._preview_scale))
            photo = self._full_photo.zoom(z, z)
            dw, dh = self._img_w * z, self._img_h * z
        self._photo = photo
        self.canvas.delete("all")
        self.canvas.create_image(cw / 2, ch / 2, anchor=tk.CENTER, image=photo)
        self.zoom_label.config(text=f"缩放: {self._preview_scale:.2f}x "
                                    f"({self._img_w}x{self._img_h})")

    def _on_canvas_resize(self, _event) -> None:
        if self._preview_fit and self._full_photo is not None:
            self._draw_preview()

    def _on_mousewheel(self, event) -> None:
        if self._full_photo is None:
            return
        self._preview_fit = False
        step = 1.2 if event.delta > 0 else 1 / 1.2
        self._preview_scale *= step
        self._draw_preview()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    root = tk.Tk()
    SaneGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
