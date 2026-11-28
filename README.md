# Android Agent Workstation

**在免 Root、免电脑的 Android 手机上搭建本地 AI Agent 开发与真机调试环境的方案与工具包。**

> Practical guide and toolkit for running CLI AI agents (`agy`, Claude Code, Codex) and on-device Android verification on an unrooted phone via Custom Termux, isolated PRoot Debian, loopback wireless ADB, and Gradle-free APK tooling.

---

## 为什么做这套方案？

在手机上直接运行 CLI AI Agent（如 Antigravity CLI `agy`、Claude Code、Codex）并完成实际开发，通常会遇到四个主要问题：

1. **官方 Termux 跑现代 TUI 体验不佳**：跨读块刷新闪烁、弹收软键盘触发 `SIGWINCH` 导致满屏重排、流式输出时无法停留在回滚区阅读、折行 URL 点不开、鼠标捕获模式下点击链接误透传、左侧抽屉只显示 `proot` 看不出内部命令、Nerd Font 与状态符号缺字。
2. **原生 Termux（Bionic）与主流 Linux ARM64 工具链存在兼容差异**：大量 CLI Agent、浏览器引擎与构建工具依赖标准 glibc Linux 环境，同时又需要隔离容器以防误触手机个人文件。
3. **手机端没有 Android Emulator，Agent 写完 App 难以验证实际运行效果**：Paparazzi / Roborazzi 依赖的 LayoutLib 缺少官方 `linux-arm64` 构建，Shizuku `rish` 也无法直接在 glibc PRoot 内运行。
4. **换机、重装或从 Google Play 版 Termux 迁移容易出问题**：直接备份恢复 `$PREFIX` 会破坏 Play 版软链，普通打包会破坏 PRoot 的 `.l2s` 硬链接映射与 Agent 会话 SQLite WAL 状态。

本仓库整理了一套经过实测的流程、配置模板与脚本工具，依次解决上述问题。

---

## 整体架构

