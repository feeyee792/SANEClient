# SANE 扫描客户端（安卓版 / uni-app x）

SANE 网络扫描客户端的 Android 移动端实现，由 Windows 版（`SANEWinDS` Python 重构版）的协议层移植而来。
**FEEYEE & 豆包 协作开发**。

通过局域网连接运行 `saned` 的服务器（如 Linux 主机 + USB 扫描仪），在手机上完成扫描、保存与管理。

- 协议层：SANE Net Protocol（TCP 6566 端口，含 `$MD5$` 认证）
- 技术栈：uni-app x（UTS 语言），无第三方依赖
- 图像：Android 原生 Bitmap / PdfDocument 编码（PNG / 多页 PDF）

---

## 环境要求

| 项 | 要求 |
|---|---|
| HBuilder X | 4.0+（uni-app x 支持），推荐 4.x / 5.x |
| 运行目标 | Android 手机或模拟器（API 24+） |
| 服务器 | 同一局域网内的 SANE 服务器（`saned`，端口 6566） |

## 如何运行

1. 用 **HBuilder X** 打开本目录（`SANEClientApp` 项目根）
2. 若提示选择项目类型，选择 **uni-app x**
3. 连接 Android 设备（开启 USB 调试）或启动模拟器
4. 菜单：运行 → 运行到手机或模拟器 → 运行到 Android App 基座
5. App 启动后，在「设置」页填写服务器地址（默认 `192.168.1.230:6566`），点「连接」

> 首次运行使用 HBuilder X 标准基座即可；发布正式包时在 HBuilder X 中「发行 → 原生App-云打包」生成 APK。

## 页面结构

| 页面 | 路径 | 说明 |
|---|---|---|
| 扫描 | `pages/index/index.uvue` | 预览区 + 模式/纸张/分辨率下拉 + 连续扫描 + 扫描按钮 + 进度 |
| 设置 | `pages/settings/settings.uvue` | 主机/端口/账号、设备选择、自动连接开关、命名模板 |
| 文件 | `pages/files/files.uvue` | 扫描结果列表（PNG 缩略图 / PDF 标识）、预览 |

底部 TabBar：扫描 / 设置 / 文件（配色与 Windows 版品牌一致：青绿 `#0FA3A3` + 浅米白背景）。

## 目录结构

```
SANEClientApp/
├── App.uvue                 # 应用生命周期
├── main.uts                 # 入口
├── manifest.json            # 应用配置（Android 权限等）
├── pages.json               # 页面路由 + tabBar
├── uni.scss                 # 品牌色变量
├── common/sane/             # 协议层（UTS）
│   ├── constants.uts        # SANE 常量/枚举（← constants.py）
│   ├── models.uts           # 数据结构（← models.py）
│   ├── wire.uts             # WireWriter/WireReader 序列化（← protocol.py）
│   ├── client.uts           # RPC 客户端 + 帧采集（← client.py）
│   ├── imageutil.uts        # 帧 → Bitmap/PNG/PDF（← images.py 语义）
│   ├── fileutil.uts         # 保存目录/文件列表/命名模板
│   ├── threadutil.uts       # 子线程 IO + 主线程回调
│   └── store.uts            # 全局状态 + 扫描流程编排
└── pages/                   # 三个页面（.uvue）
```

## 使用说明

- **连接**：设置页填主机/端口（可选用户名密码），点「连接」；「启动时自动连接」开启后，App 启动自动连接并打开上次使用的设备
- **扫描**：选择模式（彩色/灰度等）、纸张（A4/Letter 等）、分辨率（下拉列表由**设备真实选项**生成），点底部扫描按钮
- **连续扫描**：打开「连续扫描 (PDF)」开关，扫描多页后自动生成 PDF 文件
- **命名规则**：设置页可改模板，支持占位符 `{date} {time} {mode} {resolution} {page}`，默认 `{date}_{time}`
- **文件**：扫描结果保存在应用私有目录 `files/sane_scans/`，文件页可预览 PNG / 识别 PDF

## 与 Windows 版的差异

- UI 针对手机重做（单页 + 底部大按钮 + TabBar），不复用桌面两列布局
- 图像编码从「纯 Python 手写 BMP/PNG/PDF」改为 **Android 原生 Bitmap / PdfDocument**
- 配置持久化从 INI 文件改为 `uni.setStorageSync`（本地存储）
- 协议层逻辑（RPC 封包、字节序、帧采集、`$MD5$` 认证）**与 Windows 版一致**，逐行移植

## 测试设备

- 开发验证设备：**EPSON L3118**（服务器为实体 SANE 主机 `192.168.1.230:6566`）
- 常见后端差异：
  - `epsonscan2:` 后端：mode 为 `Color/Grayscale/Monochrome`，分辨率 RANGE（50~1200），支持 `scan-area`（A4/Letter…）
  - `epson2:` 后端：mode 为 `Lineart/Gray/Color`，分辨率 WORD_LIST（75/150/300/600，无 200），无 `scan-area`（用 `br-x/br-y` 毫米坐标）
  - 程序会按设备真实选项自动生成下拉列表；若某设备缺 `scan-area`，会自动回退到 `br-x/br-y` 坐标方案
- 扫描仪同一时刻只能被一个程序占用；若选项报 INVAL 或连接被中止，先确认没有其它程序（含 Windows 版客户端）占用设备

## 已知事项（编译验证）

本代码由 Python 版协议层逐行移植，**尚未在 HBuilder X 中实际编译运行**。若编译报错，请将错误信息反馈给作者，主要关注点：

1. UTS 对 `java.net.Socket` / `android.graphics` 等原生 import 的兼容性
2. `TextEncoder/TextDecoder` 在 uni-app x 的可用性（不可用时可改用 `UTSAndroid` + `StandardCharsets`）
3. `image` 组件直接显示应用私有目录绝对路径的行为（若空白，需改为读取文件转 base64 后显示）
4. `progress` / `picker` / `switch` 组件在 uni-app x 中的属性兼容性

## 许可证

GPL-3.0
