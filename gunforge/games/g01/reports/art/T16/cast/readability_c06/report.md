# 《纸灯城》第三关 C06 整帧复查

从 `paper.lantern_city_cast` 的三关确定性回放进入候车室、站台、绿皮车厢和灯座。Godot 以正式游玩 HUD 渲染 1776×936 画面，记录了入站时间、站内时间与整作时间。绿皮车厢的回放入场时弹匣为空。需要点灯或验证硬化眼的分支先走正常换弹流程。

| 战斗站点 | 普通态达到 0.20 | 硬化眼达到 0.30 且长度 ≥16 px | 1/8 预警保留像素差异 |
| --- | ---: | ---: | ---: |
| 候车室 | 6/6 | 2/2 | 2/2 |
| 站台 | 6/6 | 2/2 | 2/2 |
| 绿皮车厢 | 6/6 | 2/2 | 2/2 |
| 灯座 | 2/2 | 4/4 | 2/2 |

普通态在可见且可命中的墨身区域取 Y′ 差的中位数，参考帧移除该目标并保留同一时刻的灯光、相机和其他对象。20 例的中位差为 0.2111–0.3824，最接近门槛的是站台入场后第 260 帧的墨鸦。硬化态保留同姿态的墨身，逐眼测量得到 0.5266–0.5914 的中位差和 19–21 px 的长度。五组硬化姿态的射击均判无效。

预警对照帧只移除对应预警效果。缩为 222×117 后，8 组各有 110–155 个像素的 Y′ 变化超过 0.03。33 张整帧均通过 C03。普通、硬化与预警的缩略图辨识留待 A5 美术复核。工作台「忘」字 Boss 已完成逐笔采样。[七笔图板与交叉近景](../workbench_readability/report.md)

[普通态与硬化态缩略图](targets_1_8.jpg) · [攻击预警缩略图](warnings_1_8.jpg) · [逐样本数据与构建哈希](checks.json)

## 复跑

按[隔离候选说明](../report.md#构建隔离目录)准备 `$stage`，按[战斗输入回归](../udp/report.md#复跑)的第一条 Godot 命令生成 `$fixture`。随后在仓库根目录的 PowerShell 执行。分析器通过 `--build` 核对四站的构建编号和来源版本。

```powershell
$captures = Join-Path $env:TEMP 'paper-cast-c06'
& $env:GODOT_BIN --path gunforge/framework --max-fps 120 --audio-driver Dummy --script res://tests/train_stop_readability.gd -- "--build=$stage/level.json" "--assets=$stage" "--recording=$fixture" "--captures=$captures"
uv run --locked --project gunforge/pipeline/art python gunforge/pipeline/art/t13_readability.py $captures --build "$stage/level.json" --output "$captures/review"
```
