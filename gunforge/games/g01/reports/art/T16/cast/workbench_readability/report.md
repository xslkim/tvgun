# 《纸灯城》工作台「忘」字七笔复查

用 `paper.lantern_city_cast` 的三关回放进入爷爷的工作台。从第一笔开放起，逐笔采集朱砂描边的亮、暗两种状态。Godot 按实际射击层级生成每笔的可命中遮罩，再瞄准画面中的落笔光点逐笔净化。七枪均命中对应笔画，合计加 700 分。第七笔完成后进入点灯片尾。

| 笔画 | 可命中有效半径 | 墨身与同帧背景的 Y′ 中位差 | 低亮描边与光点在 1/8 图的变化像素 |
| --- | ---: | ---: | ---: |
| 1 · 亡 · 点 | 40.80 px | 0.4667 | 31 |
| 2 · 亡 · 横 | 55.97 px | 0.4471 | 45 |
| 3 · 亡 · 竖折 | 65.49 px | 0.4565 | 61 |
| 4 · 心 · 左点 | 44.75 px | 0.4249 | 43 |
| 5 · 心 · 卧钩 | 75.46 px | 0.4358 | 102 |
| 6 · 心 · 中点 | 40.71 px | 0.4496 | 28 |
| 7 · 心 · 右点 | 41.75 px | 0.4339 | 40 |

七笔的有效半径均达到 40 px，墨身亮度差均达到 C06 的 0.20 门槛。描边低亮时的透明度约 50%，在 222×117 缩略图上仍有 28–102 个像素的 Y′ 变化超过 0.03。所有落笔光点都在当前笔的可射区内，14 张高亮和低亮整帧均通过 C03。

第 2、3 笔有 363 个交叉像素，全部归上层第 3 笔。在第 3 笔近不透明的 303 个像素里，第 2 笔的描边带来的最大 Y′ 变化为 0.0137。向图中白圈标注的交叉点射击，判定为第 3 笔擦伤，第 2 笔保持原状态，随后仍可瞄准第 2 笔的落笔光点完成净化。

[七笔高低亮缩略图](strokes_1_8.jpg) · [第 2、3 笔交叉近景](crossing.jpg) · [逐笔命中、指标与哈希](checks.json)

轮廓和墨的质感、低亮提示的实际辨识度，以及显示器与电视上的实体光枪体验留待第三关 A5 复核。

## 复跑

按[隔离候选说明](../report.md#构建隔离目录)准备 `$stage`，按[战斗输入回归](../udp/report.md#复跑)的第一条 Godot 命令生成 `$fixture`。在仓库根目录的 PowerShell 执行。

```powershell
$captures = Join-Path $env:TEMP 'paper-cast-workbench'
& $env:GODOT_BIN --path gunforge/framework --max-fps 120 --audio-driver Dummy --script res://tests/workbench_boss_readability.gd -- "--build=$stage/level.json" "--assets=$stage" "--recording=$fixture" "--captures=$captures"
uv run --locked --project gunforge/pipeline/art python gunforge/pipeline/art/t16_workbench_readability.py $captures --build "$stage/level.json" --output "$captures/review"
```

Godot 应输出 `"passed":true`。分析结果应记录七笔的有效半径、C06 数值结果和低亮缩略图差异，三项均为 7 例。
