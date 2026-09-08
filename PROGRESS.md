# 开发进度记录（2026-09-08）

## 第十七轮：分享/打印/导出 + 文件页长列表优化（9-08 晚 19:30）

**新增文件 `common/sane/share.uts`**（系统分享/打印/导出，UTSAndroid + Intent + FileProvider + MediaStore）：
- **分享**：`UTSAndroid.convert2AbsFullPath(unifile路径)` 转真实路径 → `UTSAndroid.getFileProviderUri(file)` 转 content:// Uri → `Intent.ACTION_SEND` + `EXTRA_STREAM` + `FLAG_GRANT_READ_URI_PERMISSION` + `startActivity(createChooser)`
- **打印**：`androidx.print.PrintHelper` 在 5.24 编译环境不存在，降级为 `ACTION_VIEW` + `image/png` 调系统图片查看器，Toast 提示"在查看器菜单里选打印"；PDF 点打印提示先系统打开
- **导出**：Android 10+（SDK≥29）走 MediaStore（PNG→Pictures/sane_scans，PDF→Documents/sane_scans）；Android 9- 直接写 `Environment.getExternalStoragePublicDirectory`。manifest 加 `WRITE_EXTERNAL_STORAGE`
- 坑：UTS import 是**包名**（`import { Intent } from 'android.content'`），类名放花括号，不是 `'android.content.Intent'`

**文件页长列表优化**：
- 新文件 `common/sane/filegroup.uts`：按文件名前 8 位日期（`20260908`）分组 + 关键词本地过滤，输出扁平 `FlatFileItem` 数组（分组头 + 文件项交替）。字段拍平为非空 string（fileName/filePath/fileSizeText/isPdf），避开 UTS 模板里嵌套 nullable 的 smart cast 坑
- 引入官方 **uni-recycle-view** 回收长列表组件（复制到 `uni_modules/`），固定 itemHeight=90px，只渲染屏幕可见 item，成千上万文件不卡。分组头和文件项统一高度
- **分组可折叠**：点分组头 toggle，展开 ▼ / 折叠 ▶，折叠状态存 `collapsed: Array<string>`
- 顶部搜索框 v-model + watch，边打边过滤文件名
- 坑：`filtered.length` 是 Number，push 到 Int 数组要 `.toInt()`；template 不能直接用 import 的 store，改成 data 里的 fileCount；slot 断言要 import 组件自带的 `LayoutItem` 类型

## 第十六轮：文件存储改 uni-app x 官方文件系统（9-08 下午 15:49）

**进度条不走的根因（对照 Python 版确认）**：Python `int((transferred / expected_total) * 100)` 是浮点除法；UTS 版 `transferred / expectedTotal` 在 Kotlin 里是**整数除法**，恒为 0 → 进度永远不触发。改 `(transferred * 100 / expectedTotal).toInt()`（6.5M×100 不溢出，语义与 Python 一致）。

**加诊断日志**：overran 实际字节/段数、frame done 数据长度、rendering bitmap、bitmap ok、png saved、页面 catch 完整异常——用于精确定位失败环节。

## 第十六轮：文件存储改 uni-app x 官方文件系统（9-08 下午 15:49）

**真机日志证据**：`java.io.FileNotFoundException: /unifile:/usr/sane_scans/xxx.png: open failed: ENOENT`——`uni.env.USER_DATA_PATH` 返回 **unifile:// 协议路径**，Java `FileOutputStream`/`File` 打不开。且数据传输已验证 100% 完整（transferred=6524880=expected）、Bitmap 渲染成功（1240x1754），失败点唯一且明确。

