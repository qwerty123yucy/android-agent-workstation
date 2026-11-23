# 04. 打通宿主机真机 ADB 闭环（免 Root、免电脑）

手机上跑 AI Agent 编译 Android App 时，最大的痛点是“没有模拟器看真机效果”。换个角度：**Termux 本身就运行在一台真 Android 设备上**，利用 Android 11+ 无线调试，经 `127.0.0.1` 回环即可把宿主机变成 Agent 的真机验收目标。

---

## 一、两条接入路线如何选？

| 维度 | 路线 A：原生 Termux 受限 HTTP 桥（强隔离推荐） | 路线 B：`proot` 直连复用 `127.0.0.1:5037`（开发高效） |
| :--- | :--- | :--- |
| **适用场景** | 严格用 `--isolated` 隔离 Agent 权限，只允许操作单个测试包名 | `--isolated` 仅防环境污染，或需要完整 `adb` / Gradle 仪器测试 |
| **PRoot 内依赖** | 只需 `curl`（零额外工具） | `apt install -y adb`（Debian 13 自带协议 `1.0.41`，与外层一致） |
| **权限隔离** | 强：包名白名单 + Token + `aapt2` 验包名 + 前台窗口校验 | 弱：完整 `adb shell`（UID 2000），需依靠规则与人工授权自律 |

---

## 二、第一步：手机开发者选项（一次性）

打开 **设置 → 开发者选项**：
1. 开启 **USB 调试**
2. 开启 **无线调试**（Android 11+，首次激活需连任意 Wi-Fi）
3. 开启 **充电时不休眠**（避免验收时自动锁屏导致截屏和点击失效）
4. 开启 **停用子进程限制**（Android 12+）
5. **国产 ROM 必开开关**（不开启会导致静默装包失败或 `input tap/swipe` 报 `INJECT_EVENTS` 拒绝）：
   - **OPPO / 一加 / 真我（ColorOS）**：开启 **禁止权限监控**
   - **小米（HyperOS / MIUI）**：开启 **USB 调试（安全设置）**

---

## 三、第二步：在「原生 Termux」连通无线 ADB 并固定 `5555`

> 本步全部在**原生 Termux** 执行，不要进 PRoot。

可直接使用引导脚本：
```bash
bash scripts/host-termux/adb-connect.sh
```
或按以下步骤手工执行：

1. **首次无线配对（Android 11+ 必需）**：
   - 使用手机**分屏**，一边显示 **设置 → 开发者选项 → 无线调试 → 使用配对码配对设备**（切后台会导致配对弹窗关闭、端口失效），另一边打开 Termux；
   - 执行配对并输入 6 位配对码：
     ```bash
     adb pair 127.0.0.1:<弹窗显示的配对端口>
     ```
2. **连接动态调试端口**：
   回到“无线调试”主页面，查看“IP 地址和端口”下的**连接端口**（与刚才的配对端口不同）：
   ```bash
   adb connect 127.0.0.1:<连接端口>
   adb devices -l
   ```
3. **固定到 `5555` 端口（强烈建议）**：
   ```bash
   adb tcpip 5555
   adb disconnect
   adb connect 127.0.0.1:5555
   adb devices -l
   ```

> **脱离 Wi-Fi 后还能用吗？**
> - **Wi-Fi 仅在开机后首次激活无线调试时需要几秒钟**（哪怕连无外网热点也行）。执行完 `adb tcpip 5555` 后，在手机重启前即使关闭 Wi-Fi、切蜂窝网络甚至飞行模式，`127.0.0.1:5555` 回环通道依然保持有效。
> - 如果现场完全没有 Wi-Fi，也可以用 USB 线临时连电脑或另一台手机跑一次 `adb tcpip 5555` 激活；已 Root 设备可在 Termux 直接 `su -c 'setprop service.adb.tcp.port 5555 && stop adbd && start adbd'`。

---

## 四、第三步：在 PRoot `--isolated` 内接入（二选一）

### 路线 A（强隔离）：原生 Termux 受限 HTTP 桥

本仓库提供了零外部依赖的 Python 3 受限桥 [`scripts/host-termux/adb_bridge.py`](../scripts/host-termux/adb_bridge.py)，内置四重防线：
1. 仅监听 `127.0.0.1`；
2. 全接口校验 `X-Bridge-Token`；
3. `POST /install` 先调用 `aapt2 dump badging` 校验包名，非 `ALLOWED_PKG` 返回 `403`；
4. `/screenshot`、`/ui-tree`、`/input` 执行前检查当前前台窗口必须是 `ALLOWED_PKG`，锁屏或切到其它 App 自动拒绝。

在原生 Termux 独立会话启动：
```bash
export ALLOWED_PKG="com.example.myapp"
export BRIDGE_TOKEN="$(head -c 24 /dev/urandom | base64)"
export ADB_SERIAL="127.0.0.1:5555"
echo "BRIDGE_TOKEN=$BRIDGE_TOKEN"
python3 scripts/host-termux/adb_bridge.py
```

