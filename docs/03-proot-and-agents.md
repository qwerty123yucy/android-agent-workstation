# 03. 外层 Termux、PRoot Debian (`--isolated`) 与多 Agent 深度调优

---

## 一、手机系统防杀后台（一次性）

在 **设置 → 开发者选项** 中完成两项关键配置：
1. 开启 **停用子进程限制**（Android 12+ 建议开启，防止 Phantom Process Killer 在后台终止 PRoot、Agent 或编译进程）。
2. 将 Termux 的系统电池策略设为 **不受限制 / 允许后台运行**，并在多任务卡片上按需锁定。

---

## 二、外层 Termux 初始化与 PRoot Debian 搭建

> 以下命令在**原生 Termux** 执行，不要进入 PRoot。

### 1. 完整升级并安装基础包

```bash
bash scripts/host-termux/setup-host-termux.sh
```
等价手工命令：
```bash
# 切忌跳过 pkg upgrade 直接 pkg install！
pkg update && pkg upgrade -y
pkg install -y proot-distro tmux zstd android-tools python aapt2
```

> **踩坑提醒**：Termux 是滚动发行版。如果跳过 `pkg upgrade` 直接装 `android-tools`，新装的 `adb` 依赖新版 NDK `libc++_shared.so`，会直接报：
> `CANNOT LINK EXECUTABLE "adb": cannot locate symbol "_ZNSt6__ndk113__hash_memoryEPKvm"`。
> 先执行 `pkg upgrade -y`（或至少 `pkg install --only-upgrade -y libc++`）即可解决。

### 2. 安装 Debian 13 并部署通用启动器 `proot-debian`

```bash
proot-distro install debian
install -m 700 scripts/host-termux/proot-debian.sh "$PREFIX/bin/proot-debian"
```

[`proot-debian.sh`](../scripts/host-termux/proot-debian.sh) 使用 `proot-distro login debian --isolated` 搭配 `env -i` 进入容器：
- 默认隔绝外层 `/sdcard`、`$HOME`、`/system` 与 Bionic 环境变量；
- 首次进入自动补齐 `locales` 与 `tzdata`，可通过环境变量自定义时区与语言，例如：
  ```bash
  # 在外层 ~/.bashrc 中按需设定别名
  alias deb='CONTAINER_TZ=Asia/Shanghai proot-debian'
  ```

### 3. 容器内初始化基础工具与 `tmux`

执行 `proot-debian` 进入 Debian 容器后，运行：
```bash
bash scripts/proot/bootstrap-debian.sh
# 如需在容器内做 Web/WebView 无头视觉预检，追加参数：
# bash scripts/proot/bootstrap-debian.sh --with-headless
```

配套挂载触屏优化版 `tmux` 配置（透传 **OSC 8 超链接** 与 **OSC 标题**，1:1 逐行滑动，自适应日/夜主题无底色状态栏）：
```bash
cp configs/tmux/tmux.conf ~/.tmux.conf
```

在容器内 `~/.bashrc` 确认包含基础路径与无桌面密钥环设置：
```bash
export PATH="$HOME/.local/bin:$PATH"
# 无桌面 Keyring 的容器内使用文件凭据后端（如 gws CLI 需要）
export GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file
```

---

## 三、在 PRoot 内运行 AI Agent 的共性注意项

1. **容器不支持嵌套本地内核沙箱**：PRoot 自身基于用户态 `ptrace`，内核不允许再嵌套 Bubblewrap / userns 沙箱（调用会固定返回 `operation not permitted`）。应跳过内置内核沙箱试错，依靠外层 `--isolated` 与受限桥建立安全边界。
2. **OAuth 浏览器授权体验**：容器内无桌面浏览器，登录时会打印授权 URL。借助 Custom Termux 的多行 URL 提取与单击直跳，直接点终端里的链接就能唤起手机浏览器完成登录。
3. **防止跨 Agent 递归自启**：不要让一个 Agent 在非交互子进程中调用另一个全屏 TUI Agent（如禁止在脚本或工具里自启 `agy`）。

---

## 四、Antigravity CLI (`agy`) 部署与 Custom Termux 侧栏联动

### 1. 安装
```bash
curl -fsSL https://antigravity.google/cli/install.sh | bash
```
安装完成后运行 `agy` 按提示完成登录。

### 2. 配置 `settings.json`、`statusline.py` 与 `title.py`

```bash
mkdir -p ~/.gemini/antigravity-cli ~/.gemini/config
cp configs/agy/settings.example.json ~/.gemini/antigravity-cli/settings.json
cp configs/agy/config.example.json ~/.gemini/config/config.json
install -m 755 configs/agy/statusline.py ~/.gemini/antigravity-cli/statusline.py
install -m 755 configs/agy/title.py ~/.gemini/antigravity-cli/title.py
```

