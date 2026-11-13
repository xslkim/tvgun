# 《纸灯城》显示器与电视实体光枪实测

手机光枪配 PC 显示器已通过用户验收。电视留到发布验收。用[通过 PC 验收的三关构建](../supplies/report.md)，启动日志的 `build_id` 应以 `ed50339937dd` 开头。用仓库里的播放器加载隔离目录的游戏资源，带上自动发现修复。正式录制时记录手机 HUD 的 APK 版本。[手机构建与录制流程](../../../../../../../../WORKFLOW.md)

```powershell
$stage = 'D:/gunforge_cache/t16_cast_supplies_verified'
& $env:GODOT_BIN --path gunforge/framework --script res://tools/level_player.gd -- "--build=$stage/level.json" "--assets=$stage" "--opening-dir=$stage/gunforge/games/g01/cinematics/opening_original" --network --isolated-settings
```

手机和 PC 连接同一路由器。先启动播放器，再打开 TVGun。等待自动匹配后点手机左下角「开始」，PC 应播放开场。HTTP 和 UDP 模式都可自动发现，手机设置保留原样。PC 防火墙提示时，允许 Godot 在当前局域网收包。

等开场结束或用 Enter 跳过。在播放器按 F11 全屏，按 F2 确认当前为显示器档，四边白框完整。按 C 用手机依次射击 5 个拟合点和 4 个检查点。记录界面的最大误差，按 Enter 应用本次校准。手机音量下键开始或停止录制，单段录制上限为 60 秒。[手机按键与文件格式](../../../../../../../../HANDOVER.md#手机操作) · [追踪实录要求](../../../../../../../../docs/GUNFORGE_PLAN.md#10-自动验收)

## 本轮记录

2026-11-13，Windows 播放器的 UDP 8001、8081 和 9001 广播探测均返回 `TVGUN_HERE 9000`。自动回归通过发现端口的 HTTP 开始与校准射击，以及 19 次 UDP 校准射击。用户重新连接后，PC 观察到由待开始进入开场、进入巷口、实射命中及救援。用户于 2026-11-13 确认手机光枪配 PC 显示器验收通过。此次反馈为整体验收结果，未提供单项测量值或录制文件。

## 实射路线

| 录制段 | 操作与观察 |
| --- | --- |
| 冷捕获、快甩与回屏 | 从新启动的手机端开始，镜头先离开白框并开始录制，再对准白框。停稳后在中心和四角之间快甩。弹匣非满时先试手机「换弹」按钮。再快速移出白框，在手机仍有有效坐标时扣扳机，记录离屏换弹。另录一轮完全失锁后的回屏，观察提示、准星、恢复，以及是否把环境中的矩形误锁为白框。 |
| 巷口、天桥 | 射亮灯笼并记录点灯前后。核对纸身、墨团与硬化态的判定。到天桥观察桥上居民受惊、桥下车铃和甩墨。分别保留点灯和警铃的片段。 |
| 广场、银幕前 | 广场沿龙尾到龙头净化，录龙嘴摆头、龙颚挡弹和特效；银幕前录三束扫光、净化后的暖光和影核解锁。记录强特效时的失锁或误锁。 |
| 站台、工作台 | 站台分别命中纸身与救援墨团，观察反馈和获救后的安全纸身。工作台从第 1 笔到第 7 笔，记录低亮光点，以及第 3 笔盖住第 2 笔时的误射。 |
| 开场、片尾 | 播完开场和片尾，实听旁白、背景声和提示音。开场选录起始、明暗变化和进入首站；片尾选录夜市及工作台旁白、全景和结算。用开始键复验一次跳过，记录画面与音轨是否及时退出。 |

每段录制同时记屏幕型号、分辨率、显示档、距离、环境光、后置镜头、预测提前量、白边与暗带宽度、校准最大误差。记录站点、操作、复现时间和观察结果。离屏换弹用成功数与尝试数记录。误锁由画面复核，注明发生时间或相机帧号。[阶段 0 的既有设备指标](../../../../../../../../docs/GUNFORGE_PLAN.md#13-路线图和验收标准)

## 收取和统计

在仓库根目录用 PowerShell 执行。将 `$profile` 设为本轮使用的 `monitor` 或 `tv`，填入手机显示的录制目录名和 APK 版本。同一块屏幕可有多段录制，各自保留完整目录。

```powershell
$review = Join-Path $env:USERPROFILE 'Documents\PaperLantern-A7'
$profile = 'monitor'
$profilePath = Join-Path $review $profile
New-Item -ItemType Directory -Force $profilePath | Out-Null
$remote = '/storage/emulated/0/Android/data/com.tvgun.gun/files/record'
adb shell ls $remote
$record = 'record_YYYYMMDD_HHMMSS'
$version = '手机 HUD 上的 appVersion'
adb pull "$remote/$record" $profilePath
$clip = Join-Path $profilePath $record
& .\.venv\Scripts\python.exe scripts/summarize_gun_recording.py $clip --app-version $version |
    Out-File -Encoding utf8 (Join-Path $clip 'tracking_summary.json')
```

`tracking_summary.json` 记录 FULL/PARTIAL 时间占比、最长已观测 DEAD、各等级持续时间和数据缺口。占比按有相邻帧证据的区间计算。评审时注明主动移开镜头的片段，保留原始录制。用 `frames_idx.csv` 的 `seq` 标注白框回到画面内的帧。再次运行统计命令并传入 `--return-frame` 和该帧号，可测到首次观测到 FULL 或 PARTIAL 的时间。目录里的 `full_******.jpg` 提供约每秒一张带帧号的参考。精确复核用 `frames.bin` 和[回放工具](../../../../../../../../scripts/run_track_replay.py)。

把每段的设备和场景备注放入同一目录的 `notes.md`，附上枪口回屏帧号、疑似误锁帧号和换弹计数。两块屏幕各自保留原始文件、统计和复现备注，供 A7 审阅。
