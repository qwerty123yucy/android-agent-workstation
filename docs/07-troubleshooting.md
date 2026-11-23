# 07. 全栈高频踩坑与排障速查表

| 所属层 | 常见现象 | 根因 | 解决方法 |
| :--- | :--- | :--- | :--- |
| **外层 Termux** | 装完 `android-tools` 后跑 `adb` 报 `cannot locate symbol "_ZNSt6__ndk113__hash_memoryEPKvm"` | 局部安装未升级基础库，新二进制与旧 `libc++_shared.so` ABI 不匹配 | 原生 Termux 执行 `pkg upgrade -y`（或先 `pkg install --only-upgrade -y libc++`） |
| **外层 Termux** | 从 Google Play 版迁移到自编译版后，外层命令全报 `No such file` | 误把 Play 版 `$PREFIX` 整体恢复，带入了指向已卸载 APK 的悬空软链 | 不要覆盖恢复 `$PREFIX`，使用 [`restore.sh`](../scripts/host-termux/restore.sh) 重装外层包 + `--skip-old-files` 补回自定义脚本 |
| **外层 Termux** | Agent 跑长任务或编译时整个容器突然被杀（`Killed`） | Android 12+ Phantom Process Killer 或 OEM 后台电池限制 | 开发者选项开启 **停用子进程限制**，并将 Termux 电池策略设为无限制 |
| **PRoot 容器** | 命令执行工具在开启内置沙箱时固定报 `operation not permitted` | PRoot 为用户态 `ptrace`，内核不允许再嵌套 userns/bwrap 沙箱 | 关闭/跳过内置本地沙箱，依靠 `--isolated` 容器与外层受限桥做边界隔离 |
| **Claude Code** | 接入 Ollama Cloud 后 Auto Mode 报网关不兼容或分类器失败 | 第三方网关未实现 Anthropic 服务端分类器扩展协议 | 在 `.bashrc` 与 `settings.json` 中设置 `CLAUDE_CODE_AUTO_MODE_SERVER=0` |
| **Claude Code** | `/model` 菜单仍显示官方占位模型名而非网关真实模型 | 未替换内置选项列表 | 在 `~/.claude/settings.json` 配置 `modelPicker.options` 并设 `"replaceBuiltInOptions": true` |
| **ADB 连接** | 裸 `adb` 命令报 `more than one device/emulator` | daemon 重启后自动探测本地 5555，导致 `emulator-5554` 与 `127.0.0.1:5555` 并存 | 所有脚本/命令统一显式加 **`-s 127.0.0.1:5555`** |
| **ADB 连接** | 静默装包失败或 `input tap/swipe` 报 `INJECT_EVENTS` 权限拒绝 | 国产 ROM 默认禁止 ADB 注入事件 | ColorOS 开启 **禁止权限监控**；HyperOS / MIUI 开启 **USB 调试（安全设置）** |
| **ADB 连接** | `screencap` 保存的 PNG 无法打开或花屏 | 用了 `adb shell screencap -p` 导致 `\n` 被 PTY 转为 `\r\n` | 改用 **`adb -s 127.0.0.1:5555 exec-out screencap -p > screen.png`** |
| **ADB 连接** | `input text` 输入中文变乱码；后台写剪贴板粘贴无效 | 硬件键盘事件绕过输入法；Android 10+ 禁止无焦点 UID 2000 读写剪贴板 | 分享/消息类走 `am start -a android.intent.action.SEND -t text/plain --es ...` |
| **ADB 连接** | `uiautomator dump` 超时或报 `could not get idle state` | 页面存在持续运行的无限动画（如转圈 Loading） | 改看 `screencap` 截图，或在 Debug 模式提供关闭动画开关 |
| **ADB 连接** | 手机重启后 `adb` 断连 | 重启后无线调试开关自动重置 | 重新开启无线调试，在原生 Termux 跑 `adb connect 127.0.0.1:<新端口>`（通常无需重 `pair`）再补 `adb tcpip 5555` |
| **UI 预检** | Playwright / Chromium 启动崩溃（`exit_code=256`） | 无 GPU 容器下默认 `--enable-unsafe-swiftshader` 触发 GPU 进程异常 | 改用 `/usr/bin/chromium-headless-shell` + `ignoreDefaultArgs: ['--enable-unsafe-swiftshader']` + `--use-gl=disabled` |
| **离线编译** | 容器内 `/usr/bin/javac` 报错；`gh pr edit` 报 `projectCards` 废弃错误 | Debian ARM64 下部分包装器与旧版 `gh 2.46.0` GraphQL 字段兼容性问题 | Java 编译直调 `ecj`（`eclipse-jdt-core-compiler-batch.jar -1.8`）；编辑 GitHub PR 走 `gh api -X PATCH repos/{owner}/{repo}/pulls/{num}` |
| **云端同步** | `rclone` 传 Google Drive 限流、卡死或大文件反复整包重传 | 公共 `client_id` 限流，或移动/代理网络大块并发超时 | 配置个人 Google Cloud OAuth `client_id`，混合目录用单流 `4M` 分片（`--transfers 1 --drive-chunk-size 4M --tpslimit 6 --timeout 120s`） |
