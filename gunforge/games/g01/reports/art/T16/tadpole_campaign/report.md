# 《纸灯城》三关候选 · 巷口水洼

巷口第六波结束后，三只墨蝌蚪从水洼扑近。净化小群后进入糖葫芦摊。水洼属于第一站，路线仍为三关 15 站。本候选保留开场、纸质 HUD 和 58 秒有声片尾。

[进入水洼](entry.jpg) · [扑击预警](warning.jpg) · [最近姿态](near.jpg) · [糖葫芦摊衔接](stall_handoff.jpg) · [失败重试](retry.jpg)

## 试玩

在仓库根目录的 PowerShell 启动。按 Enter 开始，左键射击，R 换弹。加 `-SkipOpening` 可直接进玩法。

```powershell
powershell -ExecutionPolicy Bypass -File .\gunforge\start_level_player.ps1 -Package paper.lantern_city_tadpole -Candidate
```

## 软件验证

- 水洼继承巷口的 4 条灯芯、12 发光弹、3500 分和 1 名获救居民。回归中三发命中朱印，进入糖葫芦摊时带着 9 发光弹和 3875 分。灯芯和救援人数在两次过场中保持一致，离场实体、遮挡层和过期瞄准均通过检查。
- Windows Godot 4.6.3 逐帧检查放任小群扑击的 481 个姿态，头部最小水平间距为 138.98 像素。相邻头部始终分开，头部中心可命中。预警水声按时触发，巷口收尾期间已预载蝌蚪素材。水洼和工作台两处均可失败，并从巷口开场重试。
- 为暗水洼加了暖色反光。四个姿态、三只墨蝌蚪的 12 个 C06 普通态样本均达到 0.20 数值门槛。调色前为 0.128–0.200，调色后为 0.210–0.283。五张代表抓帧通过 C03。C06 的 1/8 缩略图辨识度留待美术验收。
- 三关 15 站、118 条输入回放、片尾自然播放及四段跳过均通过。正常播放器载入开场，鼠标、键盘和本机模拟光枪输入通过。真实光枪、水声听感和候选美术仍待验收。

[构建收据](../../../../../../level_design/reviews/lantern_city_tadpole_build.json) · [回归及对比度证据](software_checks.json)

## 复跑

```powershell
$receipt = Get-Content -Raw gunforge/level_design/reviews/lantern_city_tadpole_build.json | ConvertFrom-Json
$root = (Get-Location).Path
& $env:GODOT_BIN --path gunforge/framework --script res://tests/tadpole_campaign_tests.gd -- "--build=$($receipt.compiled)" "--assets=$root" "--captures=$env:TEMP/paper-tadpole-campaign" --failure-retry=true
```

抓帧输出含同姿态的 `puddle_<姿态>.png`、移除墨蝌蚪后的 `puddle_<姿态>_background.png` 和逐只的 `puddle_<姿态>_tadpole<序号>_mask.png`，可用美术工具的 `checks.run("C06", ...)` 复算。构建复用独立试玩的 T06 透明图集单帧、头部遮罩和合成水声。骑车的人与路人 A 的 T10 分件已备好，下一步先在一个救援站验证路人 A 的纸身保护与胸口墨团判定。
