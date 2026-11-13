# 《纸灯城》窗口与全屏光枪映射

修复了两处播放器问题。Godot 的项目拉伸曾叠加到播放器自己的追踪框布局上，导致非原生宽高比及 F11 全屏下的白框出现裁切。播放器现在直接在原生窗口尺寸内画框。UDP 坐标在校准后的规范空间映射到关卡画布，缩放同帧收到的扳机仍使用正确坐标。

## 验证

| 配置 | 窗口与全屏 |
| --- | --- |
| 显示器档 | 1280×720 窗口、1920×1080 F11 全屏、返回后 960×720 窗口 |
| 电视档 | 1120×700 窗口、1920×1080 F11 全屏、返回后 960×720 窗口 |

六种配置均绘出完整白框和内侧暗带，窗口截图里的白框边缘与计算位置相差不到 1 像素。两档分别用带透视畸变的模拟相机，经正式校准界面录入 5 个拟合点和 4 个独立检查点。正式 UDP 入口回归 37 次扳机，含中心墨蝌蚪、右上灯笼、内容区边缘、白边、暗区和框外。白边与暗区扣一发，框外触发换弹。

旧播放器从 960×720 切至 1120×700 的同一帧收到扳机时，沿用了旧画面比例，灯笼一枪偏移 225.03 个规范像素并判空枪。修复后的隔离播放器在同样时序命中灯笼，该枪的坐标误差为 0。六种稳定配置的最大模拟映射误差为 0.00014 个规范像素。

[全屏和 4:3 窗口对照](frame_comparison.jpg) · [坐标、射击与文件哈希](checks.json) · [更新后的隔离清单](../candidate_manifest.json)

显示设置、开场及开始重试菜单、既有 UDP 和 HTTP 战斗回归也通过。修正后的 101 张整窗画面重新完成 C13 合成追踪筛查，几何范围内的 606 组全部通过。[C13 复跑和追踪数据](../tracking_c13.md)回归使用 Windows Godot、本机 UDP 与合成相机。显示器和电视上的实体光枪校准与追踪仍待验收。

## 复跑

按[隔离候选说明](../report.md#构建隔离目录)生成新的 `$stage`，按[战斗输入回归](../udp/report.md#复跑)的第一条 Godot 命令生成 `$fixture`。在仓库根目录的 PowerShell 执行。

```powershell
$output = Join-Path $env:TEMP 'paper-cast-display-resize'
$script = (Resolve-Path gunforge/framework/tests/paper_resize_udp_tests.gd).Path
& $env:GODOT_BIN --path "$stage/gunforge/framework" --max-fps 120 --audio-driver Dummy --script $script -- "--build=$stage/level.json" "--assets=$stage" "--recording=$fixture" "--evidence=$output"
```

Godot 应输出 `"passed":true`。输出目录含六种窗口截图和含 37 次扳机的 `checks.json`。
