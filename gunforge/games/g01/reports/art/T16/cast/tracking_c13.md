# 《纸灯城》三关候选 C13 合成追踪筛查

从 `paper.lantern_city_cast` 构建 `1ca059b468c9268ab77b22e9fb4cb2706cb37b21ec0d6efd3ad0296ab52bbccc` 的隔离播放器取样。101 张截图均为原生 1280×720。Godot 播放器为 48 张内容帧实际绘制显示器和电视的白边，再抓取两种显示设置、电视校准画面及开场首句字幕。101 张整窗画面覆盖水洼、天桥警铃、站台救援、三个 Boss、战斗界面及开场和片尾。两个默认档均使用 24 规范像素白边和 48 规范像素内侧暗区。[透明边缘修整](a7/remaining_edges_report.md)

[显示器 · 水洼](c13_monitor_subject_tadpole.jpg) · [电视 · 天桥警铃](c13_tv_subject_bridge_warning.jpg) · [电视校准](c13_tv_calibration_target.jpg) · [每个样本的追踪结果](tracking_c13.json)

## 结果

- 将整窗画面投影到 640×360 模拟相机画面。正视、斜视、远距和陡斜视各使用一组基准投影和一组带模糊、曝光变化及固定种子噪声的投影，共 808 组。
- 几何范围内的 606 组全部捕获四边并通过中空校验。检测角点与真实投影白边的最大偏差为 0.749 个模拟相机像素。缺失白边和实心白矩形两种反例均被拒绝。
- 陡斜视的 202 组超出既有追踪器几何范围，其中 102 组取得锁定。完整结果随报告保留。

角点参考取自 Godot 整窗截图上的实际白边像素，包含窗口缩放的影响。追踪器沿用 `scripts/guntrack.py`，按播放器 FRAME 消息所用的白边和暗区宽度配置。显示器、电视与光枪的真机连续录制、快速甩枪和离屏重锁仍待验收。

## 复跑

先按[画廊复跑](report.md#全作一致性画廊)生成原始抓帧，并按[构建隔离目录](report.md#构建隔离目录)生成三关副本。以下命令在仓库根目录运行，根目录 `.venv` 需有 `requirements.txt` 中的 `opencv-python-headless`。

```powershell
$gallery = Join-Path $env:TEMP 'paper-cast-gallery'
$output = Join-Path $env:TEMP 'paper-cast-c13'
$checks = (Resolve-Path gunforge/games/g01/reports/art/T16/cast/gallery_checks.json).Path
$script = (Resolve-Path gunforge/framework/tests/paper_tracking_capture.gd).Path
& $env:GODOT_BIN --disable-vsync --audio-driver Dummy --path "$stage/gunforge/framework" --script $script -- "--build=$stage/level.json" "--assets=$stage" "--opening-dir=$stage/gunforge/games/g01/cinematics/opening_original" "--gallery-checks=$checks" "--gallery-captures=$gallery" "--tracking-output=$output"
& .\.venv\Scripts\python.exe -B gunforge/pipeline/art/t16_tracking_screen.py --captures $output --gallery-checks $checks --output "$output/screening.json"
```

本轮原始整窗画面及 SHA-256 清单位于 `D:\gunforge_cache\t16_cast_waiting_room\c13`。[窗口和全屏光枪回归](display_resize/report.md)
