# 《纸灯城》挡弹前景与纸偶透明边缘修整

三关构建更新了巷口左右挡弹纸层，以及摊贩、录像厅老板、检票员、放映员和路人 A、B、C 的七份图集。运行副本在现有像素网格内以 8 源像素为半径，给全透明像素填入最近轮廓的颜色。同距离优先选有颜色的像素。纸偶图集按 91 个绑定矩形分别填色，矩形外的间隙按最近轮廓处理。[逐图记录与回归](edge_fill/checks.json)

两份隔离包各核对 384 个文件。九张运行副本逐像素保留全部 alpha、所有可见 RGB、原尺寸及 ICC 配置，源文件哈希可追溯。源图中紧贴有色轮廓的 61,459 个全透明黑像素已填齐。其余 333 条编译资源、玩法数据、图集的绑定矩形和前景摆放坐标与原构建吻合。[候选入口](../report.md#试玩) · [当前资源清单](../candidate_manifest.json)

## Godot 对照与挡弹

用游戏的纹理区域绘制代码，以 62.5% 和 125% 分别渲染两张前景和七份图集中各一个代表分件。18 组画面均测到局部颜色变化。对照图取 125% 画面中的变化区域，右栏放大显示颜色差值。[修整前后对照](edge_fill/raster_comparison.jpg)

在巷口实测左右两侧各一枪打在挡弹实处、各一枪打在留空处。修整前后相同坐标的结果均为两次挡弹、两次空枪。三关完整路线重新通过 15 站、118 条输入回放、失败重试和片尾四段跳过，结算为 4 条灯芯、11 发光弹、7 人获救、9275 分。正式播放器的站台救援也用 UDP 再次复测。[挡弹坐标和路线数据](edge_fill/checks.json)

C02 仍需整套画面的目视签核。之后从其余 54 张单图中完成了八张优先贴图的修整。[后续修整](priority_edges_report.md) · [最新黑白叠底](alpha_edges/index.html)

## 复跑缩放与挡弹

准备修整前后的隔离目录 `$before`、`$stage`，原构建编号见逐图记录。在仓库根目录的 PowerShell 执行。

```powershell
$script = (Resolve-Path gunforge/framework/tests/paper_edge_fill_capture.gd).Path
$probes = (Resolve-Path gunforge/games/g01/reports/art/T16/cast/a7/edge_fill/probes.json).Path
$output = Join-Path $env:TEMP 'paper-cast-edge-fill'
foreach ($entry in @(@{ name = 'before'; stage = $before }, @{ name = 'after'; stage = $stage })) {
    $dir = $entry.stage
    & $env:GODOT_BIN --path "$dir/gunforge/framework" --script $script -- "--build=$dir/level.json" "--assets=$dir" "--probes=$probes" "--captures=$output/$($entry.name)"
    if ($LASTEXITCODE -ne 0) { throw "Edge capture failed for $($entry.name)" }
}
```
