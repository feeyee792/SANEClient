# SANE 扫描客户端 / SANE Scanner Client

[English](#english) · [中文](#中文)

一个基于 **SANE 网络协议** 的跨平台扫描客户端，用 **Python 零第三方依赖** 实现：
协议层 → 图像编码 → 命令行 CLI → tkinter 图形界面，完整可用。

A cross-platform SANE network-protocol scanner client, implemented in
**pure Python with zero third-party dependencies**: protocol layer → image
encoders → CLI → tkinter GUI, fully usable.

> 本项目从 VB.NET 原版 SANEWinDS 重构而来，修复了原版多项缺陷（见
> [与 VB 原版的差异](#与-vb-原版的差异--fixes-vs-original)）。
> Rebuilt from the VB.NET SANEWinDS original, with several original bugs fixed.

---

## 目录 / Table of Contents

1. [功能特性 / Features](#功能特性--features)
2. [技术栈 / Tech Stack](#技术栈--tech-stack)
3. [架构与协议流程 / Architecture & Protocol](#架构与协议流程--architecture--protocol)
4. [目录结构 / Project Layout](#目录结构--project-layout)
5. [快速开始 / Quick Start](#快速开始--quick-start)
6. [作为库使用 / Use as a Library](#作为库使用--use-as-a-library)
7. [配置持久化 / Persistence](#配置持久化--persistence)
8. [命名规则 / Naming Rules](#命名规则--naming-rules)
9. [图像编码规格 / Image Encoders](#图像编码规格--image-encoders)
10. [打包 exe / Standalone exe](#打包-exe--standalone-exe)
11. [测试 / Testing](#测试--testing)
12. [与 VB 原版的差异 / Fixes vs. Original](#与-vb-原版的差异--fixes-vs-original)
13. [测试设备与注意事项 / Tested Device & Notes](#测试设备与注意事项--tested-device--notes)
14. [兼容性与已知限制 / Compatibility & Limitations](#兼容性与已知限制--compatibility--limitations)
15. [常见问题 / FAQ](#常见问题--faq)
16. [开源协议 / License](#开源协议--license)
17. [致谢 / Credits](#致谢--credits)

---

## 功能特性 / Features

### 协议层 / Protocol Layer

完整实现 SANE 网络协议（SANE Network Protocol，rfc 由 `saned` 提供服务），
支持以下 RPC / full SANE net protocol with these RPCs:

| RPC | 说明 / Description |
|---|---|
| `SANE_NET_INIT` | 握手，版本协商 / handshake & version negotiation |
| `SANE_NET_GET_DEVICES` | 枚举设备 / enumerate devices |
| `SANE_NET_OPEN` | 打开设备 / open a device |
| `SANE_NET_CLOSE` | 关闭设备 / close a device |
| `SANE_NET_GET_OPTION_DESCRIPTORS` | 读取全部选项约束 / option descriptors |
| `SANE_NET_CONTROL_OPTION` | 读 / 写选项（get/set value） |
| `SANE_NET_GET_PARAMETERS` | 读取当前帧参数 / current frame parameters |
| `SANE_NET_START` | 开始扫描，返回数据端口 / start scan, returns data port |
| `SANE_NET_CANCEL` | 取消扫描 / cancel scan |
| `SANE_NET_EXIT` | 退出会话 / exit session |
| 数据端口 / data port | 帧头 + 原始像素流 / frame header + raw pixel stream |

协议细节：网络字节序（big-endian）、`STRING_LIST` 正确解析（含终止空串）、
`$MD5$` 挑战-响应认证、16-bit 深度帧取高字节、服务器版本不匹配仅告警不中断。

### 图像层 / Imaging

纯手写编码器，无任何图像库依赖 / hand-written encoders, no imaging libs:

- **BMP**：1/4/8/24/32-bit 位深，RGB / 分离帧自动合并；
- **PNG**：无第三方库实现的 zlib/CRC32/IHDR/IDAT/IEND 结构编码；
- **PDF**：多页 PDF 1.4（FlateDecode），DeviceGray / DeviceRGB，
  支持 R、G、B 分离帧自动合成彩色页。

### 图形界面（tkinter，零依赖）/ GUI

- 左侧「主机信息 / 设备 / 扫描设置」，右侧「预览与保存」，顶部菜单栏；
- 主机配置（地址 / 端口 / 用户名 / 密码）持久化，**启动自动连接**并
  **自动打开上一次使用的设备**；
- 模式 / 纸张规格 / 分辨率下拉框**按设备真实约束自动生成**（默认彩色）；
- 同机多后端自动切换（设备被占用时自动尝试另一后端）；
- 连续扫描（多页合成 PDF）、命名规则（预设 + 自定义模板）、扫描完成弹窗、
  「打开保存文件夹」按钮、单页 BMP / PNG / 多页 PDF 另存；
- 连接异常自动重连，扫描进度条实时显示。

### 命令行 / CLI

`python -m sanewin` 提供完整命令行：

| 命令 / Command | 说明 / Description |
|---|---|
| `list` | 列出设备 / list devices |
| `open <device>` | 打开设备并打印选项 / open & dump options |
| `scan` | 扫描并保存 PNG（可带 `--mode/--dpi/--paper/--pdf/--out`） |
| `--ini <file>` | 读取原版 SANEWinDS.ini 主机配置 / read legacy INI |

---

## 技术栈 / Tech Stack

| 层 / Layer | 技术 / Tech | 说明 / Notes |
|---|---|---|
| 语言 / Language | Python 3.8+ | 全项目 / entire project |
| 协议 / Protocol | 标准库 `socket` / `struct` / `hashlib` | 网络字节序序列化 / wire format |
| 图像 / Imaging | 纯手写编码器 | BMP / PNG / PDF |
| 界面 / GUI | `tkinter`（标准库） | 零第三方依赖 / zero deps |
| 打包 / Packaging | PyInstaller 6.x（仅打包时） | 单文件 exe / one-file exe |
| 测试 / Testing | `unittest`（标准库） | 24 项测试 / 24 tests |

---

## 架构与协议流程 / Architecture & Protocol

### 模块依赖 / Module Dependencies

```
sanewin/
├── constants.py   # SANE 常量与枚举 / constants & enums
├── models.py      # 数据结构 / data models（SANEOptionDescriptor 等）
├── protocol.py    # WireWriter / WireReader：网络字节序序列化 / wire serialization
├── client.py      # SaneClient：RPC + 图像帧采集（控制口 + 数据口）/ RPC + capture
├── images.py      # raw 帧 → BMP / PNG / PDF / encoders
├── config.py      # 原版 SANEWinDS.ini 主机配置读取 / legacy INI reader
├── cli.py         # 命令行入口 / CLI
├── gui.py         # tkinter 界面 / GUI
└── __main__.py    # python -m sanewin 入口 / entry
```

依赖方向：`gui.py / cli.py → client.py → protocol.py → constants.py`，
`gui.py → images.py`，`gui.py → config.py`。各层之间无循环依赖。

### 一次扫描的协议流程 / Scan Sequence

```
客户端 Client                    服务器 Server (saned)
    │  init (版本协商)              │
    ├─────────────────────────────►│
    │  get_devices                 │
    │◄─────────────────────────────┤
    │  open <设备名>               │
    ├─────────────────────────────►│
    │  get_option_descriptors      │
    │◄─────────────────────────────┤
    │  control_option(设置值)      │
    ├─────────────────────────────►│
    │  start → 返回数据端口号      │
    │◄─────────────────────────────┤
    │  ┌─────── 数据端口（新连接） ────────┐
    │  │  get_parameters             │
    │  │◄───────────────────────────┤
    │  │  帧头 + 原始像素流         │
    │  │◄───────────────────────────┤
    │  └────────────────────────────┘
    │  编码：帧 → BMP / PNG / PDF   │
    │  close / exit                 │
    ├─────────────────────────────►│
```

关键细节 / key details：

- 控制连接与数据连接分离；数据端口由服务器在 `SANE_NET_START` 响应中下发；
- 帧数据以 `SANE_FRAME_*` 类型 + 尺寸 + 行距（lines）描述，客户端据此
  重组像素矩阵；
- 彩色帧可能以 R / G / B 三个分离帧下发，编码器自动合并；
- `STRING_LIST` 以 `count` 计实际字符串数，末尾终止空串不入数组；
- 认证：服务器返回 `$MD5$<salt>` 时，客户端以 `$MD5$<salt><md5(salt+password)>`
  应答。

---

## 目录结构 / Project Layout

```
SANE扫描客户端/                 # 仓库根 = 本项目 / repo root = this project
├── sanewin/                    # ★ 核心包 / core package
│   ├── __init__.py            # 包导出 / package exports
│   ├── __main__.py            # python -m sanewin 入口 / entry
│   ├── constants.py           # SANE 常量与枚举 / constants & enums
│   ├── models.py              # 数据结构 / data models
│   ├── protocol.py            # 序列化层 / wire serialization
│   ├── client.py              # SaneClient：RPC + 帧采集 / RPC + capture
│   ├── images.py              # BMP / PNG / PDF 编码 / encoders
│   ├── config.py              # 原版 INI 主机配置读取 / legacy INI reader
│   ├── cli.py                 # 命令行 / CLI
│   └── gui.py                 # tkinter 界面 / GUI
├── tests/                     # 测试 / tests（见“测试”节）
├── assets/                    # 应用图标 / app icon（app_icon.ico / source.png）
├── dist/                      # Windows 单文件 exe 发布产物 / standalone exe
├── run_gui.py                 # PyInstaller 打包入口 / packaging entry
├── version_info.txt           # exe 版本信息 / exe version info
├── LICENSE.txt                # GPL-3.0
├── .gitignore                 # 忽略规则 / ignore rules
└── README.md                  # 本文档 / this file
```

---

## 快速开始 / Quick Start

要求 / Requirements：**Python 3.8+**，无任何第三方依赖 / no third-party
dependencies。以下命令均在仓库根运行 / all commands run from the repo root.

### 图形界面 / GUI

```bash
python -m sanewin.gui
```

1. 左侧「主机信息」填 SANE 服务器地址（示例 `192.168.1.230:6566`，换成你
   自己的服务器），可填用户名 / 密码（服务器要求时）/ enter your SANE server
   address (example `192.168.1.230:6566`), plus user/password if required.
2. 点「连接」→ 设备下拉自动出现 → 选择设备即自动打开 /
   click Connect → device dropdown populates → picking one auto-opens it.
3. 设置模式 / 纸张 / 分辨率（按设备约束自动生成下拉，默认彩色）→「扫描」/
   set mode/paper/resolution (defaults: Color) → Scan.
4. 结果自动保存到自定义目录并预览；勾选「连续扫描」可多页合成 PDF /
   results auto-save to your directory and preview; batch mode merges to PDF.
5. 「保存 BMP / PNG / PDF」手动另存 / manual save buttons.

下次启动自动连接并打开上次设备 / next launch auto-connects & reopens last
device。

### 命令行 / CLI

```bash
# 列出设备 / list devices
python -m sanewin list --host 192.168.1.230 --port 6566

# 打开设备并打印全部选项约束 / open & dump option constraints
python -m sanewin open "epson2:libusb:002:007" --host 192.168.1.230

# 扫描为 PNG（灰度 300dpi）/ scan to PNG (gray, 300dpi)
python -m sanewin scan "epson2:libusb:002:007" --host 192.168.1.230 --mode Gray --dpi 300 --out scan.png

# 扫描为多页 PDF（连续扫描）/ scan to multi-page PDF (batch)
python -m sanewin scan "epson2:libusb:002:007" --host 192.168.1.230 --pdf --out scan.pdf

# 使用原版 SANEWinDS.ini 的主机配置 / read host config from legacy INI
python -m sanewin scan "epson2:libusb:002:007" --ini "SANEWinDS.ini" --out scan.png
```

---

## 作为库使用 / Use as a Library

`sanewin` 是普通 Python 包，可直接 import 使用 / a regular package:

```python
from sanewin import SaneClient, SANEAction, SANEValueType
from sanewin.models import SANEControlOptionRequest
from sanewin.images import frame_to_bmp

client = SaneClient("192.168.1.230", 6566, username="", password="")
client.init()
devices = client.get_devices()
client.open(devices[0].name)

descs = client.get_option_descriptors()
idx = next(i for i, d in enumerate(descs) if d.name == "resolution")
client.control_option(SANEControlOptionRequest(
    handle=client.handle, option=idx,
    action=int(SANEAction.SANE_ACTION_SET_VALUE),
    value_type=SANEValueType.SANE_TYPE_INT, value_size=4, values=[200],
))

port, byte_order = client.start()
frames = client.scan_all_frames(port, byte_order, progress_callback=lambda p: print(p))
bmp = frame_to_bmp(frames[0])
open("scan.bmp", "wb").write(bmp)
client.close()
client.exit()
```

---

## 配置持久化 / Persistence

GUI 配置保存在 `~/.sanewin/config.json`（用户主目录，跨平台），
无需管理员权限 / config lives in `~/.sanewin/config.json` (per-user, no admin
required):

| 键 / Key | 说明 / Description | 默认 / Default |
|---|---|---|
| `host` | SANE 服务器地址 / server address | `192.168.1.230` |
| `port` | 端口 / port | `6566` |
| `user` | 用户名（服务器要求时）/ username | `""` |
| `password` | 密码 / password | `""` |
| `last_device` | 上次使用的设备名，启动自动打开 / last device, auto-opened at launch | `""` |
| `save_dir` | 扫描文件保存目录 / scan save directory | `~/.sanewin/scans` |
| `name_scheme` | 命名规则方案 / naming scheme | `scan_日期_时间_模式` |
| `name_template` | 自定义模板（自定义方案时）/ custom template | `""` |

---

## 命名规则 / Naming Rules

GUI 提供命名规则下拉框，多种方案可选，也可自定义模板 /
several built-in schemes plus a custom template:

| 方案 / Scheme | 示例 / Example |
|---|---|
| `scan_日期_时间_模式`（默认 / default） | `scan_20260907_181530_彩色.png` |
| `日期_时间` | `20260907_181530.png` |
| `设备_日期_时间` | `L3110_20260907_181530.png` |
| `模式_日期_时间` | `彩色_20260907_181530.png` |
| `自定义...`（模板 / template） | 见下 / see below |

占位符 / placeholders（自定义模板可用 / usable in custom templates）:

| 占位符 / Token | 含义 / Meaning |
|---|---|
| `{date}` | 日期 YYYYMMDD / date |
| `{time}` | 时间 HHMMSS / time |
| `{mode}` | 模式中文名（彩色/灰度/黑白）/ mode in Chinese |
| `{device}` | 设备简称（如 L3110）/ short device name |
| `{n}` | 连续扫描页码（多页时自动补 `_N页`）/ page number in batch |

---

## 图像编码规格 / Image Encoders

| 格式 / Format | 规格 / Spec | 备注 / Notes |
|---|---|---|
| BMP | BITMAPFILEHEADER + BITMAPINFOHEADER，1/4/8/24/32bpp | RGB 分离帧自动合并 |
| PNG | IHDR/IDAT/IEND + zlib 压缩 + CRC32，8-bit RGB/Gray | 无第三方库 |
| PDF | PDF 1.4 多页，FlateDecode，DeviceGray/DeviceRGB | 分离帧自动合成彩色页 |

帧格式支持矩阵 / supported frame formats：

| 帧类型 / Frame Type | 编码结果 / Encoded As |
|---|---|
| `SANE_FRAME_GRAY`（8-bit） | 灰度 BMP / PNG / PDF |
| `SANE_FRAME_RGB`（24-bit） | 彩色 BMP / PNG / PDF |
| `SANE_FRAME_RED/GREEN/BLUE`（分离帧） | 自动合并为彩色 |
| `SANE_FRAME_GRAY`（16-bit） | 取高字节降为 8-bit |
| 未知帧类型 | 按灰度处理并告警 |

手扫仪（hand scanner）等特殊设备帧尺寸由服务器下发，按 `lines × bytes_per_line`
重组，不依赖固定比例。

---

## 打包 exe / Standalone exe

打包为 Windows 单文件 exe（含应用图标与版本信息）/ build a one-file Windows
exe (with icon & version info):

```bash
pip install pyinstaller
python -m PyInstaller --onefile --windowed --clean --noconfirm \
    --name "SANE扫描客户端" --icon assets/app_icon.ico \
    --version-file version_info.txt run_gui.py
```

产物 / Output：`dist/SANE扫描客户端.exe`。**必须**以 `run_gui.py` 为入口 /
**Must** use `run_gui.py` as the entry（`gui.py` 内部为相对导入，直接打包会报 /
`gui.py` uses relative imports and fails when packaged directly:
`ImportError: attempted relative import with no known parent package`）。

`dist/` 中的 exe 已提交到仓库，可直接下载分发 / the exe in `dist/` is
committed for direct download.

---

## 测试 / Testing

```bash
# 单元测试（协议序列化 + 图像编码，无需服务器）
# unit tests (protocol + image encoders, no server needed)
python -m unittest tests.test_protocol tests.test_client

# PDF 编码器结构校验（合成帧，无需服务器）
# PDF encoder structural checks (synthetic frames, no server needed)
python tests/test_pdf.py

# 真实服务器集成测试（默认 192.168.1.230:6566，不可达自动跳过；
# 可用 SANE_TEST_HOST / SANE_TEST_PORT / SANE_TEST_USER / SANE_TEST_PASSWORD 覆盖）
# real-server integration tests (auto-skip when unreachable)
python -m unittest tests.test_real_server -v

# GUI 端到端冒烟测试（连接 → 打开设备 → 扫描 → 保存 → 预览）
# GUI end-to-end smoke test (connect → open → scan → save → preview)
python tests/gui_smoke.py 192.168.1.230 6566

# GUI 断线重连测试 / GUI reconnect test
python tests/gui_reconnect.py 192.168.1.230 6566
```

| 测试文件 / File | 覆盖 / Covers |
|---|---|
| `test_protocol.py` | WireWriter/Reader 字节序、各类型编解码 / serialization |
| `test_client.py` | 图像帧编码（BMP/PNG，各种帧格式）/ frame encoders |
| `test_pdf.py` | 多页 PDF 结构 / PDF structure validation |
| `test_real_server.py` | 真实服务器 RPC 往返 / live-server RPC round-trips |
| `gui_smoke.py` | GUI 全流程（自动打开、下拉填充、扫描、命名、持久化）/ GUI E2E |
| `gui_reconnect.py` | 断线自动重连 / auto-reconnect on broken connection |

---

## 与 VB 原版的差异 / Fixes vs. Original

1. **STRING_LIST 约束解析**：原版按“数组上界 = 计数-2”再循环读取计数次，依赖
   末尾空记录且对空字符串判 `IsNot Nothing` 会越界；新版按协议规范读取 `count`
   个字符串并丢弃终止空字符串 / original relied on a trailing-empty-record
   convention and overflowed on empty strings; rewrite follows the spec and
   drops the terminating empty string.
2. **字符串编解码**：原版逐字节 `Chr/Asc`（Latin-1 语义），UTF-8 中文会乱码；
   新版统一 UTF-8 编解码 / original used byte-wise `Chr/Asc` (Latin-1),
   garbling UTF-8; rewrite uses UTF-8 throughout.
3. **数组边界**：`get_devices` / `get_option_descriptors` 不再依赖“最后一条记录
   必为空”的约定，遇空记录即停止，非空记录越界时自动扩展 / no longer assume a
   trailing empty record; stop on empty, auto-grow on overflow.
4. **超时与断连语义**：控制连接超时抛明确的 `ConnectionError`，图像数据端口区分
   “超时”与“服务端断开” / control-channel timeout raises a clear
   ConnectionError; data channel distinguishes timeout vs. server close.
5. **界面 / UI**：全新 tkinter 界面——主机持久化、启动自动连接、设备自动切换、
   按设备真实约束生成属性下拉、连续扫描、命名规则（原版为全量选项列表 +
   手动应用）/ brand-new tkinter UI with persistence, auto-connect, backend
   fallback, constraint-driven dropdowns, batch scanning, naming rules.

---

## 测试设备与注意事项 / Tested Device & Notes

> ⚠️ **提醒 / Important**：本项目开发与验收基于 **EPSON L3118** 一体机
> （USB 连接至 SANE 服务器）。以下为实测经验，**换用其他设备前请先阅读**。

This project was developed and field-tested on an **EPSON L3118** all-in-one
(connected via USB to the SANE server). Read this before using other devices.

### 测试环境 / Tested Environment

- 设备 / Device：EPSON L3118（一体机 / all-in-one，USB）
- SANE 服务器 / Server：Linux + `saned`（sanit，TCP 6566），协议版本 1.1.3
- 客户端 / Client：本项目 Python 实现，协议版本 1.0.3（版本不匹配仅告警）
- 同一台一体机被 **两个后端** 同时暴露 / the same device is exposed by **two
  backends**：`epson2:libusb:002:007` 与 `epsonscan2:L3110 Series:...`
  （后端报告名 / backend-reported name；实际型号以机身铭牌为准）

### 其他设备的注意事项 / Notes for Other Devices

1. **设备名与后端由服务器决定 / Device names & backends come from the server**：
   先用 `python -m sanewin list --host <服务器>` 查看实际设备列表，不要照抄
   本仓库示例中的设备名 / always `list` first — don't copy device names verbatim.

2. **模式（mode）取值因后端而异 / mode values differ by backend**：

   | 后端 / Backend | 合法值 / Legal values |
   |---|---|
   | `epsonscan2` | `Color` / `Grayscale` / `Monochrome` |
   | `epson2` | `Lineart` / `Gray` / `Color` |

   GUI 已按约束自动翻译为「彩色/灰度/黑白」；**CLI 传值必须用后端实际值** /
   the GUI translates to 彩色/灰度/黑白 automatically; the CLI needs the raw value.

3. **分辨率约束不同 / resolution constraints vary**：
   `epsonscan2` 为范围 `50–1200`（含 200）；`epson2` 仅为
   `75/150/300/600`（**无 200**）。GUI 会按 WORD_LIST / RANGE 自动生成下拉；
   无 200 时自动取最近合法值（150）/ WORD_LIST or RANGE; nearest legal value
   picked when 200 is missing.

4. **纸张规格支持差异 / paper size support varies**：
   有 `scan-area` 选项的设备（如 epsonscan2）直接设置 A4/Letter/…；
   没有该选项的设备（如 epson2）由客户端用 `br-x`/`br-y` 毫米区域坐标实现
   （A4=210×297mm 等）/ devices with `scan-area` set it directly; others fall
   back to `br-x`/`br-y` mm coordinates.

5. **扫描仪同一时刻只能被一个程序占用 / one program at a time**：
   被占用时表现为选项设置返回 `SANE_STATUS_INVAL`（状态码 4）或连接中断
   （`server sent incomplete data`）。关闭占用程序后重试 / when busy, options
   return INVAL or the connection drops; close the other program and retry.

6. **需要认证的服务器 / servers requiring auth**：用户名/密码已在协议层支持
   （`$MD5$` 挑战-响应）；GUI 左侧「主机信息」填写即可 / user/password supported
   via `$MD5$` challenge-response; fill them in the GUI's Host section.

7. **ADF / 连续扫描**：连续扫描按页逐张进纸，取决于设备是否支持 ADF；
   L3118 为平板（Flatbed），一次一页 / batch mode feeds page by page and
   depends on ADF support; L3118 is a flatbed (one page at a time).

8. **16-bit / 高深度**：部分后端支持 16-bit 帧；协议按网络字节序取高字节，
   编码器自动降为 8-bit 处理 / 16-bit frames are handled (high byte per the
   wire byte order) and encoded down to 8-bit.

---

## 兼容性与已知限制 / Compatibility & Limitations

- **平台 / OS**：Windows / macOS / Linux 均可用（tkinter 为标准库）；
  「打开保存文件夹」按钮在非 Windows 上自动降级为 `xdg-open` / `open`。
- **Python**：3.8+（未使用 3.9+ 专属语法）。
- **服务器版本不匹配**：客户端 1.0.3 对服务器 1.1.3 仅告警，可正常使用。
- **设备占用**：扫描仪同一时刻只允许一个程序访问（见上文注意 5）。
- **分辨率 200**：设备约束不含 200 时自动取最近合法值，不会报错。
- **网络**：默认连接超时 10s；局域网外使用请先确认端口可达（6566/tcp）。
- **编码性能**：PNG/PDF 使用纯 Python 压缩，超大分辨率扫描较慢
  （A4@300dpi 约 2500×3500 像素，可接受）。

---

## 常见问题 / FAQ

**Q: 连接失败 / 超时？** 确认服务器 `saned` 已监听 6566 端口且防火墙放行；
`telnet <服务器> 6566` 可快速验证。

**Q: 设备被占用（选项设置报 INVAL 或连接断开）？** 扫描仪同一时刻只能被一个
程序访问。关闭占用程序（如其它扫描软件）后重试。GUI 会自动尝试切换同机的
另一个后端。

**Q: `server sent incomplete data`？** 通常是设备被占用导致的连接中断，不是
代码问题；空闲时重试即可。

**Q: 版本不匹配（client 1.0.3 / server 1.1.3）？** 仅告警，不影响使用。

**Q: 我的设备分辨率没有 200？** 按设备真实约束自动取最近合法值（如 150），
无需手动处理。

**Q: exe 双击无反应？** 首次启动可能较慢（单文件解压）；确认没有杀毒软件拦截；
如仍无反应，用命令行运行 `SANE扫描客户端.exe` 查看报错。

---

## 开源协议 / License

本项目基于 **GPL-3.0** 许可开源（LICENSE.txt），继承自 VB.NET 原版
SANEWinDS 的许可要求 / released under **GPL-3.0** (LICENSE.txt), inherited
from the VB.NET original SANEWinDS.

---

## 致谢 / Credits

- **FEEYEE**：项目发起人、需求方与全部测试验证 / initiator, requirements &
  full field testing
- **豆包（Doubao）**：协议逆向分析、重构实现与文档 / protocol analysis,
  rewrite implementation & docs
- 本项目由 FEEYEE 与豆包协作完成 / co-built by FEEYEE & Doubao
