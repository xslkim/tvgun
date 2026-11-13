# 《纸灯城》片尾摊位局部调色对照

把全景左侧摊位、透光屋檐和邻近桌面的橙红向暖杏收拢。采用有羽化边界的局部调色，保留灯泡的亮芯和纸面明暗。对照构建沿用三关候选的全部玩法、运镜和音轨，单独保存为待审阅版本。[摊位与屋檐近看](stalls_detail.jpg) · [七组 Godot 同帧对照](dissolve_compare.jpg) · [检查数据](checks.json)

| 检查 | 现用候选 | 局部调色 |
| --- | ---: | ---: |
| 全景贴图 C04 色板覆盖率 | 72.96% | 73.44% |
| 叠化第 1.35 秒近朱砂面积 | 1.232% | 0.244% |
| 叠化完成时近朱砂面积 | 1.245% | 0.341% |
| 镜头拉远后近朱砂面积 | 1.031% | 0.313% |

近朱砂面积沿用 C04 报告的较窄色差范围 ΔE00 ≤10。全景贴图仍低于 90% 初始色板门槛。1672×941 的贴图中有 87,635 个 RGB 像素在左侧局部变化，调色区域外的像素和全图 alpha 逐字节一致。对照中七个实际画面都通过 C03 亮度检查。[C04 基线与定位](../c04_report.md)

Godot 按相同模拟时刻比对。街巷末帧和叠化起帧逐字节一致，1.8 秒叠化的透明度、近景退出时点、拉远及回工作台的时序完全一致。54 张路线与叠化帧中 49 张逐字节一致，五张差异帧均处于全景可见阶段。15 站、118 条序列化输入、失败重试、两张片尾贴图预载和四段跳过均通过。结算为 4 条灯芯、11 发光弹、7 人获救、9275 分。[回放与原帧哈希](checks.json)

正式播放器复测了约 90 秒开场与 14 条字幕，以及 58 秒自然片尾。Enter、Esc 和本机 UDP 的四种跳过均停止片尾音轨，重试通过。两处旁白窗口的抽样音画偏差最大为 0.076 秒，使用 Dummy 音频驱动。关卡查看器也已用对照回放打开叠化前一帧。[播放器和回放记录](checks.json)

## 试玩与直接看片尾

在仓库根目录用 PowerShell 编译局部调色对照并启动三关。如果本机尚未生成现用三关候选，先运行一次[现用三关的构建或试玩命令](../../report.md#试玩)。将 `-SkipOpening` 去掉可看开场。

```powershell
& .\.venv\Scripts\python.exe gunforge/pipeline/level_design/build_lantern_city_ending_palette.py
if ($LASTEXITCODE) { throw 'Ending palette build failed' }
$variant = Get-Content -Raw gunforge/level_design/reviews/lantern_city_ending_palette_build.json | ConvertFrom-Json
powershell -ExecutionPolicy Bypass -File .\gunforge\start_level_player.ps1 -Package paper.lantern_city_cast -Build $variant.compiled -SkipOpening
```

本机可在关卡查看器直接跳到叠化前，再按「播放」。`review.dat` 绑定此对照构建。下方复跑命令可在其他机器生成同一格式的录制。

```powershell
$root = (Get-Location).Path
& $env:GODOT_BIN --path gunforge/framework --script res://tools/level_review.gd -- "--build=$($variant.compiled)" "--assets=$root" "--recording=D:/gunforge_cache/t16_cast_ending_palette/review.dat" --at-tick=10758
```

## 复跑

```powershell
$cast = 'gunforge/games/g01/reports/art/T16/cast'
$base = Get-Content -Raw gunforge/level_design/reviews/lantern_city_cast_build.json | ConvertFrom-Json
$work = Join-Path $env:TEMP 'paper-cast-ending-palette'
New-Item -ItemType Directory -Force $work | Out-Null
$baseStage = Join-Path $work 'base-stage'
$variantStage = Join-Path $work 'variant-stage'
$audit = 'gunforge/pipeline/level_design/audit_lantern_city_release.py'
& .\.venv\Scripts\python.exe $audit --package paper.lantern_city_cast --build $base.compiled --output "$work/base_manifest.json" --stage $baseStage
& .\.venv\Scripts\python.exe $audit --package paper.lantern_city_cast --build $variant.compiled --output "$work/variant_manifest.json" --stage $variantStage
$probe = 'res://tests/paper_epilogue_palette_probe.gd'
foreach ($edition in 'before', 'after') {
    $stage = if ($edition -eq 'before') { $baseStage } else { $variantStage }
    & $env:GODOT_BIN --disable-vsync --audio-driver Dummy --path gunforge/framework --script $probe -- "--build=$stage/level.json" "--assets=$stage" "--captures=$work/$edition" "--recording=$work/$edition.dat" --failure-retry=true | Out-File -Encoding utf8 "$work/$edition.log"
    if ($LASTEXITCODE) { throw "Godot route failed for $edition" }
}
& $env:GODOT_BIN --headless --path gunforge/framework --script res://tests/compare_campaign_recordings.gd -- "$work/before.dat" "$work/after.dat" "$work/review.dat" | Out-File -Encoding utf8 "$work/recording.log"
if ($LASTEXITCODE) { throw 'Campaign recording comparison failed' }
uv run --locked --project gunforge/pipeline/art python gunforge/pipeline/art/t16_ending_palette_review.py --before-stage $baseStage --after-stage $variantStage --before-manifest "$work/base_manifest.json" --after-manifest "$work/variant_manifest.json" --receipt gunforge/level_design/reviews/lantern_city_ending_palette_build.json --captures $work --output "$work/review"
```

本轮原始回放、抓帧和播放器日志位于 `D:\gunforge_cache\t16_cast_ending_palette`。调色观感仍待美术签核。[对照隔离清单](candidate_manifest.json) · [现用候选验收包](../report.md)
