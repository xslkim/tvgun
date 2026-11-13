# 《纸灯城》银幕影 Boss 命中区复查

从 `paper.lantern_city_cast` 的三关回放进入银幕前。Godot 在三个磁带墨怪都已生成时逐盘测量可见且可命中的墨色，并在第三盘净化后测量影核。每个目标都用同一姿态和相机抓取显示帧与隐藏该目标的参考帧。

| 目标 | 实际可命中像素 | 超出墨色的命中像素 | 有效半径 |
| --- | ---: | ---: | ---: |
| 左胶片盘墨渍 | 10,038 | 0 | 56.49 px |
| 中胶片盘墨渍 | 10,038 | 0 | 56.49 px |
| 右胶片盘墨渍 | 10,038 | 0 | 56.49 px |
| 影核 | 10,726 | 0 | 58.42 px |

四个目标的有效半径均达到 40 px。加上当前相机视差的完整偏移范围，四个目标的边界均避开 60 px 边缘带和游玩 HUD 保留区。四张游戏帧通过 C03。隐藏目标后，96.0%–100% 的命中区像素至少有一个 RGB 通道变化达到 8/255。[游戏画面与命中边界](hit_regions.jpg)

三台放映机的机身射击均判无效，各扣一发光弹并触发无效音效。机身耐久、净化计数和得分保持原值。影核锁定时射向其位置判空枪。[误射中间机身的实际画面](projector_invalid.jpg)

每盘净化都移除本路磁带墨怪、将对应墨光切换为暖光并加 100 分。同帧暖光与墨光对照中，三束光各自改变了 30,859–40,572 个像素。第三盘净化后影核出现，命中再加 100 分并启动火车站转场。转场期间重送旧影核姿态会被拒绝，灯芯、光弹、救援和得分带入候车室。[逐盘暖光对照](light_swaps.jpg) · [回归数据和哈希](checks.json)

实际观看距离下的墨色辨识度与实体光枪瞄准仍待复核。

## 复跑

按[隔离候选说明](../report.md#构建隔离目录)准备 `$stage`，按[战斗输入回归](../udp/report.md#复跑)的第一条 Godot 命令生成 `$fixture`。在仓库根目录的 PowerShell 执行。

```powershell
$captures = Join-Path $env:TEMP 'paper-cast-screen-boss'
& $env:GODOT_BIN --path gunforge/framework --max-fps 120 --audio-driver Dummy --script res://tests/screen_boss_mask_tests.gd -- "--build=$stage/level.json" "--assets=$stage" "--recording=$fixture" "--captures=$captures"
uv run --locked --project gunforge/pipeline/art python gunforge/pipeline/art/t16_screen_boss_masks.py $captures --build "$stage/level.json" --output "$captures/review"
```

Godot 应输出 `"passed":true`。分析结果应记录四个目标的有效半径均达标、三束暖光切换均可见，且没有命中像素落在墨色之外。
