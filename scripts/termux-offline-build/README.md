# Custom Termux 手机端零 Gradle 离线快编工具包

无需在手机上下载几个 GB 的 Gradle 或完整 Android SDK，直接基于 Debian ARM64 系统包（`openjdk-21-jre-headless`、`ecj`、`aapt2`、`zipalign`）与少量精简 JAR 依赖，在 **~15 秒** 内完成 `terminal-emulator` 单元测试、4 个 Java 模块增量重编译、Google `D8` DEX 合并、Android 16 16 KB 页对齐与 v1/v2/v3 正式签名。

> **适用范围**：修改 `terminal-emulator` / `terminal-view` / `termux-shared` / `app` 的 Java 代码或 `app/src/main/assets/`（如内置字体）。如果改动了 C/C++ JNI 或新增了 `res/` XML 资源 ID，请使用主机 Gradle（`./build-release.sh`）全量编出一次基础 APK。

## 1. 准备依赖目录（默认 `/opt/termux-build-tools`）

1. 在 PRoot Debian 内安装系统依赖：
   ```bash
   apt update && apt install -y openjdk-21-jre-headless ecj aapt2 zipalign
   ```
2. 在工具目录（默认 `/opt/termux-build-tools`，可通过 `TERMUX_BUILD_TOOLS` 覆盖）放入以下标准上游 JAR/工具：
   - `android.jar` — Android SDK 平台存根（API 30）
   - `r8.jar` — Google 官方 `D8`/`R8` 编译器
   - `annotation-1.3.0.jar` 与 `drawerlayout.aar` — AndroidX 编译依赖
   - `d2j/` — `dex2jar`（首次运行自动从基础 APK 提取三方库存根到 `cache/`）
   - `apksigner-root/` — 官方 `apksigner`

## 2. 环境变量配置

| 变量 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `TERMUX_BUILD_TOOLS` | `/opt/termux-build-tools` | 离线工具链目录 |
| `TERMUX_REPO` | `/root/termux-app` | Custom Termux 源码仓库路径 |
| `TERMUX_OUT_DIR` | `/root/migration` | 签名 APK 输出目录 |
| `TERMUX_BASE_APK` | `$TERMUX_OUT_DIR/termux-custom-arm64-v8a.apk` | 作为资源/三方库模板的基础 APK |
| `TERMUX_KEYSTORE_PROPERTIES` | `/root/termux-signing/keystore.properties` | 本地签名配置文件（参考 [`keystore.properties.example`](../../termux-custom/keystore.properties.example)） |

## 3. 日常迭代流程

```bash
# 1. 在源码仓库修改代码、递增 app/build.gradle 的 versionCode 并 git commit
# 2. 运行 terminal-emulator 全量单元测试
python3 scripts/termux-offline-build/run_tests.py

# 3. 15 秒离线编译、16 KB 对齐并签发新版 APK
python3 scripts/termux-offline-build/build_fast_apk.py
```
