# 《纸灯城》开发状态与换机交接

更新于 2026-11-11。开发分支为 `main`，T13 本轮代码基线为 `c4d6ee1`。

## 当前进度

- **0B 与 T12 已验收。** 用户确认 0B 五项正式签核。T12 已完成 A5，手机光枪在显示器和电视上均通过。当前两关连续包 `paper.lantern_city` 已通过十站软件回归。第一关部分独立候选的设备复测仍有历史待项，详见[美术执行状态](../gunforge/games/g01/reports/art/execution_state.json)。
- **T13 连续候选已到工作台。** `paper.train_station` 串联候车室、站台、绿皮车厢和灯座，最后拉镜抵达工作台。通关、失败重试、资源跨站、输入回放、灯光预载均已验证。用户已验收原版候车室。工作台 Boss 仍待接入。[T13 报告](../gunforge/games/g01/reports/art/T13/report.md)
- **三站普通态对比度试样已可运行。** 候车室、站台、绿皮车厢各有一个独立候选，每站六个可射样本均达到 C06 的 0.20 数值门槛。灯座原版的两个样本已达标。试样色调与 1/8 缩略图辨识度留待美术复核。[四站预审画廊与 JPG 对照](../gunforge/games/g01/reports/art/T13/gallery.html)
- **四站硬化眼试样已可运行。** `paper.train_station_hardened` 采用原站点画面，四站五个姿态的 10 只眼均达到 C06 的亮度与尺寸门槛。射击硬化眼判为无效，软化时切回原朱砂印记。全程软件回归和回放已通过，墨伞眼形留待 A5。[硬化眼对照与验收记录](../gunforge/games/g01/reports/art/T13/variants/hardened_eyes/comparison/checks.json)

## 在新 Windows 机器上启动

准备 Git、Git LFS、uv 和 **Godot 4.6.3 Windows console**。下列命令在 PowerShell 执行。Godot 路径换成新机器上的实际位置。

```powershell
git lfs install
git clone --branch main https://github.com/xslkim/tvgun.git
Set-Location tvgun
git lfs pull

uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r gunforge/pipeline/level_design/requirements.lock

$env:GODOT_BIN = 'C:\Tools\Godot\Godot_v4.6.3-stable_win64_console.exe'
.\gunforge\start_level_player.ps1 -Package paper.train_station_hardened -Candidate -QuitAfter 2
```

已有本地克隆时，在 `main` 上执行 `git pull --ff-only origin main`，再执行 `git lfs pull`。启动冒烟检查应输出 `level_player_ready:true`、`http_error:0` 和空的 `udp_errors`。去掉 `-QuitAfter 2` 即可试玩。按 Enter 开始，左键射击，R 换弹。

- `paper.train_station` 打开 T13 原版四站连续候选。
- `paper.train_station_hardened` 打开四站暖纸色硬化眼试样。
- `paper.waiting_room_contrast`、`paper.platform_contrast`、`paper.green_car_contrast` 分别打开三个普通态对比度试样。
- `paper.lantern_city` 打开前两关连续包。加 `-SkipOpening` 可直接进玩法。

素材和 JPG 证据随 Git LFS 获取。`.venv`、Godot 可执行文件和编译缓存由新机器准备。启动器会按当前仓库路径生成关卡资源和编译收据。旧收据中的 `D:\tvgun`、`D:\gunforge_cache` 路径用于定位原机证据；新机器启动时用 `-Package … -Candidate` 生成本机路径。

继续做美术数值检查时，执行 `uv sync --locked --project gunforge/pipeline/art`。该环境包含 SciPy 和 scikit-image；当前候选的启动和关卡编译使用根目录的 `.venv`。旧 GPU 原始抓帧位于原机缓存，代表帧 JPG 和验收 JSON 已入库。

## 在新机器上复跑

先运行上面的硬化眼启动命令生成本机收据，再运行关卡编译器测试及 T13 连续候选软件回归。

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s gunforge/pipeline/level_design -p 'test_*.py'
$review = Get-Content -Raw gunforge/level_design/reviews/train_station_hardened_build.json | ConvertFrom-Json
$root = (Get-Location).Path
& $env:GODOT_BIN --headless --path gunforge/framework --script res://tests/train_station_tests.gd -- "--build=$($review.compiled)" "--assets=$root"
```

连续回归预期到达工作台，最终为 4 条灯芯、10 发光弹、2 人获救、1000 分。可读性抓帧由 `gunforge/framework/tests/train_stop_readability.gd` 生成，数值由 `gunforge/pipeline/art/t13_readability.py` 复算。`build_train_station_hardened.py --probe-builds <目录>` 可同时生成四站的单独抓帧构建。

## 接下来做什么

1. **合并 T13 可读性预审候选。** 沿用现有四站连续路线，把三个普通态调色试样与暖纸色硬化眼接到同一个独立候选。复跑 C03、C06、点灯和挡弹、跨站资源、失败重试、回放与纹理预载。给出同姿态 JPG，集中复核色调、墨伞眼形和缩略图。
2. **签核「忘」字七笔遮罩。** 确认七笔轮廓、笔顺、第 3 笔覆盖第 2 笔的关系，以及字形来源和授权。通过后制作 Boss 质感并接入工作台。遮罩签核期间可继续完成第 1 项。[笔顺 JPG](../gunforge/games/g01/reports/art/T13/forget_strokes/stroke_order.jpg) · [授权原文](../gunforge/games/g01/reports/art/T13/forget_strokes/ARPHICPL.TXT)
3. **T13 整关验收。** Boss 接入后统一做 A5、美术与玩法复核，再分别跑手机光枪的显示器和电视实测。更新[美术执行状态](../gunforge/games/g01/reports/art/execution_state.json)和 [T13 验收报告](../gunforge/games/g01/reports/art/T13/report.md)。
