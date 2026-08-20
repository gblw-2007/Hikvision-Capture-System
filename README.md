这里为您整理了完整版的 Markdown 格式开发文档。您可以直接点击代码块右上角的 **“复制”** 按钮，新建一个文本文档，将内容粘贴进去后，重命名为 `README.md` 即可。

```markdown
# 海康 7A47 系列结构化抓拍信息接收系统 - 开发者文档

> **当前版本：** V1.0 (田字排版与日志双向透传终极版)  
> **底层架构：** Python 3.9+ / PyQt5 / HCNetSDK (C++)  
> **核心定位：** 实时对接海康威视 IPC（如 7A47 系列）的底层内存回调，解析 `mixedTargetDetection`（混合目标检测）结构化报文，并提供工业级数据展示、自动存储配额管理及离线检索分析。

---

## 📂 1. 目录结构与说明

项目整体分为三大模块：**主代码（核心运行环境）**、**工具（协议测试与辅助脚本）**、**文档（原厂资料）**。

```text
海康7A47系列结构化抓拍信息接收/
├── 主代码/
│   ├── hik_engine.py          # 核心SDK引擎。通过 ctypes 封装海康 C++ SDK，负责登录、布防与底层内存回调
│   ├── pyqt.py                # 主程序 GUI 入口。基于 PyQt5 构建（包含渲染、缓存、日志拦截等核心业务）
│   ├── vehicleLogo.json       # 车辆标志映射配置。用于将报文中的车标 ID 转换为可读的车辆品牌
│   ├── hik_sdk/               # 海康 SDK 运行依赖库（非常重要，不可缺失）
│   │   ├── HCNetSDK.dll/.lib  # 海康网络通讯主 SDK 库
│   │   ├── HCCore.dll/.lib    # 海康核心算法库
│   │   ├── PlayCtrl.dll/.lib  # 播放控制解码库
│   │   ├── HCNetSDKCom/       # SDK 核心组件库文件夹（包含音频、预览、解析等多个底层 DLL）
│   │   ├── cameras.json       # 摄像机历史连接配置（记录 IP、端口、账号、密码的本地缓存）
│   │   └── ...                # 其他底层依赖动态库
│   └── ClientDemoDll/         # 原厂提供的客户端演示 DLL（供二次开发调试参考）
├── 工具/
│   ├── HTTP协议抓拍解析.py      # 工具脚本：通过 HTTP 监听接收并解析抓拍数据的测试器
│   ├── 海康HTTP分析中心.py      # 工具脚本：基于 HTTP 协议的简易分析主程序
│   ├── 海康SDK抓拍.py           # 工具脚本：SDK 抓拍基础功能的剥离测试脚本，用于快速验证设备连通性
│   └── ...
└── 文档/
    └── 设备管理平台SDK文档/      # 存放海康威视官方 SDK 接口说明（CHM/PDF）、错误码表及官方 Demo

