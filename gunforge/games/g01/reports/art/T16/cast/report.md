# 《纸灯城》三关角色齐备候选

骑车的居民和停好的自行车位于天桥上层。桥下墨车夫响铃时，居民短暂切换到受惊姿态。居民与车都可被光弹穿过，只消耗弹药，既有桥栏依旧挡弹。天桥仍需净化滴墨和墨车夫。三关候选现包含 8 套居民造型、7 次救援和 7 种墨怪。

[桥上居民与自行车](cyclist_idle.jpg) · [桥下墨车夫响铃](cyclist_and_cart.jpg) · [三关候选天桥](bridge_campaign.jpg) · [广场过站](plaza_handoff.jpg)

[A7 验收材料与真机路线](a7/report.md) · [运行资源逐件检查](a7/asset_coverage.md) · [全作一致性画廊](gallery.html) · [同构建抓帧校验](gallery_checks.json)

[片尾局部调色对照](a7/ending_palette/report.md) · [C04 色板和朱砂用量](a7/c04_report.md) · [C05 文字筛查与复核页](a7/c05_report.md) · [C15 全程纹理、转场和帧时间复测](performance.md) · [C13 合成追踪筛查](tracking_c13.md) · [第三关 C06 整帧复查](readability_c06/report.md) · [工作台 Boss 七笔复查](workbench_readability/report.md) · [天桥与影院攻击预警](attack_warnings/report.md) · [银幕影 Boss 命中区](screen_boss_masks/report.md) · [墨舞龙随动命中区](dragon_masks/report.md) · [开场与有声片尾播放器回归](cutscene_player/report.md) · [窗口和全屏光枪映射](display_resize/report.md)

## 试玩

上一版 PC 鼠标整体通过。最新三关候选改为 8 发开局，支持首次点灯补弹与救援回血，并增加左下角生命数字。下列三关命令会编译新版。[当前 PC 试玩构建与验证](supplies/report.md) · [上一版命中与预警调整](mouse_balance/report.md)

在仓库根目录的 PowerShell 执行。按 Enter 开始，左键射击，R 换弹。三关版可加 `-SkipOpening` 直接进入玩法。

```powershell
powershell -ExecutionPolicy Bypass -File .\gunforge\start_level_player.ps1 -Package paper.footbridge_cyclist -Candidate
powershell -ExecutionPolicy Bypass -File .\gunforge\start_level_player.ps1 -Package paper.lantern_city_cast -Candidate
```

## 软件验证

- 天桥独立回归覆盖灯笼点亮和复亮、桥栏挡弹、滴墨软化及攻击打断。对居民站立、受惊姿态和自行车可见像素各开一枪，三发都判为空枪，分数与灯芯保持原值。回放复现三发输入及居民恢复站立的时序。
- Godot 同帧抓取桥上居民和桥下墨车夫，实测警铃姿态的垂直间距为 169.17 像素。三关路线从天桥进入广场时，居民、受惊姿态和自行车的实体及画面均清理，救援人数仍为 2。四张代表帧通过 C03。
- 三关 15 站、118 条输入回放、水洼与工作台失败重试、58 秒片尾自然播放与四段跳过均通过。候选的 342 个编译资源、2 个开场媒体和 39 个播放器及运行时文件均已核对，384 文件的隔离目录也通过正常启动和完整路线回归。故意更改隔离副本中的骑车居民 PNG 时加载器拒绝启动，恢复后全部哈希再次吻合。

- 当前隔离包已补齐 19 张色彩图的 RGBA8 运行副本，296 张 PNG 均通过对应的编码检查。补齐 RGBA8 阶段的 50 张 Godot 路线原帧逐像素相同。后续累计修整 67 张贴图的透明边缘，已复测缩放、挡弹、弱点和三关路线。[编码证据](a7/asset_coverage.md) · [边缘修整](a7/remaining_edges_report.md)

- 正式播放器已修正校准框边界判定。白边和内侧暗区会扣弹并判为空枪，离开整框才换弹。更新后的隔离包通过 15 个 UDP 扳机事件及 2 次 HTTP 请求，覆盖水洼、天桥、站台与转场。[战斗输入回归](udp/report.md)

[原隔离候选的软件验证记录](software_checks.json) · [A7 基线资源与隔离文件清单](candidate_manifest.json) · [三关构建收据](../../../../../../level_design/reviews/lantern_city_cast_build.json)

## 构建隔离目录

```powershell
$receipt = Get-Content -Raw gunforge/level_design/reviews/lantern_city_cast_build.json | ConvertFrom-Json
$stage = Join-Path $env:TEMP 'paper-lantern-city-cast-waiting-room'
& .\.venv\Scripts\python.exe gunforge/pipeline/level_design/audit_lantern_city_release.py --package paper.lantern_city_cast --build $receipt.compiled --output "${stage}-manifest.json" --stage $stage
& $env:GODOT_BIN --path "$stage/gunforge/framework" --script res://tools/level_player.gd -- "--build=$stage/level.json" "--assets=$stage" "--opening-dir=$stage/gunforge/games/g01/cinematics/opening_original" --isolated-settings
```

## 全作一致性画廊

A7 基线的 51 张 Godot 抓帧通过 C03，覆盖 15 站、8 套居民造型、7 种墨怪、3 个 Boss 和 15 个界面状态。天桥警铃同框来自实战分支，站台路人 A 受困与获救后、水洼小群及封面片尾均来自同一 A7 基线。Chrome 检查了桌面和 420 像素窄窗，画廊图片可加载，墨蝌蚪局部可点开 1776×936 原帧。

生成器用构建清单与三组 Godot 日志核对构建编号，混用旧版日志会被拒绝。以下命令在仓库根目录运行，日志以 UTF-8 写入。

```powershell
$receipt = Get-Content -Raw gunforge/level_design/reviews/lantern_city_cast_build.json | ConvertFrom-Json
$root = (Get-Location).Path
$captures = Join-Path $env:TEMP 'paper-cast-gallery'
New-Item -ItemType Directory -Force "$captures/route", "$captures/controls", "$captures/display" | Out-Null
$common = @("--build=$($receipt.compiled)", "--assets=$root")
& $env:GODOT_BIN --path gunforge/framework --script res://tests/paper_gallery_capture.gd -- @common "--captures=$captures/route" --failure-retry=true | Out-File -Encoding utf8 "$captures/route.log"
& $env:GODOT_BIN --path gunforge/framework --script res://tests/paper_action_tests.gd -- @common "--capture-dir=$captures/controls" "--opening-dir=$root/gunforge/games/g01/cinematics/opening_original" | Out-File -Encoding utf8 "$captures/controls.log"
& $env:GODOT_BIN --path gunforge/framework --script res://tests/display_setup_tests.gd -- @common "--capture-dir=$captures/display" | Out-File -Encoding utf8 "$captures/display.log"
uv run --locked --project gunforge/pipeline/art python gunforge/pipeline/art/t16_consistency_gallery.py --build $receipt.compiled --captures $captures
```

骑车居民采用 T10 纸偶分件导出的站立和受惊两张姿态，搭配 T10 自行车素材。角色美术辨识度、实际铃声和实体光枪仍待验收。两轮共 26,634 帧，全部低于 16.67 ms。候车室第 8520 帧为 8.31–8.55 ms，银幕前首帧为 5.37–5.62 ms。[边缘对照](a7/alpha_edges_report.md) · [性能复跑](performance.md)
