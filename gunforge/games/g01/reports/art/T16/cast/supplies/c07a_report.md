# 《纸灯城》三关画面覆盖复测

在通过 PC 鼠标验收的生命与补给构建 `ed50339937dd3994adf58a7db62fb3bce341f90c8723a3dccf01342f8c69c5d3` 上，以 Godot 4.6.3 Compatibility 和 1776×936 透明视口检查 C07a。透明视口可直接从 alpha 识别露底。先用一张全不透明图跑通过对照，再挖掉 16×9 像素矩形。检测器准确找到了 144 个透明像素和矩形位置。[逐帧数据](c07a_checks.json) · [故意留洞的反例](c07a_control_hole.png)

| 采样 | 范围 | 露底帧 |
| --- | --- | ---: |
| 185 个静态和视差极限样本 | 37 个场景段各测静止及四个镜头角点 | 0 |
| 406 个回放时刻 | 15 站、36 个场景段，分别检查静态图层合成与完整游戏画面 | 0 |

回放采样包括每秒、每段起止与四分点、工作台拉镜关键帧及相邻帧、片尾街巷和全景叠化的 0%、25%、50%、75%、100%。「摊主仍被困住」属于另一条路线，本轮覆盖它的静止和四角。巷口的逐层补画范围已用设计遮罩核对，结果见 [C07b 逐层诊断](c07b_report.md)。

[当前 PC 试玩](report.md)

## 复跑

使用与已验构建一致的隔离目录。在仓库根目录运行。

```powershell
$stage = 'D:/gunforge_cache/t16_cast_supplies_verified'
$work = Join-Path $env:TEMP 'paper-cast-c07a'
New-Item -ItemType Directory -Force $work | Out-Null
$route = (Resolve-Path gunforge/framework/tests/night_market_tests.gd).Path
$probe = (Resolve-Path gunforge/framework/tests/paper_station_coverage.gd).Path
& $env:GODOT_BIN --headless --path "$stage/gunforge/framework" --script $route -- "--build=$stage/level.json" "--assets=$stage" "--recording=$work/route.dat"
if ($LASTEXITCODE) { throw 'Campaign recording failed' }
& $env:GODOT_BIN --disable-vsync --audio-driver Dummy --path "$stage/gunforge/framework" --script $probe -- "--build=$stage/level.json" "--assets=$stage" "--recording=$work/route.dat" "--output=$work/coverage"
```
