# 《纸灯城》龙头、骑车居民、弱点与准星边缘修整

三关候选按正式关卡的资源绑定更新了八张贴图。复用 8 源像素的透明边缘填色，在两份各 384 个文件的隔离包之间逐件核对。仅这八张图片的运行路径与哈希变化，全部 alpha、可见 RGB、原尺寸和 ICC 配置逐像素核对通过。[逐件哈希与回归](priority_edges/checks.json) · [当前候选试玩](../report.md#试玩)

| 对象 | 修整前紧邻轮廓的透明黑点 | 修整后 |
| --- | ---: | ---: |
| 墨舞龙上颚、下颚和尾纸 | 8,358 | 0 |
| 天桥骑车居民的站立与受惊姿态 | 6,659 | 0 |
| 磁带墨怪和墨伞的朱砂弱点 | 578 | 0 |
| HUD 准星 | 629 | 0 |

用 Godot 的纹理区域绘制代码，以 62.5% 和 125% 各渲染八张贴图，共 16 组前后对照。颜色变化集中在缩放时取样到透明像素的轮廓附近。图板取 125% 的边缘近景，右栏显示放大的颜色差值。[缩放对照](priority_edges/raster_comparison.jpg)

## 命中与完整路线

- 从修整前后的三关回放各取同一姿态，分别射击售票处磁带墨怪和海报厅墨伞的朱砂。四次实射均判为弱点命中，各扣一发光弹并净化目标。[坐标与命中结果](priority_edges/checks.json)
- 墨舞龙的 30 个姿势继续达到 40 px 有效命中半径门槛，上下颚实射仍挡弹。银幕影的四个目标均无墨色外命中，三路暖光切换通过。[墨舞龙图板](../dragon_masks/report.md) · [银幕影图板](../screen_boss_masks/report.md)
- 15 站、118 条输入回放、失败重试和四段片尾跳过通过。结果为 4 条灯芯、11 发光弹、7 人获救、9275 分。天桥居民和自行车仍为空枪，墨车夫可命中。准星显隐、失锁提示和六种窗口或全屏配置通过。[正式播放器回归数据](priority_edges/checks.json)

当前构建的 101 张整窗画面重新投影到模拟相机。几何范围内 606 组全部锁定，最大角点偏差仍为 0.749 个模拟相机像素。实心白矩形和缺失白边的反例均被拒绝。[C13 数据与复跑](../tracking_c13.md)

其余 46 张已定位单图在后续一轮完成修整，同轮还修整了四邻检查新定位的四张贴图。正式 C02 目视签核、实体光枪和 A7 签核待完成。[后续修整](remaining_edges_report.md) · [真机路线](device_route.md)

## 复跑

按[前景边缘修整步骤](edge_fill_report.md#复跑缩放与挡弹)分别准备本轮修整前后的隔离包。`$probes` 换成本报告目录中的 `priority_edges/probes.json`。要复测两处朱砂弱点，按[战斗输入回归](../udp/report.md#复跑)为待测构建生成同版本 `$fixture`，再运行以下命令。

```powershell
$script = (Resolve-Path gunforge/framework/tests/paper_cinema_weak_replay.gd).Path
& $env:GODOT_BIN --headless --path "$stage/gunforge/framework" --script $script -- "--build=$stage/level.json" "--assets=$stage" "--recording=$fixture"
```