在 PRoot `--isolated` 内仅用 `curl` 即可跑完闭环：
```bash
export BRIDGE="http://127.0.0.1:18765"
export TOKEN="<填入原生 Termux 输出的 BRIDGE_TOKEN>"

# 检查状态
curl -fsS -H "X-Bridge-Token: $TOKEN" "$BRIDGE/health"
# 上传并安装 APK（自动校验包名）
curl -fsS -X POST -H "X-Bridge-Token: $TOKEN" --data-binary @./app-debug.apk "$BRIDGE/install"
# 启动测试 App
curl -fsS -X POST -H "X-Bridge-Token: $TOKEN" -H "Content-Type: application/json" -d '{"clear_data": false}' "$BRIDGE/launch"
# 抓 UI 树与无损截屏
curl -fsS -H "X-Bridge-Token: $TOKEN" "$BRIDGE/ui-tree" -o ./ui.xml
curl -fsS -H "X-Bridge-Token: $TOKEN" "$BRIDGE/screenshot" -o ./screen.png
# 注入点击 / 滑动 / 按键 / 文本
curl -fsS -X POST -H "X-Bridge-Token: $TOKEN" -H "Content-Type: application/json" -d '{"action":"tap","x":540,"y":1200}' "$BRIDGE/input"
# 查看实时日志 + 崩溃缓冲区
curl -fsS -H "X-Bridge-Token: $TOKEN" "$BRIDGE/logcat?lines=200"
# 测试完成强停 App
curl -fsS -X POST -H "X-Bridge-Token: $TOKEN" "$BRIDGE/stop"
```

### 路线 B（高效开发）：PRoot 直连复用 `127.0.0.1:5037`

1. PRoot Debian 内安装 `adb` 客户端并校验通道：
   ```bash
   apt update && apt install -y adb
   python3 scripts/proot/adb-check.py
   ```
2. 核对 `adb version` 第一行与原生 Termux 一致（通常同为 `1.0.41`），确认直接命中外层 Server。
3. **三条必守铁律**：
   - **严禁在 PRoot 内执行 `adb kill-server` 或无线 `adb pair`**；若断连最多尝试一次 `adb connect 127.0.0.1:5555`，仍不通则退回原生 Termux 重连。
   - **所有脚本和命令始终显式加 `-s 127.0.0.1:5555`**：ADB daemon 重启后经常自动探测本地 5555 端口并同时显示 `emulator-5554` 与 `127.0.0.1:5555` 两条记录，导致裸 `adb` 报 `more than one device/emulator`。
   - **全程走 TCP 流（不依赖 `/sdcard`）**：
     ```bash
     adb -s 127.0.0.1:5555 install -r -t ./app-debug.apk
     adb -s 127.0.0.1:5555 shell am start -W -n com.example.myapp/.MainActivity --ez silent_test true
     adb -s 127.0.0.1:5555 exec-out screencap -p > ./screen.png
     adb -s 127.0.0.1:5555 shell uiautomator dump /data/local/tmp/ui.xml
     adb -s 127.0.0.1:5555 exec-out cat /data/local/tmp/ui.xml > ./ui.xml
     adb -s 127.0.0.1:5555 shell rm -f /data/local/tmp/ui.xml
     adb -s 127.0.0.1:5555 shell am force-stop com.example.myapp
     ```

---

## 五、Android 16 真机实测高阶经验

### 1. 中文 UTF-8 文本输入避坑
- **不要用 `adb shell input text` 输中文**：它注入硬件键盘事件，绕过输入法拼音组词，直接输出乱码或原始 ASCII。
- **不要依赖后台 `IClipboard` 写入 + `KEYCODE_PASTE (279)`**：Android 10+ 限制非前台焦点的 UID 2000 读写剪贴板。
- **首选无损方式**：对于支持分享/消息入口的 App，直接走 Binder `ACTION_SEND`（`text/plain`），并将 `--es` 内容包在单条 `adb shell "..."` 的单引号内，避免远端 `/system/bin/sh` 按空格拆参：
  ```bash
  adb -s 127.0.0.1:5555 shell "am start -a android.intent.action.SEND -t text/plain --es android.intent.extra.TEXT '你好，这是一段 UTF-8 文本' -n <包名>/<分享入口Activity>"
  ```

### 2. 主力机运行礼仪（无人值守不打扰）
1. **默认静音验收**：自研 App 预留 `--ez silent_test true` 等测试参数，避免自动化跑测时外放音效/BGM；
2. **隔离用户真实存档**：自动化测试写独立临时 `SharedPreferences` / DB 名，绝不覆盖用户数据；
3. **释放屏幕唤醒锁**：若 App 持有 `FLAG_KEEP_SCREEN_ON` 或持续 VSync 绘制，验收后务必 `am force-stop <pkg>` 让屏幕正常息屏；
4. **隐私与前台守卫**：操作前核对 `dumpsys window displays` 的 `mCurrentFocus`（`NotificationShade` 代表锁屏，`permissioncontroller` 代表系统权限框），严禁越权触碰未授权应用，用完清理 `/data/local/tmp/*.xml`。

### 3. 自绘 `Canvas` 与真实按压时长测试
- `uiautomator` 看不到自绘 `Canvas` 内部按钮：建议在 Activity 启用 `android:launchMode="singleTask"` + `onNewIntent` 调试钩子切换场景，并输出结构化 `Logcat` 几何诊断行（屏幕尺寸、`WindowInsets.getDisplayCutout()` 安全挖孔边距、各按钮中心点、两两 `RectF` 重叠/越界数），再配合 `screencap` 目视审计。
- **防跨帧误触**：测菜单/弹窗入口时，务必使用 150 ms 真人按压时长（`adb -s 127.0.0.1:5555 shell input swipe <x> <y> <x> <y> 150`），不要只测零驻留 `input tap`，才能暴露 `ACTION_DOWN → 切出弹窗 → ACTION_UP 误点关闭键` 的穿透 Bug。
