# 《纸灯城》三关候选性能复测

在 Windows Godot 4.6.3 Compatibility、RTX 3080 Ti 上运行 `paper.lantern_city_cast` 的隔离包。1776×936 游戏视口逐个固定步绘制，窗口为 1280×720，关闭垂直同步并使用 Dummy 音频。两轮共 26,634 帧，覆盖 15 站、三次投影机扫光刷怪、58 秒片尾和重开的纹理缓存清理。[试玩与构建清单](report.md) · [逐站和转场数据](performance.json)

## 候车室回放检查点

候车室第 8520 帧曾录到 18.26 ms。三次定点回放中，场景纹理上传均为零。使用正式的 60 帧检查点周期时，当帧花 2.85–2.93 ms 保存检查点。将探针周期设为 61 帧后，该帧的检查点耗时为零。周期调整仅用于对照采样。

第 8520 帧已累积 1162 条历史事件。内部检查点保存独立的事件数组并复用这些条目，载入检查点时再深拷贝。公开快照继续保存完整的独立副本。三次定点复测中，检查点耗时降至 1.92–2.05 ms。两轮全程在该帧分别录到 8.55 ms 和 8.31 ms。18 项会话回归覆盖随机跳转、分支、重开和不同刷新率，26 项关卡工具测试全部通过。[分段数据](performance.json) · [上一构建的全程记录](performance_before_waiting_room_checkpoint.json)

| 全程复测 | 样本 | P95 | 最慢帧 | 超过 16.67 ms |
| --- | ---: | ---: | ---: | ---: |
| 第 1 轮 | 13,317 | 7.55 ms | 14.55 ms | 0 |
| 第 2 轮 | 13,317 | 7.71 ms | 16.25 ms | 0 |

两轮所有站点和章节转场均在 16.67 ms 内。银幕前首帧分别为 5.37 ms 和 5.62 ms。上一构建用原有切场等待预热两组 HUD 字形，并将过站当帧的检查点顺延一帧。[银幕前首帧分段测量](performance_before_waiting_room_checkpoint.json)

隔离包通过 15 站路线、失败重试和片尾跳过。与上一构建相比，118 条序列化输入及过站记录完全一致，50 张 Godot 路线画面逐像素一致。[回归记录](performance.json)

## C15 资产纹理预算

按 RGBA8 与实际 mip 尺寸计入站点、纸偶、界面和字形。转场峰值取在场、预热及切前切后两帧的纹理并集。五项资产峰值与上一构建逐字节一致，七份纸偶图集的最大边长为 2041 像素。

| 类别 | 最新峰值 | 预算 |
| --- | ---: | ---: |
| 站点图层和灯光 | 28.83 MiB | 48 MiB |
| 居民、墨怪和道具 | 22.92 MiB | 32 MiB |
| 特效和界面 | 8.67 MiB | 16 MiB |
| 单站合计 | 48.37 MiB | 96 MiB |
| 转场合计 | 72.33 MiB | 160 MiB |

## 复跑

按[构建隔离目录](report.md#构建隔离目录)准备 `$stage`。关闭其他性能回归窗口，在仓库根目录运行。

```powershell
$profiles = Join-Path $env:TEMP 'paper-cast-waiting-room'
$cast = 'gunforge/games/g01/reports/art/T16/cast'
$route = (Resolve-Path gunforge/framework/tests/night_market_tests.gd).Path
$probe = (Resolve-Path gunforge/framework/tests/screen_handoff_profile.gd).Path
New-Item -ItemType Directory -Force $profiles | Out-Null
foreach ($round in 1, 2) {
    & $env:GODOT_BIN --disable-vsync --audio-driver Dummy --path "$stage/gunforge/framework" --script $route -- "--build=$stage/level.json" "--assets=$stage" "--profile=$profiles/run_$round.json" "--recording=$profiles/profile_$round.dat" | Out-File -Encoding utf8 "$profiles/run_$round.log"
    if ($LASTEXITCODE) { throw "Godot profile failed on run $round" }
}
& .\.venv\Scripts\python.exe gunforge/pipeline/level_design/profile_lantern_city_cast.py --receipt gunforge/level_design/reviews/lantern_city_cast_build.json --manifest "$cast/candidate_manifest.json" --reference-report "$cast/performance_before_waiting_room_checkpoint.json" --output "$profiles/performance.json" "$profiles/run_1.json" "$profiles/run_2.json"
foreach ($round in 1, 2, 3) {
    & $env:GODOT_BIN --disable-vsync --audio-driver Dummy --path "$stage/gunforge/framework" --script $probe -- "--build=$stage/level.json" "--assets=$stage" "--recording=$profiles/profile_1.dat" --checkpoint-interval=60 --tick=8520 --section=waiting_room.waiting_room "--output=$profiles/waiting_room_$round.json"
    if ($LASTEXITCODE) { throw "Godot probe failed on run $round" }
}
```

逐帧日志和定点探针位于 `D:\gunforge_cache\t16_cast_waiting_room`。保留更早的测量供回溯。[银幕首帧优化前](performance_before_screen_handoff.json) · [透明边缘修整前](performance_before_edge_repairs.json) · [姿态序列化优化前](performance_before_session_optimization.json)
