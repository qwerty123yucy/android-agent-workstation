# Custom Termux（`v0.118.3+custom.36106fb`）说明与构建指南

本目录提供与本教程配套的 **Custom Termux** 源码对应关系、构建方式与校验说明。

## 1. 源码与开源合规（GPLv3）

- **上游基线**：[`termux/termux-app`](https://github.com/termux/termux-app) `v0.118.3`（`5b657c6a`）
- **定制源码仓库**：[`qwerty123yucy/termux-app`](https://github.com/qwerty123yucy/termux-app/tree/custom)
- **对应分支与提交**：`custom` @ `36106fb3296894cb39738098733d8f4565cd2844`（`versionCode=1014`）
- **许可协议**：GPLv3-only（继承上游 `terminal-emulator` / `terminal-view` / `termux-shared` 的 Apache-2.0 例外；内置字体分别遵循 SIL OFL 1.1 与 Nerd Fonts 协议）

### 十一单分层提交一览

1. `1bd1a25f`（上游 PR [#5441](https://github.com/termux/termux-app/pull/5441)）：`DECSET 2026` 同步输出（`CSI ? 2026 h/l`、`DECRQM`、100 ms 安全超时）
2. `5c6f6185`（上游 PR [#5442](https://github.com/termux/termux-app/pull/5442)）：修复非输入法布局阶段的陈旧底边距抖动
3. `0ce2b392`（上游 PR [#5443](https://github.com/termux/termux-app/pull/5443)）：文档绝对行视口锚定与 `OverScroller` 亚像素平滑滚动
4. `952f309e`（上游 PR [#5444](https://github.com/termux/termux-app/pull/5444)）：软键盘主屏平移免缩放（`soft-keyboard-pan-main-screen`）
5. `2bd93fca`：本地默认体验（主屏平移默认开启、双排扩展键 + 青色 `SCROLL` 锁键、返回手势抽屉、回移 `#4977` 64 KiB Session IO 与 `#5090` 多窗口适配、16 KB ELF 页对齐与构建脚本）
6. `5d27eafe`：Warm Paper 日/夜原地自适应主题（不重建 Activity）、Mode 2031 / DSR 996/997、克制型 WCAG 对比度保护、内置 JetBrains Mono NL 四字重与抽屉三态切换键
7. `531980de`：侧栏会话列表实时命令探测（`SessionProcessInspector` 穿透 PRoot 识别 `debian · agy` 等）与 OSC 标题主行优先两行排版
8. `0436dc6b`：单元格级 OSC 8 超链接（改编自上游 PR `#5390`）、修复 `getWordAtLocation()` 回滚区与 CJK 偏移、布局感知多行 URL 提取器（`TerminalUrlExtractor`）
9. `91f03c29`：OSC 8 柔和极细下划线、鼠标捕获模式拦截链接防透传、`file://` 点击解码复制路径、`Select URL` 升级
10. `cef31f04`：API 29+ `Typeface.CustomFallbackBuilder` 四层原生有序字体回退链（主字体 → Symbols Nerd Font Mono → Noto Sans Symbols 2 过滤彩色 Emoji → 系统 `monospace`）
11. `36106fb3`：侧栏 `SessionProcessInspector` 兼容 `vroot` 容器会话探测（同时支持命令行与 `/proc/<pid>/exe` 识别及 `containers/<distro>/rootfs` 目录层级提取，`versionCode=1014`）

---

## 2. 安装预编译 APK（GitHub Releases）

如果你不想自行搭建 Android SDK 环境，可以直接在本仓库的 **Releases** 页面下载预编译 `arm64-v8a` APK：

- 文件名：`termux-app_v0.118.3+custom.36106fb_arm64-v8a.apk`
- 包名：`com.termux`（`versionCode=1014`，`versionName=0.118.3+custom.36106fb`）
- 最低系统：Android 7.0+（API 24），已适配 Android 16 16 KB 页大小对齐
- APK SHA-256：`85989b67ce57634ba7f76f1ad7cc7079a77a72e2c77b615152ded9c5287e71d0`
- 签名证书 SHA-256 指纹：`91:FE:D9:97:C4:8F:27:DA:C7:CC:44:86:CA:A1:7B:22:78:AE:0A:62:B3:0F:A2:F8:79:DF:A9:33:92:A4:42:4D`

> **安装注意**：由于签名密钥与官方 F-Droid / Google Play 版不同，首次切换需先按 [迁移指南](../docs/06-backup-and-migration.md) 做好备份、卸载旧版 Termux 后再安装；后续只要继续使用本仓库同密钥签发的新版本，均可直接覆盖升级且保留全部数据。

---

## 3. 从源码自行构建

### 方式 A：标准 Gradle 全量构建（需 JDK 17 + Android SDK + NDK）

1. 生成自己的签名密钥库（妥善保管，勿上传到任何公开仓库）：
   ```bash
   mkdir -p termux-signing
   keytool -genkeypair -v \
     -keystore termux-signing/termux-release.jks \
     -storetype PKCS12 \
     -keyalg RSA -keysize 4096 -validity 10000 \
     -alias termux-release \
     -dname "CN=Termux Custom, OU=Mobile, O=Personal, L=Local, ST=NA, C=US"
   ```
2. 复制 `keystore.properties.example` 为 `termux-signing/keystore.properties` 并填入你的密码与别名。
3. 克隆源码并构建：
   ```bash
   git clone -b custom https://github.com/qwerty123yucy/termux-app.git
   cd termux-app
   ./build-release.sh
   ```

### 方式 B：手机 PRoot 内零 Gradle 离线快编（约 15 秒）

如果你已经装好基础 APK，日常只是在手机容器里微调 Java 源码或内置字体，可使用本仓库的 [`scripts/termux-offline-build/`](../scripts/termux-offline-build/) 工具包跳过 Gradle 直接重编 DEX、16 KB 对齐并签名。

### 验证边界说明

- **已实测**：`terminal-emulator` 180/180 单元测试与 `SessionProcessInspectorTest` 9/9 单元测试通过；4 模块 ECJ + D8 离线编译零报错；`aapt2 dump badging` 确认 `versionCode=1014` 与 6 个内置字体入包；`apksigner verify` 确认 v2 + v3 正式签名校验通过；在 Android 16 真机实测。
- **未在手机 PRoot 内执行**：手机无完整 Gradle/NDK 环境时，全量 `./build-release.sh` 需在具备 Android SDK/NDK 的主机或 CI 环境执行。