```

---

## 🧠 2. 核心模块与技术特性 (`主代码/` 目录)

### 2.1 主控界面 (`pyqt.py`)

这是整个系统的中枢神经，承担了 UI 渲染、数据清洗、生命周期管理等任务。包含以下关键技术突破：

* **🖨️ 双向流捕获器 (`StreamCatcher`)**
* **机制：** 挂载在 `sys.stdout` 和 `sys.stderr`，底层强制对接 `sys.__stdout__` 和 `sys.__stderr__`。
* **作用：** 既能将 C++ SDK 的原生底层日志输出到真实的 CMD 黑框中（用于硬核排障），又能将日志无损转发到 UI 界面的“底层控制台”面板。彻底解决了 PyInstaller 无控制台打包 (`--noconsole`) 时引发的 `NoneType object has no attribute 'write'` 崩溃问题。


* **🎯 四大目标精准分流与特征继承算法**
* 深度解析海康 `mixedTargetDetection` 嵌套报文。
* **优先级链路：** `Face` (人脸) > `NonMotor` (非机动车) > `Vehicle` (机动车) > `Human` (普通人员)。
* **智能继承：** 当检测到“人脸”或“非机动车”时，算法会自动向下吸收 `Human` 节点中的“衣着、性别、背包”等特征，并执行智能去重。
* **海量字典映射：** 内置 `ATTR_TRANS` 字典，将海康底层英文代码（如 `prime`, `helmet`, `onePerson` 等二十余项特征）全面转换为结构化中文。


* **🖼️ 智能图片分配策略 (体积比对法)**
* 系统抛弃了不可靠的字符串命名匹配，改为通过 `os.path.getsize()` 遍历抓拍包中的物理图片大小。
* **防错逻辑：** 将体积最大的图始终定义为“场景全景大图”（左侧），体积最小的图定义为“目标特写图”（右侧），彻底杜绝全景与特写颠倒的 Bug。


* **📐 沉浸式非对称田字格布局 (`QSplitter`)**
* 实现了严格且视觉友好的四象限 UI：左上(人员 `2列`)、左下(车辆 `3列`)、右上(人脸 `1列`)、右下(非机动车 `1列`)。
* **焦点智控引擎：** 点击卡片进入详情页时，自动识别通道并隐藏无关象限，退出详情后瞬间还原黄金比例田字格。卡片高度根据标签数量动态自适应展开。


* **⚡ 瞬时计算与懒加载渲染**
* 采用后台瞬时内存级遍历（0.1秒内计算几万条数据以保证检索总数 100% 精确），结合前台 `QTimer` 定时队列渲染（每次取出 10~30 张卡片），确保极限海量数据下界面绝不卡死。


* **💾 无上限自动化配额守护 (`Quota Management`)**
* 解除常规限制，支持高达 `999,999 GB` 的超大监控阵列存储配额设定。
* 后台轮询线程监控归档目录，一旦越界，自动按照 `os.path.getmtime` 正序 FIFO（先进先出）清理最旧文件，实现无人值守挂机。



### 2.2 底层通信引擎 (`hik_engine.py`)

* **依赖：** 通过 Python `ctypes` 桥接海康 `HCNetSDK.dll`。
* **生命周期：** `NET_DVR_Init` -> `NET_DVR_Login_V40` -> `NET_DVR_SetupAlarmChan_V41`。
* **高并发内存回调：** 接收到底层二进制流后，通过指针偏移解包数据，分离出 JSON 和 Image 字节流，并迅速投递至 Python 的线程安全队列 `queue.Queue` 中，不阻塞 SDK 接收主线程。

---

## 🔄 3. 数据流转链路 (Data Pipeline)

1. **硬件触发：** 摄像机 AI 芯片识别到运动目标，推送 `COMM_VCA_ALARM` 等命令。
2. **SDK 回调：** `hik_engine.py` 触发 C 语言回调，获取 `pAlarmInfo` 内存指针。
3. **缓冲队列：** 组装 `{'timestamp': ..., 'raw_json': ..., 'images': ...}` 字典推入 `self.app_queue`。
4. **UI 轮询：** PyQt 主线程中 `100ms` 的定时器消费队列数据，发射 `capture_signal`。
5. **解析存储：** `_process_single_raw_capture` 解析报文，执行中文释义，并将数据持久化至本地 `LiveArchives` 和 `LiveCaptures`。
6. **无感重排：** 触发 `_refresh_grid_layout`，采用先解绑 (`removeWidget`) 后重载的安全队列渲染机制更新界面卡片。

---

## 🛠️ 4. 环境配置与开发指南

### 4.1 运行环境要求

* 操作系统：Windows 10 / 11 (64-bit) 或 Windows Server
* Python 环境：Python 3.8+ (强烈建议使用 Virtual Environment 隔离)

### 4.2 开发依赖安装

```bash
# 进入主代码目录
cd 海康7A47系列结构化抓拍信息接收/主代码

# 创建并激活虚拟环境 (无菌室打包规范)
python -m venv venv_pack
.\venv_pack\Scripts\activate

# 安装核心依赖
pip install PyQt5 psutil matplotlib pyinstaller

```

### 4.3 注意事项

* **SDK 路径：** 确保 `hik_sdk` 文件夹与 `pyqt.py` 及 `hik_engine.py` 处于**同级目录**，否则 `ctypes` 将触发 `[WinError 126]` 报错。
* **车标字典：** 务必保留 `vehicleLogo.json`，缺失将导致车辆品牌解析降级为原始数字 ID。

---

## 📦 5. 生产环境打包发布指南

为了保障底层 SDK 的高效寻址，并避免临时文件 (`AppData\Local\Temp`) 冗余导致的启动缓慢，本项目**严格禁止**使用 `--onefile` 单文件模式打包。

**请在虚拟环境的终端中，执行以下终极打包命令：**

```bash
pyinstaller --clean --noconsole --onedir --add-data "hik_sdk;hik_sdk" --add-data "vehicleLogo.json;." pyqt.py

```

### 交付说明

打包完成后，系统会在 `dist` 目录下生成 `pyqt` 文件夹。将该 `pyqt` 文件夹完整压缩后即可交付实施人员。用户只需双击内部的 `pyqt.exe` 即可完美运行，完全脱离 Python 环境。

```

```
