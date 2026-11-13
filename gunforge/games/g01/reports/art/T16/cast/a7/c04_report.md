# 《纸灯城》三关候选 C04 色板检查

基于当前隔离包的 296 条 PNG 资源记录和同构建的 41 张 Godot 原帧。贴图核对原文件哈希，原帧核对画廊记录的 PNG 哈希。数据包含每件贴图的来源、编译绑定、覆盖率及超差面积最大的五种 RGB。[候选清单](../candidate_manifest.json) · [逐件数据](c04_palette.json)

## 原始贴图

普通颜色使用定稿的九个色样，含墨黑。对 alpha 至少为 0.5 的像素按 alpha 加权，计算最近色样的 CIEDE2000 色差。覆盖率是色差不超过 15 的加权像素比例，现行门槛为 90%。灯光与独立朱砂件按编译绑定排除。四张字形沿用 Godot 材质的颜色键透明度，隐藏的灰底不计入可见色板。[项目色板](../../../../../bible/palette.json) · [美术计划](../../../../../../../../docs/ART_PLAN_PAPER_LANTERN_CITY.md#131-检查定义)

| 检查结果 | 资源记录数 |
| --- | ---: |
| 达到 90% 门槛 | 120 |
| 低于 90% 门槛 | 91 |
| 不适用 | 85 |

85 条不适用记录包括 40 张数据遮罩、26 张专用灯光、11 张独立朱砂贴图和 8 张在 alpha 0.5 处没有可计像素的贴图。有 57 条未绑定为朱砂用途的记录含近朱砂像素，仍需结合对应站点确认。

| 代表性低覆盖率样本 | 使用位置 | 覆盖率 |
| --- | --- | ---: |
| `city.png` | 片尾城市近景 | 66.35% |
| `city_wide_v1.png` | 片尾城市全景 | 72.96% |
| `square_02.png` | 广场、墨舞龙 | 75.83% |
| `street.png` | 天桥远街 | 71.04% |
| `railway_station_1_v2.png` | 第三关转场字形 | 25.26% |
| `near_right_luggage.png` | 站台右侧行李 | 9.24% |

当前门槛仍采用项目的初始值，C04 阈值标定和美术签核待完成。低覆盖率贴图需要同场景比较后再调色，尤其是已审阅的角色、字形和纸灯材质。

## 整帧朱砂用量

41 帧覆盖 15 站、战斗角色、三个 Boss、界面与片尾。用既有朱砂提取条件筛出候选像素，再按与 `#C8322C` 的色差计数。色差 ≤15 时有 19 帧超过画面 1% 的参考线，收窄至 ≤10 时有 3 帧超过参考线。近色会包含纸面、灯光或道具上的颜色，需要结合位置判读。

Godot 在同一时刻重画四组样本并隐藏 HUD 印章和当时可见的弱点贴图。墨舞龙样本同时隐藏龙嘴光晕。对照图从左到右为原帧、隐藏后原帧、剩余色差 ≤10 的青色标记。[四组同帧对照](c04_cinnabar_examples.jpg)

| 同帧样本 | 原帧近朱砂面积 | 隐藏后 |
| --- | ---: | ---: |
| 广场战斗 | 1.229% | 0.787% |
| 墨舞龙张口 | 1.382% | 0.839% |
| 天桥预警 | 0.364% | 0.127% |
| 片尾城市全景 | 1.031% | 1.031% |

隐藏后，广场与墨舞龙的窄范围占比回到 1% 以内。片尾全景保持 1.031%，标记集中在画面左侧的摊位和透光屋檐。这一区域已有独立的调色对照，可试玩并查看叠化和拉远的同帧对比。[片尾调色对照](ending_palette/report.md)三关回归通过 15 站、118 条输入回放与失败重试，50 张原路线抓帧逐字节一致。

## 复跑

按[三关隔离构建](../report.md#构建隔离目录)准备 `$stage`，再按[画廊抓帧](../report.md#全作一致性画廊)准备包含 `route` 子目录的 `$captures`。在仓库根目录运行。

```powershell
$cast = 'gunforge/games/g01/reports/art/T16/cast'
$probe = Join-Path $env:TEMP 'paper-cast-c04'
New-Item -ItemType Directory -Force "$probe/route" | Out-Null
& $env:GODOT_BIN --disable-vsync --audio-driver Dummy --path gunforge/framework --script res://tests/paper_cinnabar_probe.gd -- "--build=$stage/level.json" "--assets=$stage" "--captures=$probe/route" "--recording=$probe/route.dat" --failure-retry=true
if ($LASTEXITCODE) { throw 'Godot C04 probe failed' }
uv run --locked --project gunforge/pipeline/art python gunforge/pipeline/art/t16_asset_palette.py --stage $stage --manifest "$cast/candidate_manifest.json" --coverage "$cast/a7/asset_coverage.json" --gallery "$cast/gallery_checks.json" --captures $captures --stamps-probe "$probe/route" --stamps-preview "$probe/cinnabar_examples.jpg" --output "$probe/c04_palette.json"
```

原始证据位于 `D:\gunforge_cache\t16_cast_c04`。正式试玩仍从[三关候选入口](../report.md#试玩)启动。
