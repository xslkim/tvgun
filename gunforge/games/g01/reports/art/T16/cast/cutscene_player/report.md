# 《纸灯城》隔离候选开场与有声片尾

使用 `paper.lantern_city_cast` 的隔离目录运行正式播放器。开场视频、字幕和片尾 WAV 的哈希均与交付清单一致。片尾 WAV 与 T15 已回读的旁白混音逐字节一致，为 48 kHz、16 bit、双声道、58.0 秒。[T15 旁白和混音记录](../../../T15/wide_checks.json)

## 开场

90 秒开场自然播完，14 条字幕均在各自的媒体区间显示，字幕空档保持空白。另用两个全新播放器进程验证键盘 Enter 开始、Esc 跳过，以及 UDP START 开始、EXIT 跳过。三次均保持首站初始弹药和零射击计数。

## 片尾

从三关回放的点灯帧接入正式播放器。点灯、夜市、灯城全景、工作台四段的模拟时间分别从 0、7.2、20.8 和 47.8 秒开始，58.0 秒进入结算。两句旁白的四个音轨起止测点均落在对应字幕窗口，最新候选复测的最大采样时钟差为 0.203 秒。截帧在播放结束后统一写盘。

| 阶段 | 输入 | 实测结果 |
| --- | --- | --- |
| 点灯 | Enter | 跳过并停止音轨 |
| 夜市 | Esc | 显示设置可暂停和恢复音轨；关闭设置后可跳过 |
| 灯城全景 | UDP START | 跳过并停止音轨 |
| 工作台字幕 | UDP EXIT | 跳过并停止音轨 |

自然播放与四条跳过路径都保留 4 条灯芯、11 发光弹、7 人获救、9275 分。随后用 UDP START 重试，从巷口以零射击计数重新开始。测试使用无声驱动验证播放器解码、音轨时钟与字幕覆盖，扬声器实听和实体光枪仍待复核。[开场、旁白与结算画面](cutscene_frames.jpg) · [逐路径数据与媒体哈希](checks.json)

## 复跑

按[隔离候选说明](../report.md#构建隔离目录)准备 `$stage`，按[战斗输入回归](../udp/report.md#复跑)的第一条 Godot 命令生成 `$fixture`。在仓库根目录的 PowerShell 执行。自然播放用例包含约 90 秒开场和 58 秒片尾。

```powershell
$evidence = Join-Path $env:TEMP 'paper-cast-cutscene'
$script = (Resolve-Path gunforge/framework/tests/paper_cutscene_player_tests.gd).Path
$common = @("--build=$stage/level.json", "--assets=$stage", "--opening-dir=$stage/gunforge/games/g01/cinematics/opening_original", "--recording=$fixture")
foreach ($case in @('keyboard', 'udp', 'natural')) {
    & $env:GODOT_BIN --path "$stage/gunforge/framework" --max-fps 120 --audio-driver Dummy --script $script -- @common "--opening-case=$case" "--evidence=$evidence/$case"
    if ($LASTEXITCODE -ne 0) { throw "Cutscene regression failed for $case" }
}
uv run --locked --project gunforge/pipeline/art python gunforge/pipeline/art/t16_cutscene_player.py $evidence --stage $stage --output "$evidence/review"
```

三个 Godot 用例均应输出 `"passed":true`。汇总应包含 14 条开场字幕、4 个旁白测点和 4 条片尾跳过路径。
