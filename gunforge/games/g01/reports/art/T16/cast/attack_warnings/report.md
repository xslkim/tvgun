# 《纸灯城》天桥与影院攻击预警

用 `paper.lantern_city_cast` 的三关回放进入天桥和银幕前。每组对照保留同一帧的相机、角色姿态、灯光和 HUD，参考帧仅移除对应预警或攻击效果。Godot 以正式游玩 HUD 渲染 1776×936 画面。

## 天桥

入场 2.05 秒后，第一声车铃、桥下墨车夫的预警圈和桥上居民的受惊动作在同一模拟帧触发。居民在 0.70 秒后恢复站立。墨车夫在预警开始 1.25 秒后甩墨，甩墨声同帧启动，随后的命中扣 1 条灯芯。在铃响时净化墨车夫会取消这次甩墨和扣血。

## 影院

左、中、右放映机入场后分别在 1.50、3.10、4.70 秒开始从各自镜头扫出墨光。每束墨光在 450 ms 后生成本路磁带墨怪。生成 2.80 秒后，蓄力圈和预警音同帧启动，再过 1.25 秒扣 1 条灯芯。

| 胶片盘 | 回归分支 | 对应伤害时刻的灯芯 |
| --- | --- | --- |
| 左 | 扫光前净化，取消扫光与生成 | 4 → 4 |
| 中 | 扫光中净化，取消生成 | 3 → 3 |
| 右 | 磁带已蓄力时净化，移除该墨怪 | 2 → 2 |

桥上车铃、甩墨声和三次磁带蓄力声均由正式音频节点在对应事件帧解码并启动。无声驱动用于复跑调度，实听音量、分辨度和电视扬声器表现待设备复核。

## 画面对照

12 张游戏帧均通过 C03。缩至 222×117 后，12 组对照均有像素差异。影院的 200 ms 蓄力预警保留 119–131 个 Y′ 变化超过 0.03 的像素，1000 ms 时为 27–37 个；预警尾段在缩略图中更弱。实际距离的辨识度仍待美术与设备复核。

[1/8 同帧对照图板](comparison_1_8.jpg) · [逐帧、音轨与灯芯记录](checks.json)

## 复跑

按[隔离候选说明](../report.md#构建隔离目录)准备 `$stage`，按[战斗输入回归](../udp/report.md#复跑)的第一条 Godot 命令生成 `$fixture`。在仓库根目录的 PowerShell 执行。

```powershell
$captures = Join-Path $env:TEMP 'paper-cast-attack-warnings'
& $env:GODOT_BIN --path gunforge/framework --max-fps 120 --audio-driver Dummy --script res://tests/paper_attack_warning_tests.gd -- "--build=$stage/level.json" "--assets=$stage" "--recording=$fixture" "--captures=$captures"
uv run --locked --project gunforge/pipeline/art python gunforge/pipeline/art/t16_attack_warnings.py $captures --build "$stage/level.json" --output "$captures/review"
```

Godot 应输出 `"passed":true`。分析结果应记录 12 组帧对照和 4 条中断攻击的分支。
