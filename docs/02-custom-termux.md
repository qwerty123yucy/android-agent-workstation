# 02. Custom Termux：定制特性、配置、构建与迁移避坑

在手机上重度使用 `agy`、Claude Code、Codex、`tmux` 这类高刷新率全屏/行内 TUI 时，官方版 Termux 的很多默认行为会带来高频摩擦。我们的定制版基于官方正式版 **`v0.118.3`**，围绕移动端 AI Agent 体验做了 **11 单分层改造**（源码仓库：[`qwerty123yucy/termux-app@custom`](https://github.com/qwerty123yucy/termux-app/tree/custom)，当前 `versionCode=1014`）。

---

## 一、11 单分层改造详解

前 4 单保持极简与上游 PR 一一对应，后 7 单将本地增强干净隔离：

| # | 提交 / 上游 PR | 核心改造 | 对 AI Agent TUI 的直接价值 |
| :-: | :--- | :--- | :--- |
| 1 | `1bd1a25f` ↔ `#5441` | **DECSET 2026 同步输出**（`CSI ? 2026 h/l`、`DECRQM`、100 ms 单调安全超时） | 减少 `agy`、`claude`、`tmux`、`neovim` 跨读块刷新时的闪烁与撕裂 |
| 2 | `5c6f6185` ↔ `#5442` | **修复非 IME 布局底边距抖动** | 软键盘收起状态下开关左侧抽屉或切换扩展键栏，不再误套用陈旧 `lastMarginBottom` 触发双重 `SIGWINCH` |
| 3 | `0ce2b392` ↔ `#5443` | **文档绝对行视口锚定 + `OverScroller` 亚像素滚动** | `TerminalBuffer` 维护单调文档行号，Agent 流式输出时上翻回看自动锁住当前内容，滑回底端或键入自动恢复跟随 |
| 4 | `952f309e` ↔ `#5444` | **软键盘主屏平移免缩放**（`soft-keyboard-pan-main-screen`） | 解耦主屏逻辑行数 `mRows` 与可视行数 `mVisualRows`，弹收键盘仅平移视口不发 `SIGWINCH` 重排；备用屏（`?1049h` 如 `vim`/`less`/`tmux`）与浮窗自动回退标准行为 |
| 5 | `2bd93fca` | **本地基础体验与 Android 16 适配** | 默认开启主屏平移；内置双排扩展键 + 青色高亮 `SCROLL`（`⇳`）锁定键；返回手势呼出/收起侧滑抽屉；回移 `#4977`（64 KiB IO 缓冲）与 `#5090`（多窗口适配）；16 KB ELF 页对齐（`-Wl,-z,max-page-size=16384`） |
| 6 | `5d27eafe` | **Warm Paper 日/夜原地自适应主题 + Mode 2031** | `onConfigurationChanged` 原地切换不重建 Activity（保住滚动锚点和输入法视口）；内置暖纸浅色默认调色板（`#FAF6EE` / `#2C2925` + WCAG AA ANSI 16）；抽屉三态切换图标；`DECSET 2031` / `DSR 996/997` 实时主题通知；修正 `SGR 2 (DIM)` 浅底渲染与克制型对比度兜底（默认 `2.4`，豁免盒线/色块）；内置 JetBrains Mono NL 四字重 |
| 7 | `531980de` | **侧栏实时命令穿透 PRoot + OSC 标题优先** | `SessionProcessInspector` 读 `/proc/<pid>/stat` 前台进程组 `tpgid`，穿透 `proot` 识别 `debian · agy` / `debian · claude`；应用上报 OSC 0/2 标题优先占主行，真实命令留副行并智能去重；侧栏关闭零后台轮询 |
| 8 | `0436dc6b` | **OSC 8 超链接 + 布局感知多行 URL 提取器** | 单元格级 OSC 8（改编自上游 `#5390`，1024 槽位 GC、宽字符与重排支持）；修复 `getWordAtLocation()` 回滚区越界与 CJK 偏移；`TerminalUrlExtractor` 自动拼接跨行折行、缩进、引用栏（`│`/`>`）、卡片框、分屏与右侧滚动条中的完整 URL |
| 9 | `91f03c29` | **链接交互升级与鼠标捕获防透传** | OSC 8 低透明度极细下划线；本地默认开启 `terminal-onclick-url-open`；在 `agy`/`tmux` 等鼠标捕获模式下点中链接自动拦截，不向下层 TUI 泄漏误触左键；`http(s)://` 直跳浏览器，`file://` 解码复制路径到剪贴板；`Select URL` 支持单击直跳/长按复制 |
| 10 | `cef31f04` | **API 29+ 四层原生有序字体回退链** | `TerminalFontLoader` 使用 `Typeface.CustomFallbackBuilder` 组装：① 主字体（`~/.termux/font*.ttf` 或内置 JetBrains Mono NL 四字重）→ ② `SymbolsNerdFontMono` → ③ `NotoSansSymbols2`（过滤 `Emoji_Presentation=Yes` 防劫持彩色 Emoji）→ ④ 系统 `monospace`（CJK 与彩色 Emoji） |
| 11 | `36106fb3` | **侧栏会话兼容 `vroot` 容器探测** | `SessionProcessInspector` 同时通过命令行与 `/proc/<pid>/exe` 识别带或不带 `--kill-on-exit` 的 `vroot` 会话，兼容 `containers/<distro>/rootfs` 目录层级提取，统一显示 `debian · agy` 等标签 |

---

## 二、推荐配置文件（`~/.termux/termux.properties`）

本仓库已提供带完整注释的模板 [`configs/termux/termux.properties`](../configs/termux/termux.properties)，复制到外层 Termux 后执行 `termux-reload-settings` 即刻生效：

```properties
# 主题模式：system（随系统自动切换）/ light / dark
night-mode = system

# 低对比度 TrueColor/256 色兜底（默认 2.4，设 1.0 关闭，范围 1.0–21.0）
terminal-minimum-contrast = 2.4

# 弹收软键盘时主屏平移免 SIGWINCH 重排（定制版默认 true）
soft-keyboard-pan-main-screen = true

# 单击终端内 OSC 8 / 多行 URL 直跳浏览器或复制 file:// 路径（定制版默认 true）
terminal-onclick-url-open = true
```

进阶自定义：
- **分模式配色**：放 `~/.termux/colors-light.properties` 与 `~/.termux/colors-dark.properties` 可分别覆盖日/夜调色板；
- **自定义主字体**：放 `~/.termux/font.ttf`（可选 `font-bold.ttf` / `font-italic.ttf` / `font-bold-italic.ttf`），其余 Nerd Font 与符号回退链依然自动生效。

---

## 三、安装、共存彩排与构建方式

1. **直接安装预编译 APK**：从本仓库 Releases 下载 `arm64-v8a` APK，核对 SHA-256 后安装。
2. **不敢直接动主力 Termux？先双开彩排**：
   定制仓库的 `custom-coexist` 分支提供了独立共存包名方案（`com.termup` / `Termux+`，内置 `scripts/patch-bootstraps.py` 与 `scripts/termux-deb-patch.c` 透明重写 `.deb` 路径），可与官方 `com.termux` 同机并存试用；确认体验满意后再切回标准包名 `com.termux` 避免路径差异。
3. **自行构建**：
   - **完整 Gradle 构建**：克隆 `qwerty123yucy/termux-app` 的 `custom` 分支，配置好自己的 `keystore.properties` 后运行 `./build-release.sh`（详见 [`termux-custom/README.md`](../termux-custom/README.md)）。
   - **手机内 15 秒零 Gradle 离线快编**：见 [`scripts/termux-offline-build/README.md`](../scripts/termux-offline-build/README.md)。

---

## 四、重要避坑：从 Google Play 版 Termux 迁移

如果你手机上原本装的是 **Google Play 商店版 Termux**，切换到任何 F-Droid / GitHub / 自编译版时需要注意两个关键差异：

1. **不能直接覆盖安装**：签名证书不同，必须先备份再卸载旧版，最后安装新版。
2. **绝不能把 Play 版的 `$PREFIX` 打包覆盖到新版**：
   Google Play 版为了合规，`$PREFIX/bin` 下大量可执行文件其实是指向 APK 内部 `lib/*.so` 的符号链接；一旦卸载 Play 版，拷回来的二进制会全部变成悬空死链。此外，Play 版 `proot-distro` 容器存放在 `$PREFIX/var/lib/proot-distro/containers/debian/rootfs`，而上游标准路径是 `$PREFIX/var/lib/proot-distro/installed-rootfs/debian`。

正确迁移请直接使用本仓库经过实测的 [`backup.sh`](../scripts/host-termux/backup.sh) 与 [`restore.sh`](../scripts/host-termux/restore.sh)（详见 [06. 整机零损耗备份与迁移](06-backup-and-migration.md)）。
