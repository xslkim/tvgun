# 《纸灯城》站台路人 A

第三关站台换上路人 A。她沿用 A4 造型和 T10 纸偶分件，受困时挣扎，打掉胸口墨团后跳起致谢。误射受困时的纸身会扣 50 分。获救后她留在站台，光弹可穿过纸身。售票处保留检票员。

[受困姿态](struggle.jpg) · [净化与获救](rescue.jpg) · [致谢](thank.jpg) · [三关候选站台](platform_campaign.jpg) · [绿皮车厢衔接](car_handoff.jpg)

## 试玩

在仓库根目录的 PowerShell 运行，按 Enter 开始，左键射击，R 换弹。第一行直接进入站台，第二行从三关开头进入。

```powershell
powershell -ExecutionPolicy Bypass -File .\gunforge\start_level_player.ps1 -Package paper.platform_passerby -Candidate
powershell -ExecutionPolicy Bypass -File .\gunforge\start_level_player.ps1 -Package paper.lantern_city_rescue -Candidate
```

## Godot 验证

- 站台独立回归的 8 发均绑定显示时的姿态。误射纸身扣 50 分，居民和墨团的生命保持原值。一发命中胸口墨团即救出 1 人。获救后射击纸身及使用获救前的纸身或墨团瞄准姿态均不再扣分或重复计数。结算、重试和完整回放通过。
- 受困动画样本中，纸身最小高度为 319.02 个规范像素。四个抓帧里墨团命中覆盖均位于纸身可见区域内，有效半径至少 41.49 像素，C09 通过。普通态 C06 对比度为 0.233–0.234，四个样本均达到 0.20 数值门槛。五张代表帧通过 C03。
- 三关候选通过 15 站、118 条输入回放、水洼与工作台失败重试及片尾自然播放和四段跳过。进入站台时已救 6 人，离开站台进入绿皮车厢时已救 7 人。开场、鼠标、键盘与本机模拟光枪输入均通过。

[软件证据及分件哈希](software_checks.json) · [站台构建收据](../../../../../../level_design/reviews/platform_passerby_build.json) · [三关构建收据](../../../../../../level_design/reviews/lantern_city_rescue_build.json)

## 复跑

```powershell
$root = (Get-Location).Path
$platform = Get-Content -Raw gunforge/level_design/reviews/platform_passerby_build.json | ConvertFrom-Json
& $env:GODOT_BIN --path gunforge/framework --script res://tests/platform_passerby_tests.gd -- "--build=$($platform.compiled)" "--assets=$root" "--captures=$env:TEMP/paper-platform-passerby"
$campaign = Get-Content -Raw gunforge/level_design/reviews/lantern_city_rescue_build.json | ConvertFrom-Json
& $env:GODOT_BIN --path gunforge/framework --script res://tests/tadpole_campaign_tests.gd -- "--build=$($campaign.compiled)" "--assets=$root" "--captures=$env:TEMP/paper-rescue-campaign" --failure-retry=true
```

C06 缩略图辨识度、纸偶动作美术与实体光枪待验收。下一步接入骑车的人，验证安全居民与墨车夫在造型和射击判定上的区别。
