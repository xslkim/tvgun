# 《纸灯城》A7 验收材料

本页 A7 证据对应的基线为 `paper.lantern_city_cast`，构建编号 `1ca059b468c9268ab77b22e9fb4cb2706cb37b21ec0d6efd3ad0296ab52bbccc`。隔离目录共 384 个文件，逐项核对哈希。342 个编译资源的来源记录均能定位到仓库文件，包含 19 张 RGBA8 运行副本和 67 张已修整透明边缘的运行副本。正式资产清单仍有 0 条已登记资产记录，A7 待签核，冻结状态为 `false`。[当前候选清单](../candidate_manifest.json) · [正式资产清单](../../../../../assets/manifest.json) · [项目的 A7 要求](../../../../../../../../docs/ART_TASKS_PAPER_LANTERN_CITY.md#t16-全作冻结a7停止点)

在仓库根目录运行下方命令可重编当前 PC 试玩版。[新版生命 HUD 与补给试玩](../supplies/report.md)

```powershell
powershell -ExecutionPolicy Bypass -File .\gunforge\start_level_player.ps1 -Package paper.lantern_city_cast -Candidate
```

[当前 PC 鼠标试玩验收](pc_mouse_review.md) · [隔离启动与复跑](../report.md#构建隔离目录) · [显示器与电视实测路线](device_route.md) · [构建及证据哈希](checks.json)

## 软件证据

| 验收项目 | 当前结果与证据 |
| --- | --- |
| 三关连续游玩 | 当前隔离目录重新通过 15 站、118 条输入回放、失败重试和片尾四段跳过。可查看 [本轮路线和结算](checks.json)。 |
| 图片编码 | 296 张 PNG 全部通过用途对应的通道检查。补齐 RGBA8 时的 50 张路线原帧逐像素一致。[逐件检查](asset_coverage.md) · [编码阶段回归](rgba8_regression.json) |
| 色板与朱砂 | 91 条资源低于初始 C04 覆盖率门槛。四组同帧对照将印章与弱点和场景色分开复查，片尾全景的近朱砂色重点在左侧摊位。[逐件色板与同帧对照](c04_report.md) · [可试玩的片尾调色对照](ending_palette/report.md) |
| 文字 | 四张标题与关卡字形在原始资产和 Godot 实际画面中均识别正确。256 条色彩图记录经 C05 筛查，82 条待目视复核。[逐件检查](c05_report.md) · [带框复核页](c05_review.html) |
| 半透明边缘 | 136 张源图及 4 张 Godot 字形有黑白叠底对照。累计 67 张运行副本保留原 alpha 与可见 RGB，256 张色彩图的四邻缺口为零。本轮完成 100 组 Godot 缩放对照。[修整与证据](remaining_edges_report.md) |
| 全作美术与 UI | 当前构建的画廊覆盖 15 站、8 套居民、7 种墨怪、3 个 Boss、15 个界面状态。51 张代表帧通过 C03。[全作一致性画廊](../gallery.html) · [采样清单](../gallery_checks.json) |
| 第三关普通目标、硬化与预警 | 20 个普通态与 10 只硬化眼达到 C06 数值门槛；8 个预警在 1/8 图中保留像素差异。见 [四站整帧复查](../readability_c06/report.md)。 |
| 三个 Boss | 墨舞龙 30 个姿势、银幕影 4 个目标、工作台 7 笔的有效半径均达 40 px。见 [墨舞龙](../dragon_masks/report.md)、[银幕影](../screen_boss_masks/report.md) 和 [工作台](../workbench_readability/report.md)。 |
| 战斗、校准与窗口 | 水洼、天桥、站台与转场通过 UDP 和 HTTP；最新版修正全屏白框裁切和缩放同帧偏移，37 次 UDP 扳机通过。见 [战斗输入](../udp/report.md)、[天桥与影院预警](../attack_warnings/report.md) 和 [窗口复查](../display_resize/report.md)。 |
| 追踪与性能 | 当前候选通过 606 组 C13 合成投影，最大角点偏差 0.749 模拟相机像素。当前构建的 C15 纹理预算通过，两轮 26,634 帧全部低于 16.67 ms。候车室第 8520 帧为 8.31–8.55 ms。[C13](../tracking_c13.md) · [C15](../performance.md) |
| 开场与片尾 | 90 秒开场、58 秒片尾、字幕和旁白窗口，以及键盘和 UDP 跳过、结算与重试已在姿态序列化优化前的隔离包通过正式播放器回归。当前候选通过三关回放和片尾跳过。[有声过场复查](../cutscene_player/report.md)。 |

## 待签核与补证

- 第三关 A5 仍需复核三关候选中的站台纸偶、普通与硬化状态、工作台 Boss 和低亮光点。天桥骑车居民、水洼小群、T14 界面与 T15 全景也纳入整作一致性审阅。[第三关画廊](../../../T13/gallery.html) · [界面预审](../../../T14/gallery.html) · [片尾预审](../../../T15/report.md)
- 用户已确认生命与补给候选的 PC 鼠标、手机光枪配 PC 显示器验收通过。电视实测和正式追踪录制按发布验收安排。[实测路线与录制位置](device_route.md)
- 342 个运行资源已逐件核对格式和来源，61 处命中遮罩通过。C02 四邻缺口已修整，黑白叠底仍待目视签核。C05 的疑似文字待目视核对。C04 低覆盖率素材进入调色对照。极限姿势、遮挡与循环继续按资产补证。[逐件覆盖与复跑](asset_coverage.md)
- 执行状态记录 280 次内置出图和 0 次外部付费调用。资产分类的尝试次数、有效率、返工原因及实际费用仍需汇总。[执行状态](../../../execution_state.json)

## 复跑最新隔离目录的完整路线

按隔离启动说明准备 `$stage`，关闭播放器窗口后在仓库根目录执行。

```powershell
$routeTest = (Resolve-Path gunforge/framework/tests/night_market_tests.gd).Path
& $env:GODOT_BIN --headless --path "$stage/gunforge/framework" --script $routeTest -- "--build=$stage/level.json" "--assets=$stage" --failure-retry=true
```

预期 `"passed":true`，15 站顺序到达，回放为 118 条输入。结算为 4 条灯芯、11 发光弹、7 人获救、9275 分。