```text
┌────────────────────────────────────────────────────────────────────────────┐
│  Android 11–16 宿主机真机（免 Root、免电脑）                                │
│  ├─ 无线调试配对 + adb tcpip 5555 固定端口（激活后脱离 Wi-Fi 也可维持）     │
│  └─ 被测 Android App / 系统 UI（静默装包 / 截屏 / UI 树 / 注入 / Logcat）   │
└───────────────────────────────────▲────────────────────────────────────────┘
                                    │ 127.0.0.1:5555（本机无线调试回环）
┌───────────────────────────────────┴────────────────────────────────────────┐
│  Layer 1：Custom Termux（v0.118.3+custom，11 单面向 Agent TUI 增强）        │
│  ├─ DECSET 2026 同步输出 / 文档行锚定与亚像素滚动 / 主屏免 SIGWINCH 平移    │
│  ├─ Warm Paper 日夜自适应主题 + Mode 2031 / 四层原生字体与 Nerd Font 回退   │
│  ├─ 侧栏穿透 PRoot 显示真实命令 + OSC 标题优先 / OSC 8 与多行 URL 点击直跳  │
│  ├─ 原生 ARM64 android-tools（ADB Server @ 127.0.0.1:5037）                 │
│  ├─ 可选受限 HTTP 桥（adb_bridge.py：包名白名单 + Token + 前台焦点守卫）    │
│  └─ 通用 PRoot 启动器 + 零损耗整机备份/恢复脚本                             │
└───────────────────────────────────▲────────────────────────────────────────┘
                                    │ 127.0.0.1 TCP（PRoot 用户态共享环回网）
┌───────────────────────────────────┴────────────────────────────────────────┐
│  Layer 2：PRoot Debian 13 (Trixie) ARM64 容器（--isolated 环境隔离）        │
│  ├─ 统一时区与 UTF-8 Locale + 触屏 1:1 逐行滚动 tmux                        │
│  ├─ 多 Agent 栈：agy（statusline + title 侧栏联动）/ Claude Code（支持      │
│  │  Ollama Cloud 与 OpenRouter 网关）/ Codex / OpenCode                     │
│  └─ 工程闭环工具：                                                          │
│     · /usr/bin/adb（协议 1.0.41，复用外层 5037）或 curl 调受限 HTTP 桥      │
│     · chromium-headless-shell --use-gl=disabled（无 GPU 软渲染 UI 预检）    │
│     · ECJ + aapt2 + D8 + zipalign + apksigner（零 Gradle 离线编译签名 APK） │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 核心组件与特性速览

### 1. Custom Termux（面向 AI Agent 的终端底层优化）

基于上游 `termux/termux-app` `v0.118.3`，共 11 单分层改造（前 4 单已提交上游 PR，后 7 单为本地增强，完整源码托管于 [`qwerty123yucy/termux-app` (`custom` 分支)](https://github.com/qwerty123yucy/termux-app/tree/custom)，预编译签名版 APK 见本仓库 **Releases**）：

| 能力 | 解决的问题 |
| :--- | :--- |
| **DECSET 2026 同步输出**（`#5441`） | 消除 `agy` / `claude` / `tmux` / `neovim` 刷屏闪烁撕裂 |
| **非 IME 布局底边距抖动修复**（`#5442`） | 开关侧栏或扩展键栏不再误触发双重 `SIGWINCH` |
| **文档绝对行锚定 + `OverScroller` 亚像素滚动**（`#5443`） | 流式输出时上滑回看自动锁定位置，滑回底端自动恢复跟随 |
| **软键盘主屏平移免缩放**（`#5444`） | 主屏弹收输入法仅平移视口不发 `SIGWINCH` 重排；备用屏（`vim`/`tmux`）保持标准缩放 |
| **双排扩展键 + `SCROLL` 锁键 + 返回手势抽屉** | 提供 `SCROLL` 滚动锁定键、返回手势开关会话抽屉、64 KiB Session IO 缓冲、Android 16 16 KB ELF 对齐 |
| **Warm Paper 日/夜原地自适应主题 + Mode 2031** | `onConfigurationChanged` 不重建 Activity 原地切深浅色、抽屉三态切换键、克制型 WCAG 对比度兜底 |
| **侧栏实时命令穿透容器 + OSC 标题优先** | 穿透 `proot` / `vroot` 识别 `debian · agy` / `debian · claude`，OSC 动态标题占主行、真实命令留副行，抽屉关闭零轮询 |
| **OSC 8 超链接 + 布局感知多行 URL 提取** | 自动拼接卡片/引用栏内折行长链接、柔和极细下划线、鼠标捕获模式防透传、`file://` 点击复制路径 |
| **四层原生有序字体回退链（API 29+）** | JetBrains Mono NL 四字重 → Symbols Nerd Font Mono → Noto Sans Symbols 2（不劫持彩色 Emoji）→ 系统 `monospace` |

### 2. 工具包与配置模板目录

| 目录 | 内容说明 |
| :--- | :--- |
| [`docs/`](docs/) | 7 篇分章详细教程（架构原理 → Custom Termux → PRoot & Agent → 宿主机 ADB → 离线闭环开发 → 迁移备份 → 排障速查） |
| [`scripts/host-termux/`](scripts/host-termux/) | 原生 Termux 侧脚本：`setup-host-termux.sh`、`proot-debian.sh`、`adb-connect.sh`、`adb_bridge.py`、`backup.sh`、`restore.sh` |
| [`scripts/proot/`](scripts/proot/) | PRoot 容器内脚本：`bootstrap-debian.sh`、`adb-check.py`、`headless-ui-check.mjs` |
| [`scripts/termux-offline-build/`](scripts/termux-offline-build/) | 手机端免 Gradle 15 秒重编译 Custom Termux 的 `build_fast_apk.py` 与 `run_tests.py`（环境变量参数化） |
| [`configs/`](configs/) | `termux.properties`、`tmux.conf`、`agy` 状态栏/动态标题、`claude` 第三方网关模板、Agent 规则与可复用 Skills |
| [`termux-custom/`](termux-custom/) | Custom Termux 源码对应说明、Gradle / 离线构建指南、签名模板与 GPLv3 开源合规声明 |

---

## 快速开始

