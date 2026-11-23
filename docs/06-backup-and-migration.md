# 06. 整机零损耗备份与换机/重装迁移

这套环境包含外层 Termux 配置、自定义启动脚本、PRoot Debian 容器（含 `.l2s` 硬链接映射层、Locale/时区、完整工具链）以及 Agent 会话历史与 SQLite 摘要库。

本仓库提供了通用化的 [`scripts/host-termux/backup.sh`](../scripts/host-termux/backup.sh) 与 [`scripts/host-termux/restore.sh`](../scripts/host-termux/restore.sh)，同样适用于**旧手机换新机**或**从 Google Play 版 Termux 切换到自编译 / F-Droid 版**。

---

## 一、为什么不能粗暴打包 `$PREFIX`？

1. **Google Play 版 `$PREFIX` 死链陷阱**：Play 版 Termux 的 `$PREFIX/bin` 大量二进制是指向 APK `lib/*.so` 的符号链接，直接整体恢复到 F-Droid/自编译版会全部失效。
2. **PRoot `.l2s` 与 `0000` 挂载点**：直接手工 `tar` 容器目录容易破坏 `proot --link2symlink` 硬链接映射与挂载点权限，而 `proot-distro backup/restore` 会自动正确处理 `manifest.json`、`.l2s` 和挂载点权限。
3. **SQLite WAL 一致性**：若未退出运行中的 `agy` / PRoot 会话，会话数据库的 `-wal` / `-shm` 日志可能未落盘，导致恢复后损坏。

---

## 二、备份步骤（在旧环境「外层 Termux」执行）

1. **彻底退出所有 Agent 与 PRoot 会话**（连续执行 `exit` 回到外层 Termux 提示符，确认无后台 `proot` 进程）。
2. 执行备份脚本（支持通过 `PROOT_DISTRO` / `BACKUP_DIR` / `TERMUX_APK` 环境变量定制）：
   ```bash
   bash ~/workstation/scripts/host-termux/backup.sh
   ```
3. 脚本会自动完成 5 步并自检：
   - 导出 `restore.sh`（如通过 `TERMUX_APK=/path/to/custom.apk` 指定了安装包也会一并拷出）；
   - 通过 `dpkg -S` 精准筛出 `$PREFIX/bin` 下**不属于系统包**的用户自定义脚本（如 `proot-debian`），打包为 `custom-bin.tar.gz`，绝不打包系统二进制或 Play 版软链；
   - 打包外层 Termux `$HOME`（排除 `~/storage` 软链）为 `termux-home.tar.gz`；
   - 使用 `proot-distro backup debian | zstd -1 -T0` 导出完整容器为 `debian-proot.tar.zst`；
   - 校验压缩包完整性、归档条目数与关键路径，并生成 `SHA256SUMS.txt`。

默认输出目录：`/sdcard/Download/termux-migration/`。换机时把整个文件夹拷贝到新手机的 `Download/termux-migration/` 即可。

---

## 三、恢复步骤（在新环境「外层 Termux」执行）

1. 在新手机安装 Custom Termux APK（或 F-Droid 版 Termux）。
2. 打开 Termux，依次执行：
   ```bash
   termux-setup-storage
   bash /sdcard/Download/termux-migration/restore.sh
   ```
3. 恢复完成后执行 `source ~/.bashrc`（或新开一个会话），运行 `proot-debian` 即可回到与旧环境完全一致的容器状态。

---

## 四、安全提醒

- 整机备份归档内包含你在容器里配置的 **API Key、OAuth 登录态、SSH 密钥与聊天历史**，请仅存放在私有加密盘或离线设备，**严禁上传到公开仓库或公共网盘**。
- 如果只需要把不含密钥的 `agy` / `claude` 规则、状态栏脚本与 Skills 同步到新机器，直接同步本仓库或单独备份配置模板文件，排除 `antigravity-oauth-token`、`conversations/` 与 `conversation_summaries.db`。
