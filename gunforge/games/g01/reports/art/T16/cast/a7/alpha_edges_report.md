# 《纸灯城》半透明边缘复查

用 `paper.lantern_city_cast` 当前隔离包逐件生成 136 张黑白叠底对照。每张图含全图和同一处边缘近景。标题「纸灯城」和三个关卡名另用 Godot 的正式 HUD 纹理与着色器抓取黑白底，从两种画面反算出半透明像素。四张字形均保留透明背景及半透明边缘。[打开 140 张对照](alpha_edges/index.html) · [逐件数据、位置与哈希](alpha_edges/checks.json)

## 首轮定位与修整进度

| 对象 | 核对结果 |
| --- | --- |
| 巷口两张挡弹前景 | 左、右纸层分别有 5,410 和 2,029 个全透明黑像素紧贴有颜色的可见像素。外侧最薄的透明留边为 3 源像素。[左侧](alpha_edges/index.html#alley.scene_near_left) · [右侧](alpha_edges/index.html#alley.scene_near_right) |
| 七份纸偶图集 | 按正式绑定矩形核对 91 个分件，90 个有同类紧邻像素。涵盖摊贩、录像厅老板及另外五份居民图集。[图集对照](alpha_edges/index.html#atlas) |
| 其余单图 | 另有 54 张单图发现同类紧邻像素，包含天桥骑车居民和墨舞龙头部。逐件数据记录距离轮廓 8 像素内的情况，以及双线性采样中点的最大颜色通道差值。[骑车居民](alpha_edges/index.html#footbridge.image_018) · [龙头](alpha_edges/index.html#plaza.image_047) |

表中数量取自对应资产修整前。当前隔离包累计修整 67 张贴图。最新黑白叠底、91 个图集分件和 256 张色彩图的四邻检查均已更新。[前景和图集](edge_fill_report.md) · [优先单图](priority_edges_report.md) · [剩余贴图](remaining_edges_report.md) · [透明留边规格](../../../../../../../../docs/ART_PLAN_PAPER_LANTERN_CITY.md#121-三类图片和例外)

## 来源与验收

24 张程序直接生成的图层没有生成底色，包含「忘」字笔画、描边和余墨。15 张能按哈希定位到 T08 审阅包，历史材料未登记数值底色。其余 97 张现有来源记录未找到可直接用于 C02 的底色 RGB。黑白叠底已供目视复核，生成底色残留不超过 1% 的量化结论和正式 C02 签核仍待确认。[资产来源与覆盖](asset_coverage.md)

同一隔离包再次通过 15 站、118 条输入回放、失败重试和片尾跳过。正式 A7 签核及实体光枪实测待完成。[路线与真机步骤](report.md)

## 复跑

按[隔离启动说明](../report.md#构建隔离目录)准备 `$stage`。在仓库根目录的 PowerShell 执行。

```powershell
$lettering = Join-Path $env:TEMP 'paper-cast-lettering-edges'
$output = Join-Path $env:TEMP 'paper-cast-alpha-edges'
$script = (Resolve-Path gunforge/framework/tests/paper_lettering_edges.gd).Path
& $env:GODOT_BIN --path "$stage/gunforge/framework" --script $script -- "--build=$stage/level.json" "--assets=$stage" "--captures=$lettering"
uv run --locked --project gunforge/pipeline/art --with "jsonschema==4.26.0" python gunforge/pipeline/art/t16_alpha_edges.py --stage $stage --lettering $lettering --output $output
```

预期输出 136 份源图对照、4 份 Godot 字形对照和 91 个图集分件的数据。