**联动效果说明**：
- **[`statusline.py`](../configs/agy/statusline.py)**：针对手机 45–60 列窄屏优化的极简状态栏——左侧显示执行模式与运行中 subagent 数，右对齐显示精简模型名与 effort。
- **[`title.py`](../configs/agy/title.py)**：将当前会话标题和运行态输出为 `◐/◑ <标题>`（忙碌中）或 `✳ <标题>`（空闲/等待确认）写入终端 OSC 标题。**配合 Custom Termux 抽屉的“OSC 标题占主行 + PRoot 穿透命令留副行”排版**，多开会话时手势侧滑拉出抽屉，一眼就能看清每个窗口在跑什么任务、是否卡在等待确认。

### 3. 全局规则与 Skills 的“克制分层”

手机高频跑长任务时，全局提示词切忌无节制膨胀。推荐三层职责边界：
- **全局规则**（参考 [`configs/agent-rules/GEMINI.example.md`](../configs/agent-rules/GEMINI.example.md)）：只放跨项目环境约束（无嵌套沙箱、ADB 安全边界、后台长任务防 STALL、单轮并行只读探测）。
- **按需加载的 Skills**（[`configs/agent-rules/skills/`](../configs/agent-rules/skills/)）：平时仅占几十个 token 索引，触发时才加载完整规范（本仓库附带 `android-host-adb`、`android-apk-offline`、`headless-ui-verify` 三个通用模板）。
- **单仓库细节**：留在项目本地 `README.md` 与脚本，不堆积到全局。

---

## 五、Claude Code (`claude`) 配置与第三方网关接入

在 PRoot Debian 内安装 Claude Code 后，既可以直接用官方订阅，也可以接入 **Ollama Cloud** 或 **OpenRouter** 等兼容 Anthropic Messages API 的网关。

### 1. 接入 Ollama Cloud（含 `/model` 菜单定制与 Auto Mode 避坑）

在 `~/.bashrc` 中配置环境变量（替换为自己的密钥）：
```bash
export OLLAMA_API_KEY="<YOUR_OLLAMA_API_KEY>"
export ANTHROPIC_BASE_URL="https://ollama.com"
export ANTHROPIC_AUTH_TOKEN="$OLLAMA_API_KEY"
export ANTHROPIC_API_KEY=""               # 必须置空，避免与 AUTH_TOKEN 冲突
export CLAUDE_CODE_AUTO_MODE_SERVER=0     # 关键：关闭第三方网关不兼容的服务端分类器
```

复制并按需修改模型列表模板 [`configs/claude/settings.ollama.example.json`](../configs/claude/settings.ollama.example.json) 到 `~/.claude/settings.json`。

两个实测关键点：
1. **`modelPicker` + `"replaceBuiltInOptions": true`**：如果不设该项，`/model` 选择菜单仍会显示默认的官方占位模型；配好 `modelPicker.options` 并开启 `replaceBuiltInOptions` 后，即可直接列出网关实际提供的模型与上下文/能力标注。
2. **为什么要设 `CLAUDE_CODE_AUTO_MODE_SERVER=0`**：在第三方网关下开启 Auto Mode 时，Claude Code 默认会尝试走服务端分类器（`thirdPartyServerClassifierEnabled`），而 `ollama.com` 并不实现该扩展计费/审批协议，会触发不兼容提示或分类器回退报错。关闭服务端分类器即可恢复干净体验。

### 2. 备用：接入 OpenRouter

参考 [`configs/claude/settings.openrouter.example.json`](../configs/claude/settings.openrouter.example.json)，在 `~/.bashrc` 中指向 `https://openrouter.ai/api`，并设置 `export CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1` 开启网关模型自动发现。

### 3. 配套全局规则

将 [`configs/agent-rules/CLAUDE.example.md`](../configs/agent-rules/CLAUDE.example.md) 按需复制到 `~/.claude/CLAUDE.md`。

---

## 六、其他 CLI Agent 共存建议

- **Codex CLI**：在 Custom Termux 上建议优先使用 `codex --no-alt-screen`，让输出留在主屏，以完整享受 Custom Termux 的**文档行锚定**与**弹键盘主屏免重排**；另外留意 `~/.codex/packages/` 随自动更新可能积攒多版本缓存，定期清理即可。
- **OpenCode / 其它 CLI**：全部安装在 PRoot `$HOME` 内即可和平共处，共享同一套工具链与 ADB 通道。
