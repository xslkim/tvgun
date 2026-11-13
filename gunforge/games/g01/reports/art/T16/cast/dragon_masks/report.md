# 《纸灯城》墨舞龙随动命中区复查

从 `paper.lantern_city_cast` 的三关回放进入广场。清完前置波次后，每个龙节在开放期间取三个游动姿势，龙嘴另取三个开放姿势与三个摆头姿势。测量使用 Godot 同一帧的渲染变换和逐像素命中判定，龙嘴扣除上下颚实际挡住的区域。

| 目标 | 抽样姿势 | 最小可命中有效半径 |
| --- | ---: | ---: |
| 龙节 08（尾侧） | 3 | 42.74 px |
| 龙节 07 | 3 | 43.76 px |
| 龙节 06 | 3 | 44.37 px |
| 龙节 05 | 3 | 45.01 px |
| 龙节 04 | 3 | 45.58 px |
| 龙节 03 | 3 | 46.33 px |
| 龙节 02 | 3 | 46.67 px |
| 龙节 01（头侧） | 3 | 47.15 px |
| 龙嘴朱砂核 | 6 | 42.67 px |

30 个姿势的有效半径均达到 40 px，命中区避开边缘带和游玩 HUD。前景累计遮盖达到 99% 的位置没有发现仍可命中的墨色像素。相邻铜扣轴心的最大偏差小于 0.001 px，11 张整帧均通过 C03。[八节游动、摆头和净化后的 1/8 图板](motion_1_8.jpg)

游动时只开放一节。龙尾的可射点移动 108.07 px 后，按原提交姿态仍能正确净化尾侧；再次用该姿态射击会被判为目标失效。八节依次从尾到头净化，每节露出暖纸并退出命中判定。

八节完成后才开放龙嘴。上下颚在六个嘴部姿势中挡住朱砂核原始覆盖的 624–630 个像素，实际误射两处龙颚均挡弹。预警中采到约 7.96° 的摆头，净化仍命中露出的朱砂核，并在喷墨释放前打断攻击。九个目标合计加 900 分，净化后的纸龙保留到转场，灯芯、救援、光弹和得分随玩家进入影院售票处。[龙嘴与龙颚近景](mouth_jaws.jpg) · [30 个姿势、同帧参考与命中记录](checks.json)

暖纸质感、实际距离下的弱点辨识和实体光枪体验留待整作复核。

## 复跑

按[隔离候选说明](../report.md#构建隔离目录)准备 `$stage`，按[战斗输入回归](../udp/report.md#复跑)的第一条 Godot 命令生成 `$fixture`。在仓库根目录的 PowerShell 执行。

```powershell
$captures = Join-Path $env:TEMP 'paper-cast-dragon'
& $env:GODOT_BIN --path gunforge/framework --max-fps 120 --audio-driver Dummy --script res://tests/dragon_campaign_masks_tests.gd -- "--build=$stage/level.json" "--assets=$stage" "--recording=$fixture" "--captures=$captures"
uv run --locked --project gunforge/pipeline/art python gunforge/pipeline/art/t16_dragon_masks.py $captures --build "$stage/level.json" --output "$captures/review"
```

Godot 应输出 `"passed":true`。分析结果应记录 30 个姿势的有效半径达标、11 张整帧通过 C03。