**修复（API 全部查证自 HBuilderX 官方类型定义 `...\types\uni\uts-plugin-api\lib\uni-fileSystemManager\`）**：
- imageutil.uts：写 PNG/PDF 改 `ByteArrayOutputStream → android.util.Base64.encodeToString(NO_WRAP) → fs.writeFileSync(path, b64, 'base64')`
- fileutil.uts：`getScansDir()` 改 unifile 拼接 + `accessSync` 检查 + `mkdirSync(dir, true)`；`listScanFiles()` 改 `readdirSync` + `statSync`（size/lastModifiedTime）
- 删 `import { File } from 'java.io'`

## 第十四轮：switch 事件类型名（9-08 下午 15:24）

`UniChangeEvent` 不存在（编译报"找不到名称"）——从 HBuilderX 内置类型定义查证（`plugins/.../types/vue/SwitchChangeEvent.d.ts`）：switch 的 change 事件类型是 **`UniSwitchChangeEvent`**（`detail.value: boolean`）。onMultiChange / onAutoChange 两处已改。

> 已从类型定义文件确认：picker=UniPickerChangeEvent、switch=UniSwitchChangeEvent。今后事件参数一律先查 `HBuilderX\plugins\hbuilderx-ai-chat\uni-agent\knowledges\uni-app-x\types\uni-app-x\types\vue\` 下的 d.ts，不再猜名字。

## 第十三轮：真机运行修复（9-08 下午 15:19，首次真机启动）

**里程碑：编译通过 + 协议层真机全链路跑通**（日志证实）：
- 连接 192.168.1.230:6566 成功（client 1.0.3 ↔ server 1.1.3）
- 打开设备 `epson2:libusb:002:007` 成功（handle=0, status=0）
- START 成功（data port=39211, byte order=0x1234）
- 图像传输开始：format=1(GRAY) lines=1754 bpl=3720 ppl=1240 depth=8 last=true（A4@150dpi，bpl 含 padding）
- 注意：`server overran expected byte count without EOF; aborting`——transferred 达到 expectedTotal 时 break，数据应完整（与 Python 版行为一致）

| 类型 | 位置 | 修复 |
|---|---|---|
| 启动 IndexOutOfBoundsException（modeList[0] 空数组） | index.uvue 模板 | data 给默认列表（Color/Grayscale、A4/Letter、75-600）+ 模板三元保护 |
| `argument 1 has type UTSJSONObject, got UniPickerChangeEvent`——picker change 事件参数类型必须用框架类型 | index.uvue / settings.uvue | onModeChange/onPaperChange/onResChange/onDeviceChange → `UniPickerChangeEvent` + `e.detail.value as number`；onMultiChange/onAutoChange（switch）→ `UniChangeEvent` + `e.detail.value` |
| `font-size/color/font-weight only supported on <text>` | settings.uvue | 3 个 `.section-title` 从 `<view>` 改 `<text>` |
| progress `stroke-width="4"` 传字符串 → ClassCastException | index.uvue | `:stroke-width="4"` 数值绑定 |

> 关键经验：**uni-app x 的事件参数必须用框架内置类型**（picker=UniPickerChangeEvent、switch=UniChangeEvent），声明为 UTSJSONObject/any 会在运行时强转失败。

## 第十二轮编译修复（9-08 下午 15:06，HBuilder X 5.24）—— 全量类别审查

| 类型 | 位置 | 修复 |
|---|---|---|
| `Promise.reject<string>(...)` 报"No type arguments expected for fun reject(value: Any?): UTSPromise\<Unit\>"——UTS 的 reject 不接受泛型且固定返回 Unit | store.uts doScan | 改同步 `throw new Error('扫描进行中')`（doScan 只在页面 onScan 的 try-catch 内被调用，同步 throw 可被捕获） |
| `msg = e.message` 报"actual String?, expected String"——catch 参数 e 的 message 属性判空后仍不可收窄 | index.uvue / settings.uvue | catch 内取 `const m: string \| null = e.message` 局部变量再判空 |
| `.catch((err: any) => ...)` 报"No candidates applicable"——UTS 的 catch 回调签名是 `(Any?) -> R`，`any` 不匹配 | settings.uvue | `(err: any \| null)` + 内部 `(err as Error).message` 取信息 |
| 预防：catch 里 `throw e`（e 是 any，UTS 要求 Error） | client.uts scanAllFrames | `throw e as Error`（673 行的 throw e 在 instanceof 收窄后，合法保留） |

> **本轮对全部 8 个 UTS 模块 + 3 个页面逐文件通读**，按 12 类已知 UTS 坑（any 属性访问/可空链/数组规则/类型化数组/可选参数/Promise/reject/事件对象/Date/枚举/override/throw）全量排查，非被动等编译报错。最终复查：Promise.reject、.catch((err: any)、msg = e.message、throw e（非收窄）、as any、e.detail、Array<number | null> 全部清零。

## 第十一轮编译修复（9-08 下午 14:33，HBuilder X 5.24）

| 类型 | 位置 | 修复 |
|---|---|---|
| `c.setOption(idx, [mode])` 报"实际 UTSArray\<String\>，预期 UTSArray\<Number?\>"——选项值含字符串（mode/paper） | models.uts + client.uts + store.uts | `SANEControlOptionRequest.values` / `setOption` 参数 / `controlOption` 局部类型统一为 `Array<number \| string \| null>`；BOOL 分支 `v != 0` 改 `(v as number) != 0` |
| `return Promise.reject(...)` 报"expected UTSPromise\<String\>, actual UTSPromise\<Unit\>"——reject 类型推断丢失 | store.uts doScan | `Promise.reject<string>(...)` 显式泛型 |
| `e.detail.value` 报"找不到名称 detail"——UTS 5.24 的 `any` 不支持点属性访问（含页面事件对象） | index.uvue ×4、settings.uvue ×2 | 事件参数改 `UTSJSONObject`，`(e["detail"] as UTSJSONObject)["value"] as number/boolean` |

> 关键经验：**UTS 5.24 的 any 不能点属性访问**——JSON 用 UTSJSONObject 索引、页面事件对象也用 UTSJSONObject 索引取 detail。这是 store.uts `obj.host` 同源问题的延伸。

## 第十轮编译修复（9-08 下午 14:01，HBuilder X 5.24）

| 类型 | 位置 | 修复 |
|---|---|---|
| `c.init()` 报"No value passed for parameter 'username'"——UTS 5.24 不支持 `?` 可选参数的省略调用 | client.uts | `init(username?: string)` → `init(username: string = '')`，内部判空改判 `== ''` |
| `r.quant` 报"Only safe (?.) calls allowed on SANERange?"——`d.constraint.range != null` 检查对嵌套属性链不生效 | store.uts | 局部变量 + 独立判空块 |

> 同类排查：全项目 `?` 可选参数、可空链解引用均已清零（common + pages）。

## 第九轮编译修复（9-08 下午 13:40，HBuilder X 5.24）

| 类型 | 位置 | 修复 |
|---|---|---|
| `setPixels` 报"实际 Int32Array，预期 IntArray"——UTS 的 Int32Array 不映射 Kotlin IntArray | imageutil.uts | 改用 `new IntArray(...)`（与已验证的 `new ByteArray` 同族，UTS 原生数组构造） |
| `obj.host` 报"找不到名称 host"——UTS 5.24 下 `as any` + 点属性访问不可用 | store.uts loadConfig | 改用 `json as UTSJSONObject` + `obj["host"]` 索引访问 |

> 全项目 `as any` 已清零；JSON 使用点仅 store.uts 3 处已全部覆盖。

## 第八轮编译修复（9-08 上午 11:36，HBuilder X 5.24）

| 类型 | 位置 | 修复 |
|---|---|---|
| `bmp.setPixels(pixels, ...)` 报"实际 UTSArray\<Int\>，预期 IntArray"——UTS 的 Array\<Int\> 是装箱 UTSArray | imageutil.uts | `pixels` 改为 `new Int32Array(...)`（映射 Kotlin IntArray，元素赋值 Int 合法） |
| `canvas.drawBitmap(bmp, 0.0, 0.0, null)` 报候选不适用——字面量 0.0 是 Double，需要 Float | imageutil.uts | `0.0.toFloat()` |
| `children.length` 找不到——`dir.listFiles()` 返回 Kotlin 原生数组（用 .size） | fileutil.uts | `.length` → `.size` |
| `pad2(d.getMonth() + 1)` 报"实际 Number，预期 Int"——JS Date API 返回 number | fileutil.uts | Date 全部补 `.toInt()`（getMonth 特殊括号处理） |

> 经验：UTS 数组规则 = UTSArray（自己创建的 Array\<T\>）用 `.length`；Java/Kotlin 原生数组（ByteArray、File[]）用 `.size`；类型化数组 Int32Array ↔ Kotlin IntArray。

## 第七轮编译修复（9-08 上午 11:32，HBuilder X 5.24）

| 类型 | 位置 | 修复 |
|---|---|---|
| `reply.values.push(s)` 报"实际 String，预期 Number?"——ControlOption 回复的字符串值无处安放 | models.uts | `SANEControlOptionReply.values` 类型改为 `Array<number \| string \| null>`（发送端 request.values 保持 Array<number\|null> 不变） |
| acquireFrame 里 `this.controlSocket.getInetAddress()` Smart cast 失败 | client.uts | 局部变量 `const sock` |
| `const msg: string = e.message`——any.message 是 String? | client.uts | 判空后再赋值 |
| `run()` hides member of supertype 'Runnable' | threadutil.uts | 加 `override` |
| **预防性**：request / controlOption / readControlOptionReply / readReplyValues 里的 `this.reader` 解引用（编译每次递进暴露更多 smart cast） | client.uts | 全部改局部变量 `const r` |

## 第六轮编译修复（9-08 上午 11:18，HBuilder X 5.24）

| 类型 | 位置 | 修复 |
|---|---|---|
| `throw new SaneError(...)` 报"推断类型是 SaneError，预期 Throwable"——**UTS 中 throw 的对象必须是 Error 子类** | client.uts | SaneError / EmptyFrameException / ServerDisconnectedException 全部 `extends Error`，消息经 `super(message)` 传入 |
| `this.controlSocket.close()` 报 Smart cast impossible（disconnect 函数内给属性赋 null 导致） | client.uts | 改局部变量 `const sock = this.controlSocket` |

> 全局核验：所有 `throw new` 目标均为 Error 子类；其余 mutable 属性解引用均无同函数赋值，安全。

## 第五轮编译修复（9-08 上午 11:07，HBuilder X 5.24）

重新编译后剩余 2 处报错 + 顺带预防性排查，已一次性处理：

| 类型 | 位置 | 修复 |
|---|---|---|
| `Uint8Array` 元素赋值不接受 UByte（`out[i] = buf[i].toUByte()` 报 `set(index: Number, element: Number)` 不适用） | wire.uts readExact | 改 `out[i] = buf[i].toInt() & 0xFF`（Int 是 Number 子类） |
| **UTS 不支持数组内元组类型标注**（`Array<[number \| string \| boolean, Int]>` → Syntax error） | client.uts request | 新增 `SaneRpcItem` 类（data + dataType），8 处调用点全部替换 |
| 函数返回元组未验证（`start(): [Int, Int]`、`findOption(): [Int, ...]`） | client.uts + store.uts | 预防性改为 `SaneStartResult` / `SaneFindResult` 类返回 |
| AI 修复遗留的缩进错乱 | client.uts getOptionDescriptors | 已整理为规范缩进 |

> 全局终检扫描确认：元组标注、`Array<[`、可选链 `?.`、空合并 `??`、UByte 赋值已全部清零。

## 第四轮编译修复（9-08 上午，HBuilder X 5.24 / uni-app x VDOM 模式）

5.24 编译器下 kotlin 编译失败 3 处，且日志里出现了**非我编写的代码**（`Array<any>`、`const idx = i as number`、`new ByteArray`、`toUByte()`）——判定为 HBuilder X 的 **[AI修复] 按钮自动改动了源码且改坏**。本轮已全部人工修复：

| 类型 | 位置 | 修复 |
|---|---|---|
| enum 不能传给 Int 参数（`writeWord(rpc)` 报"实际类型 SANENetProcedureNumber，预期 Int"） | constants.uts + wire/client/models/imageutil/store | **所有 enum 全部改为 const Int 常量**（SANE_NET_* / SANE_STATUS_* / SANE_TYPE_* / SANE_CONSTRAINT_* / SANE_FRAME_* / SANE_Word 等），引用点批量替换 |
| [AI修复] 把 readExact 改成 `new ByteArray(n)` + `out[i as number] = buf[i].toUByte()`（Number 索引报错） | wire.uts | 保留 ByteArray 中转（Java InputStream.read 需要 byte[]），索引用 Int 修正 |
| [AI修复] 把 request 改成 `Array<any>` + `const idx = i as number`（String.get 索引报错） | client.uts | 还原为 `Array<[number \| string \| boolean, Int]>`，`items[i][0]` 直接索引 |
| [AI修复] md5Hex 残留 `d.size` / `Byte` 类型 | client.uts | 重写为 ByteArray 中转 + `.toInt()` 版本 |
| `toBytes()` 返回 Uint8Array 不能传给 `OutputStream.write(byte[])` | wire.uts | 改为返回 ByteArray（`.toByte()` 逐元素转换） |
| `optionValueArrayLength` 的 `let vt: Int` try/catch 未初始化风险 | wire.uts | 简化：直接比较 optionType |
| 顶层 const 用函数初始化（VERSION_CODE） | constants.uts | 改为字面量 16777219（saneVersionCode(1,0,3)） |

> 结论：**不要再点 HBuilder X 的 [AI修复] 按钮**，把报错贴给豆包人工修，否则源码会被改坏且难以追踪。

## 第三轮编译修复（9-08 上午，5.07）

`UTSAndroid` 报错定位到 HBuilderX 内部 findUnauthorized.js 被改坏；真实代码错误 2 处已修（`charCodeAt(0)` 可空 & 运算、`stream: any` 类型化 InputStream）；fileutil.uts 移除 UTSAndroid 改用 `uni.env.USER_DATA_PATH`；client.uts `getInetAddress()` null 兜底。

## 第二轮编译修复（9-08 上午，UTS 层）

HBuilder X 5.07 第二轮编译报错，已全部修复：

| 类型 | 位置 | 修复 |
|---|---|---|
| `toString` 需 `override` 修饰 | models.uts | 加 `override` |
| Int/Number 类型不匹配（`.length`、除法、`parseInt`、`indexOf`、`Math.max`、循环变量赋 Int 字段） | wire.uts / client.uts / imageutil.uts / store.uts / settings.uvue / index.uvue / fileutil.uts | 全部补 `.toInt()`；for 索引赋值转 Int |
| `this.client` 属性 null 收窄不可靠 | store.uts | 全部改局部变量 `const c = this.client` |
| 进度回调参数类型不符 | index.uvue | `(p: number)` → `(p: Int)` |
| Java `long` 与 number | fileutil.uts | `timeStamp` 改 `Long`、`f.length().toNumber()` |
| `UTSAndroid` 找不到（报在 HBuilderX 内部 uni-console 插件文件） | — | **待观察**：可能是上述错误导致的级联报错，重编译确认；若仍在则需查 HBuilderX/插件版本 |

> 上一轮（9-08 凌晨）已修 7 处 CSS 兼容问题（page 选择器 / 100vh / [disabled] / :last-child / word-break）。

## 项目状态

**SANE 扫描客户端（安卓版 / uni-app x）** 一期代码已完成：
- 位置：`D:\开发\SANEClientApp\`
- 协议层（UTS，从 Windows 版 Python 逐行移植）：`common/sane/`（constants / models / wire / client / imageutil / fileutil / threadutil / store）
- 三个页面：扫描页 `pages/index`、设置页 `pages/settings`、文件页 `pages/files`
- 配置：manifest.json / pages.json / uni.scss（品牌色青绿 #0FA3A3）
- 说明文档：README.md（含环境要求、运行步骤、已知事项）

## 已完成功能

- SANE Net 协议全部 RPC：Init / GetDevices / Open / Close / Cancel / GetOptionDescriptors / ControlOption / GetParameters / Start / Authorize($MD5$) / Exit
- 图像帧采集（含空帧/超时/异常长度处理，进度回调）
- 帧 → Bitmap → PNG / 多页 PDF（Android 原生编码，零第三方依赖）
- 扫描页：预览 + 模式/纸张/分辨率下拉（按设备真实约束生成）+ 连续扫描开关 + 进度条 + 底部大按钮
- 设置页：主机/端口/账号/设备选择/自动连接开关/命名模板
- 文件页：扫描结果列表（PNG 缩略图 / PDF 标识）+ 预览弹层
- 配置持久化（uni.setStorageSync），启动自动连接上次设备
- 设备后端适配：`epsonscan2:`（scan-area + RANGE 分辨率）与 `epson2:`（br-x/br-y 毫米坐标 + WORD_LIST 分辨率）自动回退

## 明天待办（按顺序）

1. **重新编译**：HBuilder X 打开 `D:\开发\SANEClientApp` → 运行到 Android 基座，把新报错贴给豆包
2. **预期 UTS 层报错点**（很可能会遇到，提前心里有数）：
   - `UTSAndroid` 报错是否消失（若仍在 → 查 HBuilderX 版本/uni-console 插件）
   - `TextEncoder / TextDecoder` 是否可用（不可用 → 换 `UTSAndroid` + `StandardCharsets`）
   - enum 与 Int 混用（writeWord(枚举)）是否报错（报 → 改 const 数字常量）
   - `image` 组件直接显示应用私有目录图片是否可行（不行 → FileSystemManager 转 base64）
3. **编译通过后真机验证**（连实体 SANE 服务器 192.168.1.230:6566）：
   - 设置页连接 → 设备枚举 → 扫描页选项下拉是否按设备生成
   - 扫描一页 PNG → 连续扫描 PDF → 文件页查看
4. 顺手事项：tabBar 图标（当前纯文字）、扫描结果存相册（MediaStore）、PDF 分享打开

## 路线图（待实现功能，下一版）

~~系统分享 / 系统打印 / 一键导出~~ **已完成（第十七轮）**——见 `common/sane/share.uts` 与文件页预览弹层三个按钮。

下一版可考虑：PDF 多页打印（PrintHelper 只支持 Bitmap，PDF 需 PdfRenderer 逐页渲染）、分组折叠状态持久化。

## 注意事项

- `.hbuilderx/` 和 `unpackage/` 目录是 HBuilder X 生成的，**不要动**
- 扫描仪同一时刻单程序占用，验证时先确认没有其它程序占用
- 测试设备：EPSON L3118（`epsonscan2:` 与 `epson2:` 双后端差异已适配）
