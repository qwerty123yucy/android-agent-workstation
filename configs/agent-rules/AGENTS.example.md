# Android 真机验收闭环指令模板（可写入项目 `AGENTS.md`）

## 方式 A：通过原生 Termux 受限 HTTP 桥（`$BRIDGE`）

1. 每次修改并编出 APK 后，调用 `POST $BRIDGE/install` 装包并 `POST $BRIDGE/launch` 拉起，等待 1–2 秒让首屏稳定渲染。
2. 先抓 `GET $BRIDGE/ui-tree` 保存 XML，解析控件文案与 `bounds="[x1,y1][x2,y2]"`（需要点击时取中心点 `((x1+x2)/2, (y1+y2)/2)`）；再抓 `GET $BRIDGE/screenshot` 直接看图核验布局、文字截断（含 `...`）、元素重叠与对比度。
3. 验证交互时，调用 `POST $BRIDGE/input` 触发点击/滑动/输入，每次操作后间隔 0.5–1 秒再复查 UI 树与截图。
4. 若返回 `403 target_not_in_foreground`，先查 `GET $BRIDGE/logcat?lines=200` 排查是否闪退，并确认手机未锁屏、未弹出系统权限框。
5. 验收结束后调用 `POST $BRIDGE/stop` 释放屏幕唤醒锁。

## 方式 B：通过复用的宿主机 ADB（`-s 127.0.0.1:5555`）

1. 始终显式指定 `-s 127.0.0.1:5555`，严禁在 PRoot 内执行 `adb kill-server` 或 `adb pair`。
2. 仅操作用户授权的目标测试包名；启动时优先附带静音/测试隔离参数（如 `--ez silent_test true`）。
3. 截图使用 `adb -s 127.0.0.1:5555 exec-out screencap -p > ./screen.png`；UI 树先 dump 到 `/data/local/tmp/ui.xml` 再经 `exec-out cat` 读回，用完删除临时文件。
4. 弹窗/菜单入口按钮补测 `150ms` 真人按压时长（`input swipe x y x y 150`）防跨帧穿透。
5. 验收完毕执行 `adb -s 127.0.0.1:5555 shell am force-stop <package>` 释放屏幕与唤醒锁。
