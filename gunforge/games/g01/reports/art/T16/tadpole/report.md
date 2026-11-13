# 《纸灯城》巷口水洼试玩

巷口水洼里的三只墨蝌蚪会边游边放大，水声和收拢的圆环预示扑击。射中头部可打断该只的扑击并得 100 分，打中头上的朱印另得 25 分。射中可见的尾巴只消耗光弹。净化三只后结算，灯芯耗尽后可从水洼重试。

[初始小群](start.jpg) · [扑近预警](warning.jpg) · [净化反馈](clear_effect.jpg) · [失败重试](failure.jpg) · [通关结算](result.jpg)

## 试玩

在仓库根目录运行。按 Enter 开始，左键射击，R 换弹。

```powershell
powershell -ExecutionPolicy Bypass -File .\gunforge\start_level_player.ps1 -Package paper.tadpole_encounter -Candidate
```

## Windows Godot 4.6.3 回归

- 头部显示直径为 96.9–127.5 个规范像素。最小姿态的命中区经半径 12 像素的形态学开运算后，有效半径为 48.06 像素，超过 40 像素门槛。朱印完全落在头部内。C09 通过。
- 从生成到耗尽灯芯逐帧检查三只墨蝌蚪。相邻头部命中区最少相隔 139.94 像素，可见轮廓水平间距至少 63.15 像素，运动范围位于 60 像素安全边内。五张 Godot 抓帧通过 C03。
- 普通头部与朱印命中、可见尾巴空枪、扑击前取消伤害、换弹、失败重试、结算均通过。含一次尾部空枪及一次换弹的 5 条输入回放复现完整状态和事件轨迹。正常播放器启动通过，HTTP 和 UDP 均未报错。
- 三关交付候选的隔离副本复跑通过，涵盖 15 站、114 条输入回放、工作台重试、片尾自然播放及四段跳过。

[构建收据](../../../../../../level_design/reviews/tadpole_encounter_build.json) · [数值及抓帧校验](software_checks.json)

编译后可用同一播放器的输入队列复跑，并将原始抓帧写入临时目录。

```powershell
$receipt = Get-Content -Raw gunforge/level_design/reviews/tadpole_encounter_build.json | ConvertFrom-Json
$root = (Get-Location).Path
& $env:GODOT_BIN --path gunforge/framework --script res://tests/tadpole_encounter_tests.gd -- "--build=$($receipt.compiled)" "--assets=$root" "--captures=$env:TEMP/paper-tadpole"
```

## 素材与待验

原 T06 分件源图在旧机缓存。本候选取 T06 透明预览图集里的一帧，沿用原轮廓和朱印，叠加轨迹、缩放和摆动。水面和短水声由构建脚本生成。水声已验证在预警时调度，实听、墨蝌蚪普通态 C06、实体光枪和最终美术仍待验收。接下来将小群放入第一关连续路线，验证过站资源和水洼两侧的目标辨识度。
