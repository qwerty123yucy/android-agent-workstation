# 05. 端到端闭环开发：Headless Chromium 预检 + 零 Gradle 离线编译 APK

在手机 ARM64 PRoot 容器里做移动端开发，可以将以下四个环节串联为本地闭环流程：
**代码编写 → 无头浏览器预检（Web/WebView）→ 零 Gradle 离线编译签名 APK → 真机 ADB 安装与视觉/手势验收 → 自动修复。**

---

## 一、Web / WebView / Canvas 界面预检（无 GPU 容器避坑）

PRoot ARM64 容器内没有物理 GPU 或 PCI 设备，直接启动 `/usr/bin/chromium` 或保留 Playwright 默认的 `--enable-unsafe-swiftshader` 参数会导致渲染进程崩溃（`GPU process isn't usable / exit_code=256`）。

**实测稳定的解法**：
1. 在 Debian 容器内安装无头壳与中文字体：
   ```bash
   apt update && apt install -y chromium-headless-shell fonts-wqy-zenhei
   ```
2. 使用 Skia 纯软件渲染（`--use-gl=disabled`）并显式剔除 `--enable-unsafe-swiftshader`。本仓库提供了检查脚本 [`scripts/proot/headless-ui-check.mjs`](../scripts/proot/headless-ui-check.mjs)，可在指定手机视口（如横屏 `844×390`、`780×360` 或竖屏 `390×844` @ `deviceScaleFactor=2`）下自动完成：
   - 零 `pageerror` / `console.error` 断言；
   - HUD 胶囊、标签、按钮的水平文本溢出检测（`scrollWidth > clientWidth + 1`）；
   - 同级控件两两 `getBoundingClientRect()` 重叠碰撞检测；
   - 输出高清截图，由多模态 Agent 直接读图复核字形缺字、对比度与视觉节奏。

---

## 二、零 Gradle 离线编译与签名 Android APK

在手机 PRoot 上跑完整 Gradle 往往重、慢且容易撞上 ARM64 `aapt2` 或系统 `javac` 包装器异常。对于轻量原生 Java/Canvas App 或全屏 WebView App，可以直接组合五个独立工具完成离线编译、对齐与 v1/v2/v3 签名（全程仅需 5–15 秒）：

### 1. 所需基础组件
- `openjdk-21-jre-headless`（或 JDK 17+）、`ecj`（`eclipse-jdt-core-compiler-batch.jar`）、`aapt2`、`zipalign`（Debian 源均自带 ARM64 原生包）
- 一个 Android 平台存根 `android.jar`（如 API 30+）
- Google 官方 `r8.jar`（内置 `D8` 字节码转 DEX 编译器）
- 官方 `apksigner`（支持 v1/v2/v3 签名）

### 2. 五步通用构建流水线

```bash
TOOLS_DIR="${ANDROID_BUILD_TOOLS:-/opt/termux-build-tools}"
ECJ_JAR="/usr/share/java/eclipse-jdt-core-compiler-batch.jar"

# 1) 编译并链接资源，生成 R.java 与未对齐基础包（纯原生无 Web 资源时省略 -A assets）
aapt2 compile --dir res -o build/compiled_res.zip
aapt2 link -I "$TOOLS_DIR/android.jar" \
  --manifest AndroidManifest.xml \
  -A assets \
  --java build/gen --auto-add-overlay \
  -o build/base-unaligned.apk build/compiled_res.zip

# 2) 用 Eclipse 批量编译器 (ECJ) 编译 Java 8 目标源码
java -jar "$ECJ_JAR" \
  -1.8 -encoding UTF-8 -nowarn \
  -classpath "$TOOLS_DIR/android.jar" \
  -d build/classes $(find build/gen src -name '*.java')

# 3) 用 Google D8 转为 classes.dex
java -cp "$TOOLS_DIR/r8.jar" com.android.tools.r8.D8 \
  --release --min-api 24 --lib "$TOOLS_DIR/android.jar" \
  --output build/dex $(find build/classes -name '*.class')

# 4) 压入 DEX、zipalign 对齐并执行 v1+v2+v3 正式签名
zip -j build/base-unaligned.apk build/dex/classes.dex
zipalign -f -p 4 build/base-unaligned.apk build/aligned.apk
java -cp "$TOOLS_DIR/apksigner-root/usr/share/java/*" \
  com.android.apksigner.ApkSignerTool sign \
  --ks keystore.jks --ks-pass pass:<YOUR_PASSWORD> \
  --ks-key-alias <YOUR_ALIAS> --key-pass pass:<YOUR_PASSWORD> \
  --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true --v4-signing-enabled false \
  --out build/release-signed.apk build/aligned.apk

# 5) 完整性自检
zipalign -c 4 build/release-signed.apk
java -cp "$TOOLS_DIR/apksigner-root/usr/share/java/*" \
  com.android.apksigner.ApkSignerTool verify --verbose build/release-signed.apk
```

### 3. 实战避坑清单
1. **文件名与 `app_name` 禁用冒号（`:` / `：`）**：避免 Android 浏览器下载器与文件系统路径异常。
2. **WebView 强防缓存**：更新内嵌页面时递增资源文件名后缀（如 `file:///android_asset/app_v102.html?v=102`），设置 `WebSettings.LOAD_NO_CACHE`，并在 `loadUrl` 前调用 `webView.clearCache(true)`。
3. **纯原生 `Canvas` 防彩色 Emoji 劫持**：Android 系统 `NotoColorEmoji.ttf` 会拦截 `⚔`、`⚡`、`❄`、`⚙`、`☄`、`♥` 等 BMP 符号并画成花哨贴纸；自绘 UI 应使用矢量 `Path` 或单色几何字形（`★`、`✦`、`◈`、`↺`）。
4. **弹窗手势起手隔离**：如果底层按钮在 `ACTION_DOWN` 打开弹窗、而弹窗在 `ACTION_UP` 响应按钮/空白关闭，务必增加 `modalGestureStarted` 状态位（仅在弹窗打开后收到新的 `ACTION_DOWN` 才置 `true`）及约 200 ms 关闭防抖，防止同一根手指抬起瞬间把刚打开的弹窗关掉。

---

## 三、把闭环固化进 Agent 指令

可直接参考本仓库的 [`configs/agent-rules/AGENTS.example.md`](../configs/agent-rules/AGENTS.example.md) 与 [`configs/agent-rules/skills/`](../configs/agent-rules/skills/)，把离线编译、无头预检与真机 ADB 验收规范写入项目规则或全局 Skills。
