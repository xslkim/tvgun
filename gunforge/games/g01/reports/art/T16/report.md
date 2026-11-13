# T16 三关交付候选清单

清单对应 `paper.lantern_city_epilogue`，含完整三关、90 秒开场和 58 秒有声片尾。每项编译资源记录相对路径、SHA-256、格式、关卡引用位置及来源记录。Windows 与 WSL 生成的清单内容一致。[候选清单](candidate_manifest.json) · [交付回归](delivery_checks.json)

[最新版 A7 验收材料](cast/a7/report.md) · [最新全作画廊](cast/gallery.html) · [此构建的早期画廊](gallery.html) · [早期抓帧与 A4 来源](gallery_checks.json)

| 文件 | 数量 | 核对结果 |
| --- | ---: | --- |
| 编译资源 | 333 | 288 张 PNG、15 段 PCM WAV、30 个 JSON 均通过哈希与读取检查 |
| 开场媒体 | 2 | 视频与字幕哈希符合开场清单，90 秒 Theora/Vorbis 视频完整解码 |
| 播放器及运行时 | 39 | 编译锁定的实现文件与播放器依赖逐项核对 |
| 编译包 | 1 | 构建身份、源清单和编译负载摘要通过校验 |

## 隔离目录验证

按清单复制出的目录恰有 375 个文件。从该目录启动 Windows Godot 4.6.3 后，开场在约 2 秒显示首句字幕，按 Esc 后进入巷口。三关 15 站、114 条输入回放、工作台失败重试、片尾自然播放和四段跳过均通过。故意改动隔离副本中的全景 PNG 时，Godot 拒绝启动。恢复后重新核对了隔离目录全部哈希。[隔离验证](delivery_checks.json)

## 试玩与复跑

从仓库根目录在 PowerShell 启动当前候选。首次开始会播放开场。

```powershell
powershell -ExecutionPolicy Bypass -File .\gunforge\start_level_player.ps1 -Package paper.lantern_city_epilogue -Candidate
```

已有编译收据时，可把清单和隔离运行目录输出到新的位置。下例使用项目的 Python 3.12 环境。

```powershell
$receipt = Get-Content -Raw gunforge/level_design/reviews/lantern_city_epilogue_build.json | ConvertFrom-Json
$stage = Join-Path $env:TEMP 'paper-lantern-city-t16'
& .\.venv\Scripts\python.exe gunforge/pipeline/level_design/audit_lantern_city_release.py --build $receipt.compiled --output "${stage}-manifest.json" --stage $stage
& $env:GODOT_BIN --path "$stage/gunforge/framework" --script res://tools/level_player.gd -- "--build=$stage/level.json" "--assets=$stage" "--opening-dir=$stage/gunforge/games/g01/cinematics/opening_original" --isolated-settings
```

## A7 待验

`g01/assets/` 有 66 个文件，其中 14 个进入当前运行包。巷口预审清单的 60 条记录全部匹配。清单保留巷口源素材和前版短片尾的归属。仓库正式资产清单目前有 0 条资产记录，冻结状态为 `false`。[仓库正式资产清单](../../../assets/manifest.json)

还需逐项补齐适用的美术与引擎检查，并完成第三关 A5、T14 界面、T15 全景与混音及整作实体光枪验收。哈希和解码通过记录在本候选中。[第三关预审](../T13/gallery.html) · [界面预审](../T14/gallery.html) · [片尾预审](../T15/report.md)

## 全作一致性画廊

同一构建的 46 张 Godot 抓帧全部通过 C03，涵盖三关 15 站、三个 Boss 和 15 个界面状态。三关 114 条输入回放、失败重试、片尾四段跳过和显示设置的 19 发本机模拟校准回归通过。居民和墨怪的局部可点开同姿态的完整画面。[画廊](gallery.html) · [画面、站点和取样帧记录](gallery_checks.json)

此清单对应的构建有六套居民造型和六种墨怪。后续三关候选已接入巷口墨蝌蚪、站台路人 A 和天桥骑车居民，更新后的隔离清单随新候选提供。[A4 设定与审核](../T09/gallery/index.html) · [最新试玩与清单](cast/report.md)

可用 `res://tests/paper_gallery_capture.gd` 按回放取样，用 `paper_action_tests.gd` 和 `display_setup_tests.gd` 生成界面抓帧。画廊生成脚本读取 `route`、`controls`、`display` 三个抓帧目录及同名日志，校验各自的构建编号后生成页面和检查清单。