1. **安装 Custom Termux**
   - 从本仓库 [Releases](https://github.com/qwerty123yucy/android-agent-workstation/releases) 下载最新签名版 `termux-app_v0.118.3+custom.36106fb_arm64-v8a.apk`（支持 Android 16 / 16 KB 页对齐），或按 [`termux-custom/README.md`](termux-custom/README.md) 自行从源码编译。
   - 打开手机 **开发者选项**，开启 **停用子进程限制**（Android 12+）并将 Termux 设为不受电池优化限制。

2. **初始化外层 Termux 与 PRoot Debian (`--isolated`)**
   ```bash
   # 在原生 Termux 执行（务必先完整升级再装包，避免 libc++ 符号缺失）
   pkg update && pkg upgrade -y
   pkg install -y git proot-distro tmux zstd android-tools python aapt2

   git clone https://github.com/qwerty123yucy/android-agent-workstation.git ~/workstation
   cp ~/workstation/configs/termux/termux.properties ~/.termux/termux.properties
   termux-reload-settings

   # 安装 Debian 并部署通用隔离启动器（默认 UTC，可通过 CONTAINER_TZ 自定义时区）
   proot-distro install debian
   install -m 700 ~/workstation/scripts/host-termux/proot-debian.sh "$PREFIX/bin/proot-debian"
   ```

3. **进入 PRoot 容器并初始化基础环境与 Agent**
   ```bash
   proot-debian
   # 容器内克隆工具包并初始化基础依赖（可选加 --with-headless 安装 Chromium 软渲染）
   git clone https://github.com/qwerty123yucy/android-agent-workstation.git ~/workstation
   bash ~/workstation/scripts/proot/bootstrap-debian.sh
   cp ~/workstation/configs/tmux/tmux.conf ~/.tmux.conf
   ```
   随后按 [`docs/03-proot-and-agents.md`](docs/03-proot-and-agents.md) 安装并配置 `agy`（挂载 `statusline.py` + `title.py`）和/或 Claude Code（含 Ollama Cloud / OpenRouter 网关配置）。

4. **打通宿主机无线 ADB 回环（免 Root、免电脑）**
   - 手机开启 **USB 调试**、**无线调试**（ColorOS 另开 **禁止权限监控**，MIUI/HyperOS 另开 **USB 调试（安全设置）**）。
   - 在**原生 Termux** 执行分屏配对与 `5555` 端口固定：
     ```bash
     bash ~/workstation/scripts/host-termux/adb-connect.sh
     ```
   - 根据隔离需求二选一接入 PRoot：
     - **强隔离（路线 A）**：在原生 Termux 运行 `~/workstation/scripts/host-termux/adb_bridge.py`，容器内只用 `curl` 操作白名单包名；
     - **直连开发（路线 B）**：容器内直接用 `adb -s 127.0.0.1:5555` 透明复用外层 `127.0.0.1:5037` Server，并用 `python3 ~/workstation/scripts/proot/adb-check.py` 校验通道。

---

## 详细教程目录

- [01. 整体架构与设计取舍](docs/01-architecture.md)
- [02. Custom Termux：11 项底层增强、配置、构建与 Play 版迁移避坑](docs/02-custom-termux.md)
- [03. 外层 Termux、PRoot Debian (`--isolated`) 与 `agy` / Claude Code 深度调优](docs/03-proot-and-agents.md)
- [04. 宿主机无线 ADB 闭环：受限 HTTP 桥 vs 直连 `5037` 与 Android 16 真机技巧](docs/04-host-adb-loopback.md)
- [05. 端到端闭环开发：Headless Chromium 预检 + 零 Gradle 离线编译 APK](docs/05-closed-loop-dev.md)
- [06. 整机零损耗备份与换机/重装迁移](docs/06-backup-and-migration.md)
- [07. 全栈高频踩坑与排障速查表](docs/07-troubleshooting.md)

---

## 许可与致谢

- 本仓库的文档、脚本、配置模板与 Skills 采用 [MIT License](LICENSE)。
- 配套 Custom Termux 源码与预编译 APK 基于上游 [`termux/termux-app`](https://github.com/termux/termux-app)（`v0.118.3`），遵循 **GPLv3-only** 协议发布，对应源码分支公开在 [`qwerty123yucy/termux-app@custom`](https://github.com/qwerty123yucy/termux-app/tree/custom)。
- OSC 8 超链接存储层与测试用例改编自上游 PR [`termux/termux-app#5390`](https://github.com/termux/termux-app/pull/5390)（`@matthematics1137`）。
- 预装字体遵循各自开源协议：JetBrains Mono NL（SIL OFL 1.1）、Symbols Nerd Font Mono、Noto Sans Symbols 2（SIL OFL 1.1）。
