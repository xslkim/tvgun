# 《纸灯城》夜市巷口图层显露检查

对通过 PC 鼠标验收的构建 `ed50339937dd3994adf58a7db62fb3bce341f90c8723a3dccf01342f8c69c5d3`，用 Windows Godot 4.6.3 Compatibility 在 1776×936 透明视口逐层抓帧。将七张已批准的巷口设计遮罩按站点内容原点 (72, 42) 裁切到视口，逐层排除前方 alpha ≥ 254 的像素。巷灯参与前方遮挡计算。巷口 11 个场景段的图层绑定相同且视差系数均为零，共用一组图层位置。[逐层数据与哈希](c07b_checks.json) · [设计遮罩](../../../../../bible/geometry/alley_extent_v1/baseline.json)

| 图层 | 暴露像素中 alpha < 254 | alpha < 128 |
| --- | ---: | ---: |
| [近景右](layer_diagnostics/near_right.png) | 2,130 | 0 |
| [近景左](layer_diagnostics/near_left.png) | 9,934 | 1 |
| [中景右](layer_diagnostics/mid_right.png) | 3,784 | 0 |
| [中景左](layer_diagnostics/mid_left.png) | 5,584 | 0 |
| [中景地面](layer_diagnostics/mid_ground.png) | 2,102 | 0 |
| [远景城镇](layer_diagnostics/far_town.png) | 13,908 | 0 |
| [远景底板](layer_diagnostics/far_base.png) | 0 | 0 |

诊断图中灰色为合格的显露像素，琥珀色为 alpha 128–253，红色为 alpha < 128。按现行不透明门槛，六层共 37,442 个像素需要复核，均在距离设计遮罩边界 5 像素以内。唯一低于 128 的像素在近景左上边缘 (721, 2)，alpha 为 123。遮罩内侧超过 1 像素处未出现 alpha < 128。人为清空中景左一块 9×9 的显露区域，检测准确报出新增的 81 个内部缺口像素。

本轮结果覆盖已有批准遮罩的巷口七层，保留现行 C07b 门槛及未通过状态。图层和玩法使用现有候选资源。全作背景覆盖已有 [C07a 回放与视差极限复测](c07a_report.md)。

## 复跑

在仓库根目录执行，使用对应构建的隔离目录和 Godot。通过 `uv sync --locked --project gunforge/pipeline/art` 准备美术检查环境。

```powershell
$stage = 'D:/gunforge_cache/t16_cast_supplies_verified'
$work = Join-Path $env:TEMP 'paper-cast-c07b'
$probe = (Resolve-Path gunforge/framework/tests/paper_alley_layer_extents.gd).Path
& $env:GODOT_BIN --disable-vsync --audio-driver Dummy --path "$stage/gunforge/framework" --script $probe -- "--build=$stage/level.json" "--assets=$stage" "--output=$work/captures"
if ($LASTEXITCODE) { throw 'Layer capture failed' }
$manifest = (Resolve-Path gunforge/games/g01/reports/art/T16/cast/supplies/candidate_manifest.json).Path
$checker = (Resolve-Path gunforge/pipeline/art/t16_alley_layer_extents.py).Path
uv run --locked --project gunforge/pipeline/art python $checker --stage $stage --manifest $manifest --captures "$work/captures" --output "$work/checks.json"
```

严格不透明检查当前返回 1，并生成 `checks.json` 和七张诊断图。
