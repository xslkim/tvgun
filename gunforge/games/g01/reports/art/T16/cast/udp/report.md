# 《纸灯城》正式播放器战斗输入回归

光枪坐标经过校准后，落在白边或内侧暗区的扳机事件会消耗一发光弹并判为空枪。只有落在整个 1920×1080 校准框之外才会发起换弹。边框射击提交空的命中几何，避免击中延伸到画面之外的实体。UDP 光枪与 Android 兼容 HTTP 入口使用同一套判定。

| 实测路径 | 结果 |
| --- | --- |
| 白边、内侧暗区、经校准移入白边的坐标 | 三次均扣一发，命中数与得分保持原值 |
| 校准框外 | UDP 和 HTTP 都启动换弹，无射击；UDP 验证弹匣补满 |
| 水洼 | 尾部空枪，重复包只扣一发；两次普通头部命中和一次朱印命中合计 325 分 |
| 水洼清场到糖葫芦摊 | 演出期间拒绝开枪；过站后保留分数、弹药、灯芯、救援和射击计数 |
| 天桥 | 居民和自行车的可见区域均为空枪；墨车夫命中加 100 分 |
| 站台 | 误射纸身扣 50 分，纸身和墨团均未受伤；胸口墨团加 100 分并救 1 人；获救后的纸身空枪 |

Godot 4.6.3 Windows 图形播放器以回环 UDP 接收 15 个不同序列号的扳机事件，并通过本机 HTTP 接收 2 次扳机请求。测试用三关 118 条确定性回放定位场景，命中点取自播放器已经绘制的姿态。三关构建编号为 `85d234e0f4b4f2865881d2e355bf897f82d2af93ae6f6950c6431e5adada59c6`。校准边界和实景追踪仍需用实体光枪在显示器与电视上验收。

[回归数据](checks.json) · [更新后的隔离候选清单](../candidate_manifest.json)

## 复跑

先按[候选说明](../report.md)生成三关构建及隔离目录。以下命令沿用隔离步骤中的 `$stage`，在仓库根目录执行。测试使用正式端口，运行前请关闭其他播放器窗口。

```powershell
$fixture = Join-Path $env:TEMP 'paper-cast-campaign.dat'
$script = (Resolve-Path gunforge/framework/tests/paper_udp_combat_tests.gd).Path
& $env:GODOT_BIN --headless --path gunforge/framework --script res://tests/night_market_tests.gd -- "--build=$stage/level.json" "--assets=$stage" "--recording=$fixture"
& $env:GODOT_BIN --path "$stage/gunforge/framework" --max-fps 120 --audio-driver Dummy --script $script -- "--build=$stage/level.json" "--assets=$stage" "--recording=$fixture"
```

两条命令均应输出 `"passed":true`。第二条命令应输出 `"udp_sequences":15`，并在 `checks` 中记录两次 HTTP 回应。
