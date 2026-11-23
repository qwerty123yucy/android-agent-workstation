# 01. 整体架构与设计取舍

把一台免 Root、免电脑的 Android 手机改造成顺手的本地 AI Agent 工作站，本质上是在解决**“终端渲染手感 → 标准 Linux 运行时 → 安全边界 → 真机执行观测”**四层协同问题。

---

## 一、三层架构总览

```text
[Layer 2] PRoot Debian 13 (--isolated)
          ├─ 标准 glibc ARM64 运行时，承载 agy / Claude Code / Codex / Node / Python
          ├─ 隔离宿主机 /sdcard、/system 与 Bionic 环境变量
          ├─ Headless Chromium 软渲染预检 + 零 Gradle 离线编译 APK
          └─ 通过 127.0.0.1 TCP 流对接外层 ADB Server 或受限 HTTP 桥
                 ▲
                 │  127.0.0.1 TCP（用户态 ptrace 共享环回网，无需挂载共享目录）
                 ▼
[Layer 1] Custom Termux（v0.118.3+custom）
          ├─ 针对现代 Agent TUI 的 10 项底层体验优化（同步输出 / 免缩放平移 / 侧栏穿透 / 超链接 / 字体链）
          ├─ 维护外层原生 ARM64 android-tools（ADB Server @ 127.0.0.1:5037）
          ├─ 可选运行受限 HTTP 桥（adb_bridge.py，包名白名单 + Token + 前台焦点守卫）
          └─ 承载通用 PRoot 启动器与整机零损耗备份/迁移脚本
                 ▲
                 │  127.0.0.1:5555（免 Root、免电脑无线调试回环）
                 ▼
[Layer 0] 宿主机 Android 11–16 真机
          └─ 静默装包 / 启动 / UI 树 XML / 无损截屏 / 真实手势注入 / Logcat
```

---

## 二、四个关键技术取舍

### 1. 为什么选 `Termux + PRoot Debian`，而不是纯 Termux 或 AVF？

- **相对纯原生 Termux**：原生 Termux 使用 Android Bionic libc 与非标准 `$PREFIX` 路径。现代编码 Agent（如 `agy`、Claude Code、Codex）以及无头 Chromium、Python/Node 原生扩展大多面向标准 glibc `linux-arm64` 构建，在 Bionic 下经常撞上动态链接、`/tmp` 权限或 TLS 证书路径坑。PRoot 无需 Root 即可提供完整 Debian 用户态。
- **相对 Android 原生 AVF（Linux Terminal）**：AVF 虚拟机性能更好，但受限于硬件虚拟化与厂商 ROM 开放策略，大量国产旗舰机型并未完整开放或无法方便与外层终端、无线 ADB 协同。Termux + PRoot 几乎全机型通用。
- **相对 SSH 连远端电脑/VPS**：如果本身有常开服务器，手机 Termux + Tailscale + SSH 确实更省电、编译更快；本方案针对的是**纯单机/离线自包含、随时随地直连真机闭环开发**的场景，两者并不冲突，可以在同一个 Custom Termux 里并行使用。

### 2. 为什么强烈建议开启 `proot-distro login --isolated`，而它为何不影响 ADB？

`--isolated` 做了两件关键的事：
1. **不自动挂载** `/sdcard`、Termux `$HOME`、`/system` 等宿主机目录；
2. **清空宿主环境变量**，避免外层 `LD_PRELOAD`、`ANDROID_*`、Bionic `PATH` 污染 glibc 容器。

但它**不会隔离网络**——`proot` 基于用户态 `ptrace` 拦截系统调用，没有创建独立的 Linux network namespace，因此容器内访问 `127.0.0.1` 与外层 Termux 及宿主机完全互通。所有 APK 安装、截屏回传、UI 树导出与日志拉取都可以走 **TCP 流**，无需挂载 `/sdcard`。

### 3. 为什么由「外层原生 Termux」管理 ADB，而不是容器内自管或用 Shizuku `rish`？

1. **Shizuku `rish` 在 PRoot 内跑不通**：`rish` 依赖 `/system/bin/app_process` 与 Android Binder，进入 glibc PRoot 会因路径与动态链接器不匹配失败。
2. **Google 官方 `platform-tools-latest-linux.zip` 只有 `x86_64`**：无法在 ARM64 PRoot 中直接运行；部分旧发行版仓库里的 `adb` 版本偏旧（如 `29.0.6`），缺少 Android 11+ 必需的 `adb pair`。
3. **原生 Termux 的 `android-tools` 是原生 ARM64 最新版**：完整支持 `adb pair` 与 `adb tcpip 5555`，且外层启动的 ADB Server 监听 `127.0.0.1:5037`，PRoot 内（Debian 13 自带同协议 `1.0.41` 的 `adb`）可直接透明复用。

### 4. 为什么不推荐在 ARM64 手机上折腾 Paparazzi / Roborazzi 做 UI 截图测试？

Paparazzi / Roborazzi 底层依赖 AOSP LayoutLib / Robolectric Native Graphics 原生库，Google 官方仅分发 `linux-x86_64`、macOS 和 Windows 构建，**没有官方 `linux-arm64` 版本**。纯业务逻辑单元测试可以直接跑，但做视觉与排版验收，**宿主机本身就是一台真机**——Web/WebView 页面先在容器里用无头 Chromium 预检，原生 App 直接走本机 ADB 回环看真机截图，成本低得多且结果更真实。

---

## 三、权限边界怎么选？

在打通本机 ADB 时，必须先明确你开 `--isolated` 的目的：

- **目的 A：隔离 Agent 权限，防止碰手机其它 App 和个人数据**
  不要把裸 `127.0.0.1:5037` 暴露给 Agent（`adb shell` 拥有 UID 2000 权限，可以从网络侧穿出 `--isolated`）。请采用 **[路线 A：受限本地 HTTP 桥](04-host-adb-loopback.md#路线-a强隔离原生-termux-受限-http-桥)**，只白名单放行当前开发中的单个测试包名。
- **目的 B：主要防环境污染，且信任当前会话或需要完整 `adb` / 授权自动化**
  可采用 **[路线 B：PRoot 直连复用 `127.0.0.1:5037`](04-host-adb-loopback.md#路线-b高效开发proot-直连复用-1270015037)**，并通过全局 Agent 规则与人工授权严格约束操作范围。
