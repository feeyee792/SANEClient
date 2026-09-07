# -*- coding: utf-8 -*-
"""重连逻辑针对性测试：连接中断后 _open_with_retry 应自动重建连接并成功打开设备。

用法: python tests/gui_reconnect.py [host] [port]
"""
from __future__ import annotations

import sys
import tkinter as tk

sys.path.insert(0, ".")

from sanewin.client import SaneClient  # noqa: E402
from sanewin.gui import SaneGui  # noqa: E402

HOST = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.230"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 6566
DEVICE = ("epsonscan2:L3110 Series:58364E5A3332363816:esci2:usb:ES016D:4418"
          if len(sys.argv) <= 3 else sys.argv[3])

root = tk.Tk()
root.withdraw()
g = SaneGui(root)

# 1. 手动建立连接（模拟用户点"连接"）
c = SaneClient(HOST, PORT)
assert c.init() == 0, "init 失败"
g.client = c
print("连接 OK")

# 2. 首次打开
g._open_with_retry(DEVICE)
assert g.client.handle >= 0
print(f"首次打开 OK (handle={g.client.handle})")

# 3. 模拟服务器中止连接
g.client.disconnect()
print(f"模拟断开 (handle={g.client.handle})")

# 4. 再次打开 → 应自动重连
g._open_with_retry(DEVICE)
assert g.client is not None and g.client.handle >= 0, "重连失败"
print(f"自动重连并打开 OK (handle={g.client.handle}, 新连接={g.client._control is not None})")

g.client.exit()
root.destroy()
print("RECONNECT TEST OK")
